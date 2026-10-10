"""Orchestrates the budget-constrained resilience optimiser on top of the finder's event screen."""
from __future__ import annotations

import time

import numpy as np

from ..domain.dataset import FnbDataset
from ..models import optimiser as opt
from ..models import reverse_stress as rs
from ..models.mitigation import LABEL
from ..schemas.finder import OptimiseRequest
from ..schemas.mitigation import Intervention
from .finder import screen

N_EVENTS = 50          # optimise over the top representatives of the screen


def auto_candidates(ds: FnbDataset, sc, events_idx: list[int], max_n: int) -> list[Intervention]:
    """Candidates from where the tail events bite: protect the upstream nodes behind the most portfolio loss, and
    buffer / diversify / qualify substitutes at the owned business units that lose most (weighted by their share of the
    holding, so in the company view a small segment of a large group ranks by what it actually carries)."""
    fin, d0, w = sc.fin[events_idx], sc.d0[events_idx], sc.w
    owned = sc.owned
    ids = sc.net.node_ids
    upstream_score = {}
    for r in range(len(events_idx)):
        for i in np.flatnonzero(d0[r] > 0.05):
            if ids[i] not in owned and ds.by_id[ids[i]].entity_type != "financial":
                upstream_score[ids[i]] = upstream_score.get(ids[i], 0.0) + float((fin[r] @ w) * d0[r, i])
    holding_loss = {k: float((fin[:, sc.net.idx[k]] * (sc.net.va[sc.net.idx[k]] > 0)).sum() * w[sc.net.idx[k]]) for k in sorted(owned)}
    out: list[Intervention] = []
    for nid, _ in sorted(upstream_score.items(), key=lambda kv: -kv[1])[:4]:
        out.append(Intervention(type="facility_protection", entity_ids=[nid], magnitude=0.4, label=f"Protect {ds.by_id[nid].name}"))
    for hid_, _ in sorted(holding_loss.items(), key=lambda kv: -kv[1])[:4]:
        nm = ds.by_id[hid_].name
        out += [Intervention(type="inventory_buffer", entity_ids=[hid_], magnitude=14, label=f"+14 d inventory at {nm}"),
                Intervention(type="supplier_diversification", entity_ids=[hid_], magnitude=0.5, label=f"Diversify suppliers of {nm}"),
                Intervention(type="input_substitution", entity_ids=[hid_], magnitude=0.2, label=f"Qualify substitutes at {nm}")]
    return out[:max_n]


def run_optimise(ds: FnbDataset, req: OptimiseRequest) -> dict:
    t0 = time.perf_counter()
    sc = screen(ds, req.finder)
    events_idx = sc.reps[:N_EVENTS]
    events = [sc.events[i] for i in events_idx]
    cands = req.candidates or auto_candidates(ds, sc, events_idx, req.max_candidates)
    bad = [i for c in cands for i in c.entity_ids if i not in ds.by_id]
    if bad:
        raise ValueError(f"unknown entity ids in candidates: {bad[:5]}")
    pb = opt.make_problem(ds.entities, ds.relations, events, sc.weights, sc.params, min(req.tail_events, len(events)), cands)
    base = pb.evaluate(())
    plan, path = opt.greedy(pb, req.budget_musd)
    greedy_val = pb.evaluate(tuple(plan))
    plan = opt.local_search(pb, plan, req.budget_musd)
    best = pb.evaluate(tuple(plan))
    frontier_plan, frontier = opt.greedy(pb, float(pb.costs.sum()) + 1.0)

    exh = None
    if req.exhaustive_check:
        single_ratio = sorted(range(len(cands)), key=lambda j: -(base - pb.evaluate((j,))) / max(pb.costs[j], 1e-6))
        pool = single_ratio[:10]
        e = opt.exhaustive(pb, req.budget_musd, pool)
        red_best = base - e["best_objective"]
        exh = dict(pool_size=len(pool), pool_note="all candidates" if len(cands) <= 10 else "10 best by single-intervention benefit per cost",
                   n_feasible_plans=e["n_feasible_plans"], best_objective=e["best_objective"],
                   best_plan=[cands[j].label for j in e["best_plan"]],
                   optimality_gap=None if red_best <= 1e-15 else round(max(0.0, (red_best - (base - best)) / red_best), 4),
                   note="Gap = share of the exhaustive optimum's reduction that the greedy + swap plan misses, within the pool.")

    def jacc(a, b):
        a, b = set(a), set(b)
        return 1.0 if not a and not b else len(a & b) / len(a | b)

    sens = []
    for f in (0.5, 2.0):
        alt, _ = opt.greedy(pb, req.budget_musd, pb.costs * f)
        alt = opt.local_search(pb, alt, req.budget_musd) if f == 1 else alt
        sens.append(dict(cost_factor=f, plan=[cands[j].label for j in alt], objective=pb.evaluate(tuple(alt)), jaccard_with_base=round(jacc(alt, plan), 3)))

    robust = None
    if req.robustness_draws > 0:
        k = pb.tail
        base_d = rs.stability_draws(pb_net(pb, ()), ds.entities, events, rs.weight_vector(pb_net(pb, ()), sc.weights), sc.params,
                                    req.robustness_draws, req.seed)
        _, _, _, ents_p, _, net_p = pb._tail(tuple(sorted(plan)))
        plan_d = rs.stability_draws(net_p, ents_p, events, rs.weight_vector(net_p, sc.weights), sc.params, req.robustness_draws, req.seed)
        tail = lambda m: np.sort(m, axis=1)[:, ::-1][:, :k].mean(axis=1)  # noqa: E731
        red = tail(base_d) - tail(plan_d)
        robust = dict(n_draws=req.robustness_draws, seed=req.seed, median_reduction=float(np.median(red)), p05=float(np.percentile(red, 5)),
                      p95=float(np.percentile(red, 95)), share_positive=float((red > 0).mean()))

    # additive output: the events that still hurt most after the plan (read from the engine call already made; no new maths)
    p_before = pb._tail(())[1]
    p_after = pb._tail(tuple(sorted(plan)))[1]
    residual = [dict(id=events[i].id, label=events[i].label, hazard=events[i].hazard, baseline_impact=float(p_before[i]), after_impact=float(p_after[i]))
                for i in np.argsort(-p_after)[:5]]

    chosen = [dict(label=cands[j].label, type=cands[j].type, entity_ids=cands[j].entity_ids, magnitude=cands[j].magnitude,
                   annualised_cost_musd=round(float(pb.costs[j]), 4), single_reduction=pb.evaluate(()) - pb.evaluate((j,)))
              for j in plan]
    return dict(
        budget_musd=req.budget_musd, tail_events=pb.tail, n_events=len(events), baseline_objective=base, plan_objective=best,
        reduction=base - best, reduction_fraction=(base - best) / base if base > 1e-15 else None,
        greedy_objective=greedy_val, local_search_improved=best < greedy_val - 1e-12,
        plan=chosen, plan_cost_musd=round(float(pb.costs[plan].sum()) if plan else 0.0, 4), plan_interventions=[cands[j].model_dump() for j in plan],
        candidates=[dict(label=c.label, type=c.type, entity_ids=c.entity_ids, magnitude=c.magnitude, annualised_cost_musd=round(float(pb.costs[j]), 4),
                         single_reduction=base - pb.evaluate((j,))) for j, c in enumerate(cands)],
        frontier=[dict(label=cands[x["candidate"]].label, cumulative_cost_musd=x["cumulative_cost"], objective=x["objective"]) for x in frontier],
        residual_events=residual, exhaustive=exh, cost_sensitivity=sens, robustness=robust, evaluations=len(pb.cache), runtime_seconds=round(time.perf_counter() - t0, 2),
        method=("Decision variables: one 0/1 choice per candidate intervention. Constraint: total annualised cost <= budget (placeholder costs); "
                "alternative-sourcing capacity enforced in simulation. Objective: mean portfolio impact of the worst "
                f"{pb.tail} of the top {len(events)} distinct events after the plan. Search: greedy by reduction per cost, then 1-swap local search."),
        units={"objective": "position-weighted share of annual value added lost (0-1), mean over the tail events", "cost": "USD million per year (synthetic)"},
        assumptions=["Intervention costs, magnitudes and feasibility are SYNTHETIC placeholders (see Mitigation laboratory).",
                     "Events carry no probabilities; the objective protects against the worst consequences in the event set.",
                     "Greedy plus local search is a heuristic; the exhaustive check reports the gap on a pool of at most 10 candidates.",
                     "Nothing here has been implemented in the real world."],
        labels={k: v for k, v in LABEL.items()})


def pb_net(pb, key):
    return pb._tail(tuple(sorted(key)))[5]
