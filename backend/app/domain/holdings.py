"""Holdings as companies: a listed holding can own several business units (segments) and businesses outside the F&B scope.

The supply network does not change: every segment is an ordinary entity. For holding h with segments s:

    d_h        = sum_s a_hs d_s            a_hs = share of h's value added in segment s; sum_s a_hs = 1 - o_h
    upper_h    = d_h / (1 - o_h)           o_h  = share outside Food & Beverage: NOT modelled, adds no loss to d_h;
                                                  upper_h treats it as if it were hit like the modelled part
    one_node_h = 1 - prod_s (1 - d_s)      what a company-level supply graph implies: any segment's shortfall stops the company
    P(e)       = sum_h W_h d_h(e) T(e)/365 = (d(e) . A^T W) T(e)/365

so spreading each company's weight over its segments (w = A^T W) makes every existing `disruption @ w` company-aware.
View "business_unit" treats every held unit as its own holding (one segment, share 1): the v0.3 portfolio exactly.
Company structures are SYNTHETIC (backend/data/companies.json, written by the generator).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ..schemas.domain import Entity
from ..schemas.scenario import HoldingView

if TYPE_CHECKING:
    from .dataset import FnbDataset

VIEWS: tuple[str, ...] = ("company", "business_unit")
__all__ = ["HoldingView", "VIEWS", "Segment", "Holding", "HoldingMatrix", "Holdings", "build_holdings", "units_holdings", "holding_meta",
           "validate_companies"]


@dataclass(frozen=True)
class Segment:
    entity_id: str
    name: str
    label: str
    share: float                 # share of the company's total value added (segments + other businesses = 1)


@dataclass(frozen=True)
class Holding:
    id: str
    name: str
    weight: float
    segments: tuple[Segment, ...]
    other_share: float = 0.0     # share of value added outside the F&B scope (not modelled)
    pattern: str | None = None

    @property
    def multi_segment(self) -> bool:
        return len(self.segments) > 1 or self.other_share > 0

    @property
    def kind(self) -> str:
        return "multi_segment" if self.multi_segment else "single_business"

    @property
    def primary_entity_id(self) -> str:
        return max(self.segments, key=lambda s: s.share).entity_id


@dataclass
class HoldingMatrix:
    """Holdings compiled against one network's node order."""
    A: np.ndarray                # (H, N) value-added shares
    W: np.ndarray                # (H,) position weights
    modelled: np.ndarray         # (H,) 1 - other share
    cols: list[np.ndarray]       # segment node indices per holding

    @property
    def w(self) -> np.ndarray:
        """(N,) entity weight vector: each holding's weight spread over its segments."""
        return self.A.T @ self.W

    def segment_weighted(self, D: np.ndarray) -> np.ndarray:
        return D @ self.A.T

    def if_other_hit(self, D: np.ndarray) -> np.ndarray:
        return self.segment_weighted(D) / np.maximum(self.modelled, 1e-12)

    def one_node(self, D: np.ndarray) -> np.ndarray:
        out = np.empty(D.shape[:-1] + (len(self.cols),))
        for h, c in enumerate(self.cols):
            out[..., h] = 1.0 - np.prod(1.0 - D[..., c], axis=-1)
        return out


@dataclass
class Holdings:
    view: str
    holdings: list[Holding]

    @property
    def owned(self) -> set[str]:
        """Entity ids of every segment of every held company (its own sites)."""
        return {s.entity_id for h in self.holdings for s in h.segments}

    def entity_weights(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for h in self.holdings:
            for s in h.segments:
                out[s.entity_id] = out.get(s.entity_id, 0.0) + h.weight * s.share
        return out

    def compile(self, idx: dict[str, int], n: int) -> HoldingMatrix:
        A = np.zeros((len(self.holdings), n))
        for k, h in enumerate(self.holdings):
            for s in h.segments:
                A[k, idx[s.entity_id]] += s.share
        return HoldingMatrix(A, np.array([h.weight for h in self.holdings]), np.array([1.0 - h.other_share for h in self.holdings]),
                             [np.array([idx[s.entity_id] for s in h.segments], dtype=int) for h in self.holdings])

    @property
    def n_multi_segment(self) -> int:
        return sum(h.multi_segment for h in self.holdings)


def unit_label(e: Entity) -> str:
    return (e.output_product or e.entity_type).replace("_", " ")


def unit_holding(e: Entity, weight: float) -> Holding:
    return Holding(e.id, e.name, weight, (Segment(e.id, e.name, unit_label(e), 1.0),))


def units_holdings(entities: list[Entity], weights: dict[str, float]) -> Holdings:
    """Business-unit view from plain entity weights (as given, not renormalised), in entity order."""
    return Holdings("business_unit", [unit_holding(e, weights[e.id]) for e in entities if e.id in weights])


def company_holding(ds: "FnbDataset", c: dict, weight: float) -> Holding:
    other = float(c.get("other_businesses_share", 0.0))
    segs = c["segments"]
    va = [ds.by_id[s["entity_id"]].value_added_musd for s in segs]
    tot = sum(va)
    shares = [(x / tot if tot > 0 else 1.0 / len(segs)) * (1.0 - other) for x in va]
    return Holding(c["id"], c["name"], weight,
                   tuple(Segment(s["entity_id"], ds.by_id[s["entity_id"]].name, s.get("segment") or unit_label(ds.by_id[s["entity_id"]]), sh)
                         for s, sh in zip(segs, shares)), other, c.get("pattern"))


def build_holdings(ds: "FnbDataset", weights: dict[str, float] | None = None, view: str = "company") -> Holdings:
    """Holdings for a weights dict (default: the synthetic demo portfolio). Keys are entity ids or, in the company view,
    company ids. In the company view each entity key counts towards the company that owns it, so the same money stays in
    the same place; weights are normalised to sum to 1."""
    if view not in VIEWS:
        raise ValueError(f"holding_view must be one of {list(VIEWS)}")
    raw = dict(ds.portfolio_weights if weights is None else weights)
    unknown = [k for k in raw if k not in ds.by_id and not (view == "company" and k in ds.company_by_id)]
    if unknown:
        hint = " (company ids need holding_view='company')" if any(k in ds.company_by_id for k in unknown) else ""
        raise ValueError(f"unknown holdings in weights: {unknown[:5]}{hint}")
    pos = {k: float(v) for k, v in raw.items() if v > 0}
    tot = sum(pos.values())
    if tot <= 0:
        raise ValueError("weights must be non-negative with a positive sum")
    if view == "business_unit":
        return Holdings("business_unit", [unit_holding(ds.by_id[k], v / tot) for k, v in pos.items()])
    agg: dict[str, float] = {}
    for k, v in pos.items():
        cid = k if k in ds.company_by_id else ds.company_of.get(k, k)
        agg[cid] = agg.get(cid, 0.0) + v / tot
    return Holdings("company", [company_holding(ds, ds.company_by_id[cid], v) if cid in ds.company_by_id else unit_holding(ds.by_id[cid], v)
                                for cid, v in agg.items()])


def holding_meta(ds: "FnbDataset", h: Holding) -> dict:
    """Static description of a holding for API payloads (no scenario values)."""
    p = ds.by_id[h.primary_entity_id]
    out = dict(entity_id=h.id, name=h.name, weight=round(h.weight, 6), entity_type=p.entity_type, country=p.country, kind=h.kind,
               primary_entity_id=h.primary_entity_id)
    if h.multi_segment:
        out.update(other_businesses_share=h.other_share, pattern=h.pattern,
                   segments=[dict(entity_id=s.entity_id, name=s.name, segment=s.label, share=round(s.share, 4),
                                  entity_type=ds.by_id[s.entity_id].entity_type, country=ds.by_id[s.entity_id].country) for s in h.segments])
    return out


def validate_companies(companies: list[dict], by_id: dict[str, Entity]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    owner: dict[str, str] = {}
    for c in companies:
        cid = c.get("id")
        if not cid or cid in ids:
            errors.append(f"company '{cid}': missing or duplicate id")
        ids.add(cid)
        if cid in by_id:
            errors.append(f"company '{cid}': id collides with an entity id")
        other = c.get("other_businesses_share", 0.0)
        if not isinstance(other, (int, float)) or not 0 <= other <= 0.95:
            errors.append(f"company '{cid}': other_businesses_share must be within [0, 0.95]")
        segs = c.get("segments") or []
        if not segs:
            errors.append(f"company '{cid}': no segments")
        for s in segs:
            eid = s.get("entity_id")
            if eid not in by_id:
                errors.append(f"company '{cid}': unknown segment entity '{eid}'")
                continue
            if by_id[eid].entity_type == "financial":
                errors.append(f"company '{cid}': financial entity '{eid}' cannot be a segment")
            if eid in owner:
                errors.append(f"entity '{eid}' belongs to two companies ('{owner[eid]}' and '{cid}')")
            owner[eid] = cid
    return errors
