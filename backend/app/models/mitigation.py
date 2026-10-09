"""Mitigation interventions, capacity-limited alternative sourcing, synthetic cost model and prioritisation."""
from __future__ import annotations

import copy
from collections import defaultdict

import numpy as np

from ..schemas.domain import Entity, Relation
from ..schemas.mitigation import Intervention
from ..schemas.scenario import ScenarioSpec
from ..services.runner import execute
from .climate import haversine_km

DEFAULT_MAGNITUDE = {"inventory_buffer": 14.0, "supplier_diversification": 0.5, "input_substitution": 0.2,
                     "facility_protection": 0.4, "cold_chain_resilience": 0.4, "relocate_storage": 0.85}
LABEL = {"inventory_buffer": "Increase inventory buffers", "supplier_diversification": "Diversify suppliers (capacity-limited)",
         "input_substitution": "Qualify substitute inputs", "facility_protection": "Protect exposed facilities",
         "cold_chain_resilience": "Improve cold-chain resilience", "relocate_storage": "Relocate critical storage"}
# SYNTHETIC cost placeholders (configurable): time to implement (months), feasibility 0-1, confidence in the *estimate* 0-1.
COST_PARAMS = {
    "inventory_buffer": dict(months=3, feasibility=0.85, confidence=0.60),
    "supplier_diversification": dict(months=9, feasibility=0.60, confidence=0.45),
    "input_substitution": dict(months=12, feasibility=0.50, confidence=0.40),
    "facility_protection": dict(months=18, feasibility=0.70, confidence=0.45),
    "cold_chain_resilience": dict(months=8, feasibility=0.80, confidence=0.50),
    "relocate_storage": dict(months=24, feasibility=0.40, confidence=0.40),
}
CARRY_RATE = 0.12          # annual inventory carrying cost rate
ASSET_LIFE_YEARS = 10.0
PRIORITY_WEIGHTS = {"benefit": 0.35, "benefit_cost_ratio": 0.25, "feasibility": 0.15, "speed": 0.10, "confidence": 0.15}


def default_targets(itype: str, entities: list[Entity]) -> list[str]:
    if itype == "cold_chain_resilience":
        return [e.id for e in entities if e.entity_type in ("cold_storage", "transport_operator")]
    if itype == "relocate_storage":
        return [e.id for e in entities if e.entity_type in ("cold_storage", "distribution_centre")]
    return []


def apply_interventions(entities: list[Entity], relations: list[Relation], ivs: list[Intervention], d0: np.ndarray,
                        id_index: dict[str, int]) -> tuple[list[Entity], list[Relation], list[dict]]:
    ents = {e.id: e.model_copy() for e in entities}
    rels = [r.model_copy() for r in relations]
    notes: list[dict] = []
    spare: dict[str, float] = {}
    for e in entities:
        spare[e.id] = e.revenue_musd * e.spare_capacity_fraction * max(0.0, 1 - float(d0[id_index[e.id]]) * 2)  # hit suppliers cannot help
    for iv in ivs:
        mag = DEFAULT_MAGNITUDE[iv.type] if iv.magnitude is None else iv.magnitude
        targets = [t for t in (iv.entity_ids or default_targets(iv.type, entities)) if t in ents]
        if iv.type == "inventory_buffer":
            for t in targets:
                ents[t].inventory_days = min(365.0, ents[t].inventory_days + mag)
        elif iv.type == "input_substitution":
            for r in rels:
                if r.target in targets and r.channel == "supply":
                    r.substitutability = min(0.95, r.substitutability + min(mag, 0.9))
        elif iv.type in ("facility_protection", "cold_chain_resilience", "relocate_storage"):
            f = 1 - min(mag, 0.95)
            for t in targets:
                for a in ("flood_vulnerability", "heat_vulnerability", "drought_vulnerability"):
                    setattr(ents[t], a, getattr(ents[t], a) * f)
        elif iv.type == "supplier_diversification":
            new_edges: list[Relation] = []
            for t in targets:
                for r in [x for x in rels if x.target == t and x.channel == "supply" and x.status != "modelled"]:
                    want = r.annual_flow_musd * min(mag, 1.0)
                    src_country = ents[r.source].country
                    # non-storable goods/services (power, cold storage, perishables) cannot be re-sourced across countries
                    cands = [(w, spare[w]) for w, e in ents.items() if w not in (r.source, t) and e.output_product == r.product and spare[w] > 1e-6
                             and (r.storable or e.country == src_country)]
                    cap = sum(s for _, s in cands)
                    if want <= 1e-9 or cap <= 1e-9:
                        notes.append(dict(target=t, product=r.product, note="no spare alternative capacity", shifted_musd=0.0))
                        continue
                    moved = min(want, cap)
                    frac = moved / r.annual_flow_musd
                    r.dependency = r.dependency * (1 - frac)
                    for w, s in cands:
                        share = s / cap
                        spare[w] -= moved * share
                        dep_add = r.dependency / (1 - frac) * frac * share
                        existing = next((x for x in rels + new_edges if x.source == w and x.target == t and x.product == r.product), None)
                        if existing:
                            existing.dependency = min(1.0, existing.dependency + dep_add)
                            continue
                        ws, ts = ents[w], ents[t]
                        dist = haversine_km(ws.latitude, ws.longitude, np.array([ts.latitude]), np.array([ts.longitude]))[0] if (ws.latitude is not None and ts.latitude is not None) else 5000.0
                        lead = 0.0 if not r.storable else (2.0 if ws.country == ts.country else min(45.0, 7 + dist / 800))
                        new_edges.append(Relation(id=f"{w}->{t}", source=w, target=t, product=r.product, channel="supply",
                                                  relationship_type=r.relationship_type, dependency=min(1.0, dep_add),
                                                  input_specificity=r.input_specificity, substitutability=r.substitutability, storable=r.storable,
                                                  lead_time_days=round(lead, 1), annual_flow_musd=round(moved * share, 3), status="modelled",
                                                  confidence=0.3, provenance="MODELLED by mitigation scenario: hypothetical relationship, not existing"))
                    notes.append(dict(target=t, product=r.product, note="capacity-limited" if moved < want - 1e-9 else "fully shifted", shifted_musd=round(moved, 3)))
            rels.extend(new_edges)
    return [ents[e.id] for e in entities], rels, notes


def cost_of(iv: Intervention, entities: list[Entity], relations: list[Relation], notes: list[dict]) -> dict:
    p = COST_PARAMS[iv.type]
    by = {e.id: e for e in entities}
    mag = DEFAULT_MAGNITUDE[iv.type] if iv.magnitude is None else iv.magnitude
    targets = [t for t in (iv.entity_ids or default_targets(iv.type, entities)) if t in by]
    capex = opex = 0.0
    if iv.type == "inventory_buffer":
        for t in targets:
            inflow = sum(r.annual_flow_musd for r in relations if r.target == t and r.channel == "supply" and r.storable)
            opex += inflow / 365.0 * mag * CARRY_RATE
    elif iv.type == "supplier_diversification":
        shifted = sum(n["shifted_musd"] for n in notes)
        capex = 0.8 * sum(1 for n in notes if n["shifted_musd"] > 0)
        opex = 0.03 * shifted
    elif iv.type == "input_substitution":
        capex = 1.5 * len(targets)
    elif iv.type in ("facility_protection", "cold_chain_resilience"):
        k = 0.30 if iv.type == "facility_protection" else 0.25
        capex = sum(min(mag, 0.95) * k * by[t].value_added_musd + 0.4 for t in targets)
        opex = 0.02 * capex
    elif iv.type == "relocate_storage":
        capex = sum(0.6 * by[t].revenue_musd * min(1.0, mag) for t in targets)
        opex = 0.02 * capex
    annual = capex / ASSET_LIFE_YEARS + opex
    return dict(capex_musd=round(capex, 3), annual_opex_musd=round(opex, 3), annualised_cost_musd=round(annual, 3),
                time_months=p["months"], feasibility=p["feasibility"], estimate_confidence=p["confidence"],
                basis="SYNTHETIC placeholder cost model (see docs/METHODOLOGY.md); replace with real quotes before use")


def evaluate_interventions(entities: list[Entity], relations: list[Relation], spec: ScenarioSpec, ivs: list[Intervention],
                           probability: float, horizon_years: int, max_depth: int | None = None) -> dict:
    base = execute(entities, relations, spec, max_depth)
    bl_d, bl_t = base.losses()
    bl_dtot, bl_tot = float(bl_d.sum()), float(bl_t.sum())

    def effect(ents, rels):
        ex = execute(ents, rels, spec, max_depth)
        d, t = ex.losses()
        return float(d.sum()), float(t.sum())

    def pack(label, ivs_, itype):
        ents, rels, notes = apply_interventions(entities, relations, ivs_, base.d0, base.net.idx)
        md, mt = effect(ents, rels)
        cost = [cost_of(iv, entities, rels, notes) for iv in ivs_]
        annual_cost = sum(c["annualised_cost_musd"] for c in cost)
        benefit = bl_tot - mt
        annual_benefit = benefit * probability
        bcr = annual_benefit / annual_cost if annual_cost > 1e-9 else None
        return dict(
            label=label, types=[iv.type for iv in ivs_], interventions=[iv.model_dump() for iv in ivs_],
            effect=dict(baseline_loss_musd=round(bl_tot, 3), mitigated_loss_musd=round(mt, 3), loss_reduction_musd=round(benefit, 3),
                        loss_reduction_fraction=round(benefit / bl_tot, 4) if bl_tot > 1e-9 else None, baseline_direct_musd=round(bl_dtot, 3),
                        mitigated_direct_musd=round(md, 3), baseline_indirect_musd=round(bl_tot - bl_dtot, 3), mitigated_indirect_musd=round(mt - md, 3)),
            cost=dict(capex_musd=round(sum(c["capex_musd"] for c in cost), 3), annual_opex_musd=round(sum(c["annual_opex_musd"] for c in cost), 3),
                      annualised_cost_musd=round(annual_cost, 3), time_months=max(c["time_months"] for c in cost),
                      feasibility=round(float(np.prod([c["feasibility"] for c in cost])), 3),
                      estimate_confidence=round(float(np.min([c["estimate_confidence"] for c in cost])), 3), basis=cost[0]["basis"]),
            annual_expected_benefit_musd=round(annual_benefit, 3), benefit_cost_ratio=None if bcr is None else round(bcr, 3),
            bcr_low=None if annual_cost <= 1e-9 else round(benefit * probability * 0.5 / annual_cost, 3),
            bcr_high=None if annual_cost <= 1e-9 else round(benefit * min(1.0, probability * 2) / annual_cost, 3),
            net_present_style_value_musd=round(annual_benefit * horizon_years - annual_cost * horizon_years, 3),
            notes=notes, targets=[sorted(iv.entity_ids) for iv in ivs_])

    options = [pack(iv.label or LABEL[iv.type], [iv], iv.type) for iv in ivs]
    combined = pack("Combined package", ivs, "combined") if len(ivs) > 1 else None
    # transparent composite priority score across single options
    if options:
        mb = max(max(o["effect"]["loss_reduction_musd"], 0) for o in options) or 1.0
        mbcr = max((o["benefit_cost_ratio"] or 0) for o in options) or 1.0
        for o in options:
            comp = dict(benefit=max(o["effect"]["loss_reduction_musd"], 0) / mb, benefit_cost_ratio=(o["benefit_cost_ratio"] or 0) / mbcr,
                        feasibility=o["cost"]["feasibility"], speed=1 / (1 + o["cost"]["time_months"] / 12), confidence=o["cost"]["estimate_confidence"])
            o["priority_components"] = {k: round(v, 3) for k, v in comp.items()}
            o["priority_score"] = round(100 * sum(PRIORITY_WEIGHTS[k] * v for k, v in comp.items()), 2)
        options.sort(key=lambda o: -o["priority_score"])
    return dict(baseline=dict(total_loss_musd=round(bl_tot, 3), direct_loss_musd=round(bl_dtot, 3), indirect_loss_musd=round(bl_tot - bl_dtot, 3)),
                options=options, combined=combined, priority_weights=PRIORITY_WEIGHTS,
                assumptions=[f"Annual event probability {probability:.0%} is an analyst input, not an estimate.",
                             f"Capex annualised over {ASSET_LIFE_YEARS:.0f} years; inventory carrying cost {CARRY_RATE:.0%}/yr.",
                             "Costs, times and feasibility are SYNTHETIC placeholders.",
                             "Alternative sourcing is limited by the spare capacity of unaffected suppliers of the same product.",
                             "Interventions are hypothetical; nothing here has been implemented in the real world."],
                annual_event_probability=probability)


def candidate_interventions(entities: list[Entity], base_rows: list[dict], k: int = 5) -> list[Intervention]:
    """Candidate set for automatic recommendations, derived from where the scenario actually bites."""
    ind = sorted([r for r in base_rows if r["indirect_loss_musd"] > 0], key=lambda r: -r["indirect_loss_musd"])[:k]
    dire = sorted([r for r in base_rows if r["direct_loss_musd"] > 0], key=lambda r: -r["direct_loss_musd"])[:k]
    cands: list[Intervention] = []
    for r in ind:
        cands.append(Intervention(type="inventory_buffer", entity_ids=[r["entity_id"]], magnitude=14, label=f"+14d inventory at {r['name']}"))
        cands.append(Intervention(type="supplier_diversification", entity_ids=[r["entity_id"]], magnitude=0.5, label=f"Diversify suppliers of {r['name']}"))
        cands.append(Intervention(type="input_substitution", entity_ids=[r["entity_id"]], magnitude=0.2, label=f"Qualify substitute inputs at {r['name']}"))
    types = {e.id: e.entity_type for e in entities}
    for r in dire:
        if types[r["entity_id"]] in ("cold_storage", "distribution_centre"):
            cands.append(Intervention(type="cold_chain_resilience", entity_ids=[r["entity_id"]], magnitude=0.4, label=f"Cold-chain resilience at {r['name']}"))
        cands.append(Intervention(type="facility_protection", entity_ids=[r["entity_id"]], magnitude=0.4, label=f"Protect {r['name']}"))
    seen, out = set(), []
    for c in cands:
        key = (c.type, tuple(c.entity_ids))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
