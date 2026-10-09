"""All HTTP routes (kept in one module per resource group; business logic lives in services/ and models/)."""
from __future__ import annotations

import math
import uuid
from collections import Counter
from typing import Literal, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..db import ScenarioRow, session
from ..models import analytics, backtest
from ..models.climate import HAZARD_PARAMS, PROVIDERS
from ..models.mitigation import candidate_interventions, evaluate_interventions
from ..schemas.domain import Entity, EntityDetail
from ..schemas.mitigation import MitigationRequest
from ..schemas.results import Comparison, CriticalPath, EntityImpact, MonteCarloResult, RunResult
from ..schemas.scenario import RunOptions, ScenarioRecord, ScenarioSpec
from ..services import report, scenarios as sc
from ..services.runner import execute
from ..services.state import get_state

system = APIRouter(tags=["system"])
graph = APIRouter(prefix="/api/v1", tags=["graph and entities"])
scen = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])
ana = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
mit = APIRouter(prefix="/api/v1/mitigation", tags=["mitigation"])
dat = APIRouter(prefix="/api/v1/data", tags=["data provenance"])


# ------------------------------------------------------------------ system
@system.get("/health")
def health() -> dict:
    st = get_state()
    return {"status": "ok", "version": __version__, "dataset_valid": st.dataset.validation.ok,
            "entities": len(st.dataset.entities), "relations": len(st.dataset.relations)}


@system.get("/api/v1/metadata")
def metadata() -> dict:
    st = get_state()
    return {
        "name": "FIN-04 Climate Exposure Graph", "version": __version__, "domain": "food_and_beverage",
        "domain_note": "Food & Beverage only. All data in this release is synthetic demonstration data.",
        "n_entities": len(st.dataset.entities), "n_relations": len(st.dataset.relations),
        "entity_types": sorted({e.entity_type for e in st.dataset.entities}),
        "food_categories": sorted({e.food_category for e in st.dataset.entities}),
        "countries": sorted({e.country for e in st.dataset.entities if e.country}),
        "hazards": [{"hazard_type": k, **v} for k, v in HAZARD_PARAMS.items()],
        "hazard_providers": [p.describe() for p in PROVIDERS.values()],
        "unavailable_integrations": ["World Bank CCKP (not integrated)", "Open-Meteo climate/flood APIs (not integrated)"],
        "model_status": {"calibrated": False, "validated": False, "note": "Not calibrated or validated against observed events."},
        "dataset_manifest_version": st.dataset.manifest.get("version"),
    }


# ------------------------------------------------------------------ graph & entities
@graph.get("/graph")
def get_graph(include_financial: bool = True) -> dict:
    ds = get_state().dataset
    nodes = [e.model_dump(include={"id", "name", "entity_type", "food_category", "output_product", "country", "region", "latitude", "longitude",
                                    "synthetic", "operational_criticality", "value_added_musd", "inventory_days", "confidence", "in_demo_portfolio"}) for e in ds.entities]
    edges = [r.model_dump(exclude={"provenance"}) for r in ds.relations if include_financial or r.channel == "supply"]
    return {"nodes": nodes, "edges": edges, "n_nodes": len(nodes), "n_edges": len(edges),
            "edge_semantics": "Directed supplier -> customer. 'dependency' = share of the customer's input of that product (not money).",
            "structure": analytics.graph_structure(ds.entities, ds.relations)}


@graph.get("/entities")
def list_entities(q: Optional[str] = Query(None, max_length=80), entity_type: Optional[str] = None, food_category: Optional[str] = None,
                  country: Optional[str] = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict:
    ents = get_state().dataset.entities
    if q:
        ql = q.lower()
        ents = [e for e in ents if ql in e.name.lower() or ql in e.id.lower() or ql in (e.output_product or "") or ql in (e.region or "").lower() or ql in (e.country or "").lower()]
    if entity_type:
        ents = [e for e in ents if e.entity_type == entity_type]
    if food_category:
        ents = [e for e in ents if e.food_category == food_category]
    if country:
        ents = [e for e in ents if e.country == country]
    total = len(ents)
    items = ents[(page - 1) * page_size: page * page_size]
    return {"total": total, "page": page, "page_size": page_size, "items": [e.model_dump() for e in items]}


def _entity(entity_id: str) -> Entity:
    e = get_state().dataset.by_id.get(entity_id)
    if e is None:
        raise HTTPException(404, f"entity '{entity_id}' not found")
    return e


@graph.get("/entities/{entity_id}", response_model=EntityDetail)
def get_entity(entity_id: str) -> EntityDetail:
    ds = get_state().dataset
    e = _entity(entity_id)
    ins = [r for r in ds.relations if r.target == entity_id and r.channel == "supply"]
    outs = [r for r in ds.relations if r.source == entity_id and r.channel == "supply"]
    shares: dict[str, list[float]] = {}
    for r in ins:
        shares.setdefault(r.product, []).append(r.dependency)
    hhi = None
    if ins:
        tot = sum(r.dependency for r in ins)
        hhi = round(sum((r.dependency / tot) ** 2 for r in ins), 4)
    single = sorted(p for p, v in shares.items() if len(v) == 1 and v[0] >= 0.6)
    return EntityDetail(**e.model_dump(), in_degree=len(ins), out_degree=len(outs), supplier_concentration_hhi=hhi,
                        single_source_inputs=single, missing_fields=ds.missing_fields(e))


@graph.get("/entities/{entity_id}/dependencies")
def entity_dependencies(entity_id: str, depth: int = Query(3, ge=1, le=6)) -> dict:
    ds = get_state().dataset
    _entity(entity_id)
    nb = analytics.neighbours(ds.entities, ds.relations, entity_id, depth)
    brief = lambda r, other: {  # noqa: E731
        "relation_id": r.id, "entity_id": other, "name": ds.by_id[other].name, "product": r.product, "dependency": r.dependency,
        "input_specificity": r.input_specificity, "substitutability": r.substitutability, "lead_time_days": r.lead_time_days,
        "status": r.status, "confidence": r.confidence, "channel": r.channel}
    suppliers = [brief(r, r.source) for r in ds.relations if r.target == entity_id]
    customers = [brief(r, r.target) for r in ds.relations if r.source == entity_id]
    return {"entity_id": entity_id, "suppliers": suppliers, "customers": customers,
            "upstream_hops": nb["upstream_hops"], "downstream_hops": nb["downstream_hops"],
            "n_upstream": len(nb["upstream_hops"]), "n_downstream": len(nb["downstream_hops"])}


@graph.get("/entities/{entity_id}/impact")
def entity_impact(entity_id: str, scenario_id: str = sc.DEFAULT_SCENARIO_ID) -> dict:
    ds = get_state().dataset
    _entity(entity_id)
    sid, spec = sc.resolve(scenario_id, None)
    res = sc.run(spec, sid)
    row = next(r for r in res.entities if r.entity_id == entity_id)
    ex = execute(ds.entities, ds.relations, spec)
    net = ex.net
    i = net.idx[entity_id]
    inc = []
    for k in range(net.m):
        if net.tgt[k] == i:
            u = int(net.src[k])
            inc.append({"supplier_id": net.node_ids[u], "supplier": ds.entities[u].name, "product": net.relations[k].product,
                        "supplier_disruption": round(float(ex.final[u]), 4), "transmission": round(float(ex.trans[k]), 4),
                        "passed_shock": round(float(ex.final[u] * ex.trans[k]), 4), "dependency": net.relations[k].dependency})
    inc.sort(key=lambda x: -x["passed_shock"])
    sys_rows = analytics.systemic_scores(ds.entities, ds.relations, ex.d0)
    srow = next(s for s in sys_rows if s["entity_id"] == entity_id)
    paths = [p for p in res.critical_paths if p.terminal_id == entity_id]
    if not paths:
        full = analytics.dominant_paths(net, ex.trans, ex.d0, {e.id: e.name for e in ds.entities},
                                        {r.entity_id: r.total_loss_musd for r in res.entities}, top=len(ds.entities))
        paths = [p for p in full if p["terminal_id"] == entity_id]
    return {"scenario_id": sid, "impact": row, "incoming_transmission": inc, "systemic": srow, "dominant_paths": paths}


# ------------------------------------------------------------------ scenarios
@scen.get("")
def list_scenarios() -> dict:
    with session() as s:
        rows = s.query(ScenarioRow).order_by(ScenarioRow.builtin.desc(), ScenarioRow.created_at).all()
    return {"items": [sc.record_from_row(r) for r in rows], "total": len(rows)}


@scen.post("", response_model=ScenarioRecord, status_code=201)
def create_scenario(spec: ScenarioSpec) -> ScenarioRecord:
    return sc.save_scenario(spec, "sc_" + uuid.uuid4().hex[:10])


@scen.get("/{scenario_id}", response_model=ScenarioRecord)
def get_scenario(scenario_id: str) -> ScenarioRecord:
    return sc.load_record(scenario_id)


@scen.post("/{scenario_id}/run", response_model=RunResult)
def run_scenario(scenario_id: str, options: RunOptions = RunOptions()) -> RunResult:
    sid, spec = sc.resolve(scenario_id, None)
    return sc.run(spec, sid, options.max_depth, options.top_paths)


@scen.get("/{scenario_id}/report")
def scenario_report(scenario_id: str, format: Literal["md", "csv"] = "md", include_monte_carlo: bool = False,
                    n_simulations: Optional[int] = Query(None, ge=20, le=5000), seed: Optional[int] = Query(None, ge=0)) -> PlainTextResponse:
    sid, spec = sc.resolve(scenario_id, None)
    res = sc.run(spec, sid)
    if format == "csv":
        return PlainTextResponse(report.to_csv(res), media_type="text/csv")
    mc = sc.monte_carlo(spec, n_simulations or spec.monte_carlo_runs or 500, seed if seed is not None else spec.monte_carlo_seed) if include_monte_carlo else None
    return PlainTextResponse(report.to_markdown(res, mc), media_type="text/markdown")


# ------------------------------------------------------------------ analysis
class PropagationRequest(sc.ScenarioRef):
    max_depth: Optional[int] = Field(default=None, ge=1, le=10)
    top_paths: int = Field(default=10, ge=0, le=50)


class MonteCarloRequest(sc.ScenarioRef):
    n_simulations: Optional[int] = Field(default=None, ge=20, le=5000)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    max_depth: Optional[int] = Field(default=None, ge=1, le=10)


@ana.post("/propagation", response_model=RunResult)
def propagation(req: PropagationRequest) -> RunResult:
    sid, spec = sc.resolve(req.scenario_id, req.scenario)
    return sc.run(spec, sid, req.max_depth, req.top_paths)


@ana.post("/monte-carlo", response_model=MonteCarloResult)
def monte_carlo(req: MonteCarloRequest) -> MonteCarloResult:
    sid, spec = sc.resolve(req.scenario_id, req.scenario)
    return sc.monte_carlo(spec, req.n_simulations or spec.monte_carlo_runs or 500, req.seed if req.seed is not None else spec.monte_carlo_seed, req.max_depth)


@ana.post("/network-vs-location", response_model=Comparison)
def network_vs_location(req: sc.ScenarioRef) -> Comparison:
    sid, spec = sc.resolve(req.scenario_id, req.scenario)
    return sc.run(spec, sid).comparison


@ana.get("/systemic-risk")
def systemic_risk(scenario_id: Optional[str] = None, limit: int = Query(25, ge=1, le=200)) -> dict:
    ds = get_state().dataset
    d0, sid = None, None
    if scenario_id:
        sid, spec = sc.resolve(scenario_id, None)
        d0 = execute(ds.entities, ds.relations, spec).d0
    rows = analytics.systemic_scores(ds.entities, ds.relations, d0)
    return {"scenario_id": sid, "weights": analytics.DEFAULT_WEIGHTS, "component_descriptions": analytics.COMPONENT_DESCRIPTIONS,
            "interpretation": "A 0-100 ranking aid built from normalised components. It is not a probability or a monetary loss, and centrality alone is not climate risk.",
            "total": len(rows), "rows": rows[:limit], "structure": analytics.graph_structure(ds.entities, ds.relations)}


@ana.get("/critical-paths", response_model=list[CriticalPath])
def critical_paths(scenario_id: str = sc.DEFAULT_SCENARIO_ID, top: int = Query(10, ge=1, le=50)) -> list[CriticalPath]:
    sid, spec = sc.resolve(scenario_id, None)
    return sc.run(spec, sid, None, top).critical_paths


class BacktestRequest(sc.ScenarioRef):
    observed: dict[str, float] = Field(default_factory=dict, max_length=500, description="entity_id -> observed disruption fraction (0-1)")
    use_synthetic_demo: bool = False


@ana.post("/backtest")
def run_backtest(req: BacktestRequest) -> dict:
    sid, spec = sc.resolve(req.scenario_id, req.scenario)
    sim = {r.entity_id: r.final_disruption for r in sc.run(spec, sid).entities}
    if req.use_synthetic_demo:
        obs, label = backtest.synthetic_demo(sim), "SYNTHETIC DEMONSTRATION: pseudo-observations derived from the model itself. Circular; this is NOT validation."
    else:
        bad = [k for k in req.observed if k not in sim]
        if bad:
            raise HTTPException(422, f"unknown entity ids in observed: {bad[:5]}")
        if any(not (0 <= v <= 1) for v in req.observed.values()):
            raise HTTPException(422, "observed disruption fractions must be within [0,1]")
        obs, label = req.observed, "User-supplied observations."
    return {"label": label, "scenario_id": sid, **backtest.evaluate(sim, obs)}


# ------------------------------------------------------------------ mitigation
@mit.post("/compare")
def mitigation_compare(req: MitigationRequest) -> dict:
    sid, spec = sc.resolve(req.scenario_id, req.scenario)
    ids = set(get_state().dataset.by_id)
    for iv in req.interventions:
        bad = [i for i in iv.entity_ids if i not in ids]
        if bad:
            raise HTTPException(422, f"unknown entity ids in intervention: {bad}")
    ds = get_state().dataset
    out = evaluate_interventions(ds.entities, ds.relations, spec, req.interventions, req.annual_event_probability, req.horizon_years)
    return {"scenario_id": sid, **out}


@mit.get("/recommendations")
def mitigation_recommendations(scenario_id: str = sc.DEFAULT_SCENARIO_ID, top: int = Query(8, ge=1, le=30),
                               annual_event_probability: float = Query(0.10, gt=0, le=1)) -> dict:
    sid, spec = sc.resolve(scenario_id, None)
    ds = get_state().dataset

    def compute():
        res = sc.run(spec, sid)
        cands = candidate_interventions(ds.entities, [r.model_dump() for r in res.entities])
        return evaluate_interventions(ds.entities, ds.relations, spec, cands[:24], annual_event_probability, 10)

    out = get_state().cache.get_or_set(f"rec:{sid}:{annual_event_probability}", compute)
    return {"scenario_id": sid, **{**out, "options": out["options"][:top]}, "candidates_evaluated": len(out["options"])}


# ------------------------------------------------------------------ data provenance
@dat.get("/sources")
def data_sources() -> dict:
    m = get_state().dataset.manifest
    return {**m, "reference_audit": get_state().dataset.reference_audit}


@dat.get("/quality")
def data_quality() -> dict:
    ds = get_state().dataset
    ents, rels = ds.entities, ds.relations
    n = len(ents)
    missing = Counter()
    for e in ents:
        for f in ds.missing_fields(e):
            missing[f] += 1
    groups: dict[tuple, float] = {}
    for r in rels:
        if r.channel == "supply":
            groups[(r.target, r.product)] = groups.get((r.target, r.product), 0.0) + r.dependency
    cov = float(np.mean(list(groups.values()))) if groups else 0.0
    inputs_with_suppliers = len({t for t, _ in groups})
    supply_targets = len({e.id for e in ents if e.entity_type not in ("agricultural_producer", "utility", "financial")})
    v = ds.validation
    return {
        "entities": n, "relations": len(rels), "synthetic_entities": sum(e.synthetic for e in ents),
        "observed_entities": sum(not e.synthetic for e in ents),
        "relations_by_status": dict(Counter(r.status for r in rels)), "relations_by_channel": dict(Counter(r.channel for r in rels)),
        "synthetic_relation_share": sum(r.status in ("synthetic", "modelled") for r in rels) / max(len(rels), 1),
        "entities_by_type": dict(Counter(e.entity_type for e in ents)), "entities_by_confidence": dict(Counter(e.confidence for e in ents)),
        "missing_field_counts": dict(missing), "missing_field_share": {k: round(c / n, 3) for k, c in missing.items()},
        "coordinates_available_share": round(sum(e.latitude is not None for e in ents) / n, 3),
        "mean_modelled_supplier_share_per_input": round(cov, 3),
        "unmodelled_supplier_share_per_input": round(1 - cov, 3),
        "inputs_with_modelled_suppliers": inputs_with_suppliers, "non_agricultural_entities": supply_targets,
        "mean_relation_confidence": round(float(np.mean([r.confidence for r in rels])), 3),
        "validation": {"ok": v.ok, "errors": v.errors, "warnings": v.warnings[:30], "cycles": v.cycles, "isolated_nodes": v.isolated_nodes},
        "structure": analytics.graph_structure(ents, rels),
        "notes": ["Every entity and relationship is synthetic; coordinates are approximate synthetic locations.",
                  "Unmodelled share = portion of each input assumed to come from suppliers outside the graph."],
    }
