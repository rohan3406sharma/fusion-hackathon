"""Orchestrates one deterministic scenario run: direct exposure -> propagation -> losses -> breakdowns -> comparison."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..domain.holdings import Holdings, units_holdings
from ..models import analytics
from ..models.climate import DirectExposureInputs, build_direct_inputs, direct_disruption, hazard_intensity_at_entities
from ..models.propagation import Network, compile_network, simulate
from ..schemas.domain import Entity, Relation
from ..schemas.results import RunResult
from ..schemas.scenario import ScenarioSpec

DIRECT_THR = 0.01     # disruption fraction above which an entity counts as directly exposed
INDIRECT_THR = 1e-3
HOP_THR = 1e-4

ORDER_EVIDENCE = {
    "direct": "Direct impact: proxy damage function on a SYNTHETIC hazard input. Direction of supplier->customer effects is well supported; size is not.",
    "1": "First-order: direction well supported by firm-level studies (moderate for size). Model estimate here.",
    "2": "Second-order: supported by two studies only. Model estimate, lower confidence.",
    "3": "Third-order: model-based only (no firm-level climate evidence found). Low confidence.",
    "4+": "Deeper hops: speculative model extrapolation. Very low confidence.",
}
LIMITATIONS = [
    "All entities, relationships, locations, vulnerabilities and hazard footprints are SYNTHETIC demonstration data.",
    "Hazard intensity is a dimensionless scenario index; it is not flood depth, temperature or a probability.",
    "The direct-disruption function is a configurable proxy, not a validated damage function.",
    "Second-order effects have limited empirical support; third-order and deeper results are model-based and low confidence.",
    "There is no universal indirect-loss multiplier; the indirect/direct ratio shown is an output of these assumptions only.",
    "Loss is value-added at risk over the disruption period, not a forecast of financial loss, and ignores re-routing beyond the stated parameters.",
    "Network-aware vs location-only superiority at portfolio level is an open research question; this is a model comparison, not evidence.",
]


@dataclass
class Execution:
    net: Network
    direct: DirectExposureInputs
    d0: np.ndarray
    trans: np.ndarray
    hist: list[np.ndarray]
    converged: bool
    T: float
    period_fraction: float

    @property
    def final(self) -> np.ndarray:
        return self.hist[-1][0]

    def losses(self) -> tuple[np.ndarray, np.ndarray]:
        va = self.net.va * self.period_fraction
        return va * self.d0, va * self.final


def execute(entities: list[Entity], relations: list[Relation], spec: ScenarioSpec, max_depth: int | None = None,
            net: Network | None = None) -> Execution:
    net = net or compile_network(entities, relations)
    direct = build_direct_inputs(entities, spec)
    d0 = direct_disruption(direct)                      # (1,N)
    T = direct.effective_duration_days
    depth = max_depth or spec.propagation_max_depth
    hist, conv, eff = simulate(net, d0, T, inventory_scale=spec.inventory_scale, substitution_scale=spec.substitution_scale,
                               dependency_scale=spec.dependency_scale, use_graph_alternatives=spec.use_graph_alternatives,
                               cycle_damping=spec.cycle_damping, max_depth=depth)
    return Execution(net, direct, d0[0], eff[0], [h for h in hist], conv, T, min(1.0, T / 365.0))


def _breakdown(rows: list[dict], key: str) -> list[dict]:
    df = pd.DataFrame(rows)
    out = []
    for k, g in df.groupby(key):
        out.append(dict(key=str(k), entities=int(len(g)), affected=int((g["status"] != "unaffected").sum()),
                        direct_loss_musd=round(float(g.direct_loss_musd.sum()), 3),
                        indirect_loss_musd=round(float(g.indirect_loss_musd.sum()), 3),
                        total_loss_musd=round(float(g.total_loss_musd.sum()), 3)))
    return sorted(out, key=lambda x: -x["total_loss_musd"])


def order_losses(ex: Execution) -> dict[str, np.ndarray]:
    """Incremental loss per entity by propagation order (state differences between successive hops)."""
    va = ex.net.va * ex.period_fraction
    out = {"1": np.zeros(ex.net.n), "2": np.zeros(ex.net.n), "3": np.zeros(ex.net.n), "4+": np.zeros(ex.net.n)}
    for t in range(1, len(ex.hist)):
        inc = va * (ex.hist[t][0] - ex.hist[t - 1][0])
        out["4+" if t >= 4 else str(t)] += inc
    return out


def build_run_result(entities: list[Entity], relations: list[Relation], spec: ScenarioSpec, scenario_id: str | None,
                     top_paths: int = 10, max_depth: int | None = None, weights: dict[str, float] | None = None,
                     holdings: Holdings | None = None) -> RunResult:
    ex = execute(entities, relations, spec, max_depth)
    net = ex.net
    ol = order_losses(ex)
    dloss, tloss = ex.losses()
    inten = hazard_intensity_at_entities(ex.direct)
    vsel = np.max(ex.direct.vuln * (ex.direct.weights > 0), axis=0)
    first_hop = np.zeros(net.n, dtype=int)
    for t in range(1, len(ex.hist)):
        newly = (first_hop == 0) & ((ex.hist[t][0] - ex.hist[0][0]) > HOP_THR)
        first_hop[newly] = t
    rows: list[dict] = []
    for i, e in enumerate(entities):
        status = "direct" if ex.d0[i] > DIRECT_THR else ("propagated" if ex.final[i] - ex.d0[i] > INDIRECT_THR else "unaffected")
        hop = 0 if status == "direct" else (int(first_hop[i]) if status == "propagated" else None)
        label_key = "direct" if hop == 0 else ("4+" if (hop or 0) >= 4 else str(hop))
        rows.append(dict(
            entity_id=e.id, name=e.name, entity_type=e.entity_type, food_category=e.food_category, country=e.country,
            region=e.region, synthetic=e.synthetic, status=status, hazard_intensity=round(float(inten[i]), 4),
            direct_disruption=round(float(ex.d0[i]), 4), final_disruption=round(float(ex.final[i]), 4), hop_order=hop,
            value_added_musd=e.value_added_musd, direct_loss_musd=round(float(dloss[i]), 3),
            indirect_loss_musd=round(float(tloss[i] - dloss[i]), 3), total_loss_musd=round(float(tloss[i]), 3),
            loss_by_order_musd={k: round(float(v[i]), 3) for k, v in ol.items()},
            evidence_label=ORDER_EVIDENCE.get(label_key, "Not affected under this scenario.") if status != "unaffected" else "Not affected under this scenario."))
    direct_total, total = float(dloss.sum()), float(tloss.sum())
    order_defs = [("direct", "Direct impact", float(dloss.sum()), int((ex.d0 > DIRECT_THR).sum()))]
    for k, lab in (("1", "First-order"), ("2", "Second-order"), ("3", "Third-order"), ("4+", "Deeper (4+)")):
        order_defs.append((k, lab, float(ol[k].sum()), int(((first_hop == int(k[0])) if k != "4+" else (first_hop >= 4)).sum() - 0)))
    orders = [dict(order=k, label=l, entities=n_, loss_musd=round(v, 3), evidence=ORDER_EVIDENCE[k]) for k, l, v, n_ in order_defs]
    names = {e.id: e.name for e in entities}
    paths = analytics.dominant_paths(net, ex.trans, ex.d0, names, {r["entity_id"]: r["total_loss_musd"] for r in rows}, top=top_paths)
    # bottlenecks: systemic score with scenario exposure
    scores = analytics.systemic_scores(entities, relations, ex.d0)
    bott = [dict(entity_id=s["entity_id"], name=s["name"], score=s["score"], downstream_reach=s["downstream_reach"],
                 betweenness=s["betweenness"], out_degree=s["out_degree"],
                 weighted_out_dependency=s["weighted_out_dependency"], note="ranking score, not a loss estimate") for s in scores if s["out_degree"] > 0][:8]
    cmp_ = build_comparison(entities, rows, dloss, tloss, weights, ex.period_fraction, holdings)
    summary = dict(
        n_entities=net.n, n_exposed_facilities=int((ex.d0 > DIRECT_THR).sum()),
        n_affected_downstream=int(sum(r["status"] == "propagated" for r in rows)),
        direct_loss_musd=round(direct_total, 3), indirect_loss_musd=round(total - direct_total, 3), total_loss_musd=round(total, 3),
        indirect_to_direct_ratio=round((total - direct_total) / direct_total, 3) if direct_total > 1e-9 else None,
        iterations=len(ex.hist) - 1, converged=bool(ex.converged), effective_duration_days=round(ex.T, 1),
        loss_period_fraction=round(ex.period_fraction, 4), max_depth_used=max_depth or spec.propagation_max_depth)
    assumptions = [
        f"Hazard source: {spec.data_source} (synthetic footprint; intensity is an index).",
        f"Effective disruption duration T = {ex.T:.0f} days (event + recovery); losses scaled by T/365 = {ex.period_fraction:.2f} of annual value added.",
        f"Inventory scale x{spec.inventory_scale}, substitution scale x{spec.substitution_scale}, dependency scale x{spec.dependency_scale}.",
        f"Propagation depth {summary['max_depth_used']} hops; tolerance 1e-6; converged={ex.converged}.",
        "Economic base is entity value added (revenue x type-specific ratio), so losses are less prone to chain double-counting than revenue.",
        "Financial-channel edges (lenders/insurers) are shown in the graph but excluded from physical propagation.",
    ] + ([f"Compound amplification of {spec.compound_amplification:.0%} applied where hazards overlap (analyst assumption)."] if spec.compound_amplification > 0 else [])
    units = {"losses": "USD million (value-added at risk over the disruption period)", "disruption": "fraction of normal output, 0-1",
             "hazard_intensity": "dimensionless scenario index 0-1", "transmission": "fraction of a supplier's disruption passed to the customer"}
    return RunResult.model_validate(dict(
        scenario=spec, scenario_id=scenario_id, summary=summary, orders=orders, entities=rows,
        by_food_category=_breakdown(rows, "food_category"), by_entity_type=_breakdown(rows, "entity_type"),
        by_region=_breakdown(rows, "country"), critical_paths=paths, comparison=cmp_, bottlenecks=bott,
        assumptions=assumptions, limitations=LIMITATIONS, units=units))


HIDDEN_THRESHOLDS = (0.01, 0.02, 0.05, 0.10)


def default_weights(entities: list[Entity]) -> dict[str, float]:
    ids = [e.id for e in entities if e.in_demo_portfolio]
    return {i: 1.0 / len(ids) for i in ids} if ids else {}


def build_comparison(entities: list[Entity], rows: list[dict], dloss: np.ndarray, tloss: np.ndarray,
                     weights: dict[str, float] | None = None, period_fraction: float = 1.0, holdings: Holdings | None = None) -> dict:
    """Location-only vs network-aware, for the whole network and per holding. A holding is a business unit (weights) or,
    when `holdings` is a company view, a company whose disruption is the value-added-weighted average of its segments."""
    loc_total, net_total = float(dloss.sum()), float(tloss.sum())
    if holdings is None:
        holdings = units_holdings(entities, default_weights(entities) if weights is None else weights)
    company = holdings.view == "company"
    idx = {e.id: i for i, e in enumerate(entities)}
    hold = sorted(holdings.holdings, key=lambda h: min(idx[s.entity_id] for s in h.segments))      # network order, as v0.3
    loc_d = [sum(s.share * rows[idx[s.entity_id]]["direct_disruption"] for s in h.segments) for h in hold]
    net_d = [sum(s.share * rows[idx[s.entity_id]]["final_disruption"] for s in h.segments) for h in hold]
    loc_f, net_f = pd.Series(loc_d, dtype=float), pd.Series(net_d, dtype=float)
    # average ranks: tied holdings (e.g. many with zero direct disruption) share the mean rank, so a tie is not read as "rank 1"
    r_loc = loc_f.rank(ascending=False, method="average") if len(hold) else loc_f
    r_net = net_f.rank(ascending=False, method="average") if len(hold) else net_f
    prow = []
    for k, h in enumerate(hold):
        ld, nd = round(loc_d[k], 4), round(net_d[k], 4)
        hidden = ld < DIRECT_THR and (nd - ld) >= 0.05
        row = dict(entity_id=h.id, name=h.name, location_disruption=ld, network_disruption=nd,
                   location_loss_musd=round(sum(rows[idx[s.entity_id]]["direct_loss_musd"] for s in h.segments), 3),
                   network_loss_musd=round(sum(rows[idx[s.entity_id]]["total_loss_musd"] for s in h.segments), 3),
                   rank_location=float(r_loc[k]), rank_network=float(r_net[k]),
                   # a holding untouched in both views did not "move"
                   rank_change=0.0 if nd < 1e-4 else float(r_loc[k] - r_net[k]),
                   hidden_exposure=bool(hidden), weight=round(h.weight, 6), kind=h.kind, primary_entity_id=h.primary_entity_id)
        if h.multi_segment:
            fins = [rows[idx[s.entity_id]]["final_disruption"] for s in h.segments]
            row.update(other_businesses_share=h.other_share, network_disruption_if_other_hit=round(nd / max(1.0 - h.other_share, 1e-12), 4),
                       network_disruption_one_node=round(1.0 - float(np.prod([1.0 - f for f in fins])), 4),
                       segments=[dict(entity_id=s.entity_id, name=s.name, segment=s.label, share=round(s.share, 4),
                                      location_disruption=rows[idx[s.entity_id]]["direct_disruption"], network_disruption=f)
                                 for s, f in zip(h.segments, fins)])
        prow.append(row)
    prow.sort(key=lambda r: r["rank_network"])
    pl = sum(r["location_loss_musd"] for r in prow)
    pn = sum(r["network_loss_musd"] for r in prow)
    rel = lambda a, b: round((b - a) / a, 4) if a > 1e-9 else None  # noqa: E731
    # position-weighted impact = sum_h w_h * disruption_h * T/365, i.e. share of each holding's annual value added lost
    w_loc = sum(r["weight"] * r["location_disruption"] for r in prow) * period_fraction
    w_net = sum(r["weight"] * r["network_disruption"] for r in prow) * period_fraction
    upper = sum(r["weight"] * r.get("network_disruption_if_other_hit", r["network_disruption"]) for r in prow) * period_fraction
    one = sum(r["weight"] * r.get("network_disruption_one_node", r["network_disruption"]) for r in prow) * period_fraction
    curve = [dict(threshold=t, count=sum(1 for r in prow if r["location_disruption"] < DIRECT_THR
                                        and r["network_disruption"] - r["location_disruption"] >= t)) for t in HIDDEN_THRESHOLDS]
    n_multi = sum(1 for r in prow if r["kind"] == "multi_segment")
    who = (f"{len(prow)} SYNTHETIC companies ({n_multi} with several business units, each company's disruption the value-added-weighted "
           "average of its units; any share outside Food & Beverage is not modelled)" if company else f"{len(prow)} SYNTHETIC holdings")
    return dict(
        location_only_loss_musd=round(loc_total, 3), network_aware_loss_musd=round(net_total, 3),
        absolute_difference_musd=round(net_total - loc_total, 3), relative_difference=rel(loc_total, net_total),
        portfolio_location_loss_musd=round(pl, 3), portfolio_network_loss_musd=round(pn, 3),
        portfolio_absolute_difference_musd=round(pn - pl, 3), portfolio_relative_difference=rel(pl, pn),
        portfolio_rows=prow, hidden_exposure_count=sum(r["hidden_exposure"] for r in prow),
        portfolio_location_impact=round(w_loc, 6), portfolio_network_impact=round(w_net, 6),
        portfolio_hidden_share=round(1 - w_loc / w_net, 4) if w_net > 1e-12 else None,
        hidden_exposure_curve=curve, holding_view=holdings.view,
        portfolio_network_impact_if_other_hit=round(upper, 6) if company else None,
        portfolio_network_impact_one_node=round(one, 6) if company else None,
        scope_note=(f"Location-only = direct losses at exposed facilities. Network-aware = direct + modelled indirect losses through "
                    f"supply links. Portfolio = {who} with synthetic position weights; impact = position-weighted share "
                    "of annual value added lost. The USD figures are an unweighted sum of the holdings' value-added loss. Both views are "
                    "model outputs under stated assumptions; no study has validated this comparison end-to-end. 'Hidden exposure' flags "
                    "holdings with <1% direct and >=5% propagated disruption; the curve shows how that count depends on the cut-off."))
