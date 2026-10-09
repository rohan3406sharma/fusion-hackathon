"""Orchestrates one deterministic scenario run: direct exposure -> propagation -> losses -> breakdowns -> comparison."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..models import analytics
from ..models.climate import DirectExposureInputs, build_direct_inputs, direct_disruption, hazard_intensity_at_entities
from ..models.propagation import Network, compile_network, propagate, transmission
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
    trans = transmission(net, T, inventory_scale=spec.inventory_scale, substitution_scale=spec.substitution_scale,
                         dependency_scale=spec.dependency_scale)
    depth = max_depth or spec.propagation_max_depth
    hist, conv = propagate(net, d0, trans, max_depth=depth)
    return Execution(net, direct, d0[0], trans[0], [h for h in hist], conv, T, min(1.0, T / 365.0))


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
                     top_paths: int = 10, max_depth: int | None = None) -> RunResult:
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
    cmp_ = build_comparison(entities, rows, dloss, tloss)
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


def build_comparison(entities: list[Entity], rows: list[dict], dloss: np.ndarray, tloss: np.ndarray) -> dict:
    loc_total, net_total = float(dloss.sum()), float(tloss.sum())
    hold = [(i, e) for i, e in enumerate(entities) if e.in_demo_portfolio]
    loc_f = pd.Series([rows[i]["direct_disruption"] for i, _ in hold])
    net_f = pd.Series([rows[i]["final_disruption"] for i, _ in hold])
    # average ranks: tied holdings (e.g. many with zero direct disruption) share the mean rank, so a tie is not read as "rank 1"
    r_loc = loc_f.rank(ascending=False, method="average") if len(hold) else loc_f
    r_net = net_f.rank(ascending=False, method="average") if len(hold) else net_f
    prow = []
    for k, (i, e) in enumerate(hold):
        hidden = rows[i]["direct_disruption"] < DIRECT_THR and (rows[i]["final_disruption"] - rows[i]["direct_disruption"]) >= 0.05
        prow.append(dict(entity_id=e.id, name=e.name, location_disruption=rows[i]["direct_disruption"],
                         network_disruption=rows[i]["final_disruption"], location_loss_musd=rows[i]["direct_loss_musd"],
                         network_loss_musd=rows[i]["total_loss_musd"], rank_location=float(r_loc[k]), rank_network=float(r_net[k]),
                         # a holding untouched in both views did not "move"
                         rank_change=0.0 if rows[i]["final_disruption"] < 1e-4 else float(r_loc[k] - r_net[k]),
                         hidden_exposure=bool(hidden)))
    prow.sort(key=lambda r: r["rank_network"])
    pl = sum(r["location_loss_musd"] for r in prow)
    pn = sum(r["network_loss_musd"] for r in prow)
    rel = lambda a, b: round((b - a) / a, 4) if a > 1e-9 else None  # noqa: E731
    return dict(
        location_only_loss_musd=round(loc_total, 3), network_aware_loss_musd=round(net_total, 3),
        absolute_difference_musd=round(net_total - loc_total, 3), relative_difference=rel(loc_total, net_total),
        portfolio_location_loss_musd=round(pl, 3), portfolio_network_loss_musd=round(pn, 3),
        portfolio_absolute_difference_musd=round(pn - pl, 3), portfolio_relative_difference=rel(pl, pn),
        portfolio_rows=prow, hidden_exposure_count=sum(r["hidden_exposure"] for r in prow),
        scope_note=("Location-only = direct losses at exposed facilities. Network-aware = direct + modelled indirect losses through "
                    "supply links. Portfolio = 18 equal-weight SYNTHETIC holdings. Both are model outputs under stated assumptions; "
                    "no study has validated this comparison end-to-end."))
