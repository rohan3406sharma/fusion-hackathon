"""Dataset loading, validation and graph construction."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from ..schemas.domain import Entity, Relation

log = logging.getLogger(__name__)

OPTIONAL_FIELDS = ["latitude", "longitude", "capacity_tonnes_per_year", "exposed_asset_share", "output_product", "country", "region"]


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    isolated_nodes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_graph_data(entities: list[Entity], relations: list[Relation]) -> ValidationReport:
    """Check IDs, references, duplicates, value ranges, isolated nodes, impossible dependency configurations, cycles."""
    rep = ValidationReport()
    ids = [e.id for e in entities]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        rep.errors.append(f"duplicate entity ids: {sorted(dup)}")
    idset = set(ids)
    seen: set[tuple[str, str, str]] = set()
    group_sum: dict[tuple[str, str], float] = {}
    for r in relations:
        if r.source not in idset:
            rep.errors.append(f"relation {r.id}: unknown source '{r.source}'")
        if r.target not in idset:
            rep.errors.append(f"relation {r.id}: unknown target '{r.target}'")
        if r.source == r.target:
            rep.errors.append(f"relation {r.id}: self-loop")
        key = (r.source, r.target, r.product)
        if key in seen:
            rep.errors.append(f"relation {r.id}: duplicate edge {key}")
        seen.add(key)
        if r.channel == "supply":
            group_sum[(r.target, r.product)] = group_sum.get((r.target, r.product), 0.0) + r.dependency
    for (t, p), s in group_sum.items():
        if s > 1.0 + 1e-9:
            rep.errors.append(f"impossible dependency: shares into '{t}' for product '{p}' sum to {s:.2f} > 1")
    for e in entities:
        if e.value_added_musd > e.revenue_musd + 1e-9:
            rep.errors.append(f"entity {e.id}: value added exceeds revenue")
        if e.latitude is None and e.longitude is None:
            rep.warnings.append(f"entity {e.id}: no coordinates (location_status={e.location_status})")
        elif (e.latitude is None) != (e.longitude is None):
            rep.errors.append(f"entity {e.id}: only one of latitude/longitude set")
    if rep.errors:
        return rep
    g = nx.DiGraph()
    g.add_nodes_from(ids)
    g.add_edges_from((r.source, r.target) for r in relations)
    rep.isolated_nodes = sorted(nx.isolates(g))
    if rep.isolated_nodes:
        rep.warnings.append(f"isolated nodes: {rep.isolated_nodes}")
    sup = nx.DiGraph()
    sup.add_nodes_from(ids)
    sup.add_edges_from((r.source, r.target) for r in relations if r.channel == "supply")
    rep.cycles = [sorted(c) for c in nx.strongly_connected_components(sup) if len(c) > 1]
    for c in rep.cycles:
        rep.warnings.append(
            f"cycle among {c}: kept (feedbacks such as shared cold-chain assets can be real); the propagation "
            "update is monotone and bounded so it terminates at a fixed point or the iteration cap")
    return rep


class FnbDataset:
    def __init__(self, entities: list[Entity], relations: list[Relation], scenarios: list[dict], manifest: dict,
                 reference_audit: dict):
        self.entities = entities
        self.relations = relations
        self.scenarios = scenarios
        self.manifest = manifest
        self.reference_audit = reference_audit
        self.by_id = {e.id: e for e in entities}
        self.validation = validate_graph_data(entities, relations)
        self.hazard_layers: dict[str, dict] = {}
        self.portfolio: dict = {"name": "Demo portfolio", "synthetic": True, "weighting": "equal",
                                "holdings": [{"entity_id": e.id, "weight": 1.0} for e in entities if e.in_demo_portfolio]}
        self.companies_meta: dict = {}
        self.company_by_id: dict[str, dict] = {}
        self.company_of: dict[str, str] = {}        # segment entity id -> company id

    def set_companies(self, payload: dict) -> None:
        """Synthetic company structures (companies.json). Invalid structures are reported as validation errors and ignored,
        so every holding falls back to a single business."""
        from .holdings import validate_companies
        companies = payload.get("companies", [])
        errors = validate_companies(companies, self.by_id)
        self.companies_meta = {k: v for k, v in payload.items() if k != "companies"}
        if errors:
            self.validation.errors.extend(errors)
            return
        self.company_by_id = {c["id"]: c for c in companies}
        self.company_of = {s["entity_id"]: c["id"] for c in companies for s in c["segments"]}

    @property
    def portfolio_weights(self) -> dict[str, float]:
        hs = [h for h in self.portfolio["holdings"] if h["entity_id"] in self.by_id]
        tot = sum(h["weight"] for h in hs) or 1.0
        return {h["entity_id"]: h["weight"] / tot for h in hs}

    @classmethod
    def load(cls, data_dir: Path) -> "FnbDataset":
        ents = [Entity(**d) for d in json.loads((data_dir / "fnb_entities.json").read_text())]
        rels = [Relation(**d) for d in json.loads((data_dir / "fnb_relations.json").read_text())]
        scs = json.loads((data_dir / "scenarios.json").read_text())
        manifest = json.loads((data_dir / "manifest.json").read_text())
        audit_p = data_dir / "reference_audit.json"
        audit = json.loads(audit_p.read_text()) if audit_p.exists() else {"present": False}
        ds = cls(ents, rels, scs, manifest, audit)
        pf = data_dir / "portfolio.json"
        if pf.exists():
            ds.portfolio = json.loads(pf.read_text())
        cp = data_dir / "companies.json"
        if cp.exists():
            ds.set_companies(json.loads(cp.read_text()))
        jrc = data_dir / "hazard_layers" / "jrc_flood_rp100.json"
        if jrc.exists():
            ds.hazard_layers["jrc_flood_rp100"] = json.loads(jrc.read_text())
        log.info("dataset loaded: %d entities, %d relations, valid=%s", len(ents), len(rels), ds.validation.ok)
        return ds

    def supply_relations(self) -> list[Relation]:
        return [r for r in self.relations if r.channel == "supply"]

    def graph(self, channel: str | None = "supply") -> nx.DiGraph:
        g = nx.DiGraph()
        for e in self.entities:
            g.add_node(e.id, **e.model_dump())
        for r in self.relations:
            if channel is None or r.channel == channel:
                g.add_edge(r.source, r.target, **r.model_dump())
        return g

    def missing_fields(self, e: Entity) -> list[str]:
        return [f for f in OPTIONAL_FIELDS if getattr(e, f) is None]
