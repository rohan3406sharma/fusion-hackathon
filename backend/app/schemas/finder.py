"""Schemas for the Hidden Exposure Finder (portfolio reverse stress test) and the resilience optimiser."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .mitigation import Intervention
from .scenario import HazardComponent, HazardType, HoldingView


class FinderRequest(BaseModel):
    hazards: list[HazardType] = Field(default_factory=lambda: ["flood", "heat", "drought"], min_length=1, max_length=3)
    intensity: float = Field(default=0.8, gt=0, le=1, description="Reference intensity index for every event (synthetic)")
    radii_km: list[float] = Field(default_factory=lambda: [150.0, 350.0], min_length=1, max_length=4)
    min_vulnerability: float = Field(default=0.3, ge=0, le=1)
    top_k: int = Field(default=25, ge=5, le=100)
    shortlist: int = Field(default=100, ge=10, le=300, description="Events re-ranked under uncertainty")
    stability_draws: int = Field(default=200, ge=0, le=1000)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    include_pairs: bool = True
    flood_check: Literal["flag", "drop", "off"] = Field(default="flag", description="Use the JRC 100-year river-flood layer to flag or drop flood events with no modelled river flooding near any directly hit entity")
    max_depth: int = Field(default=6, ge=1, le=10)
    weights: Optional[dict[str, float]] = Field(default=None, description="entity_id (or, in the company view, company id) -> position weight; default = synthetic demo portfolio")
    holding_view: HoldingView = Field(default="company", description="'company': a holding is a company whose disruption is the value-added-weighted "
                                      "average of its business units (segments); 'business_unit': every held unit is its own holding (v0.3)")

    @model_validator(mode="after")
    def _radii(self):
        if any(r <= 0 or r > 2000 for r in self.radii_km):
            raise ValueError("radii must be within (0, 2000] km")
        if self.weights is not None and (not self.weights or any(v < 0 for v in self.weights.values()) or sum(self.weights.values()) <= 0):
            raise ValueError("weights must be non-negative with a positive sum")
        return self


class SegmentImpact(BaseModel):
    entity_id: str
    name: str
    segment: str
    share: float = Field(description="Share of the company's value added in this business unit (synthetic)")
    direct_disruption: float
    network_disruption: float


class HoldingImpact(BaseModel):
    entity_id: str = Field(description="Holding id: the entity id of a single-business holding, the company id of a multi-segment company")
    name: str
    weight: float
    direct_disruption: float
    network_disruption: float = Field(description="Company level: value-added-weighted average of its segments' disruption")
    kind: Literal["single_business", "multi_segment"] = "single_business"
    primary_entity_id: Optional[str] = Field(default=None, description="Largest business unit (for links to an entity page)")
    other_businesses_share: Optional[float] = Field(default=None, description="Share of value added outside Food & Beverage; not modelled")
    network_disruption_if_other_hit: Optional[float] = Field(default=None, description="Upper end: as if the non-F&B share were hit like the modelled part")
    network_disruption_one_node: Optional[float] = Field(default=None, description="As one node: any segment's shortfall stops the whole company")
    segments: Optional[list[SegmentImpact]] = None


class FinderEvent(BaseModel):
    rank: int
    id: str
    kind: Literal["node", "footprint"]
    hazard: str
    label: str
    origin_id: Optional[str]
    country: Optional[str]
    region: Optional[str]
    portfolio_network_impact: float = Field(description="Position-weighted share of annual value added lost, network-aware")
    portfolio_location_impact: float = Field(description="Same, location-only (direct damage at holdings' own sites)")
    hidden_share: float = Field(description="1 - location/network")
    hidden_only: bool = Field(description="No holding is hit directly, yet the portfolio loses value through supply links")
    variants: int = Field(description="Near-duplicate events collapsed into this row")
    holdings_affected: int
    entities_hit_directly: int
    top_holdings: list[HoldingImpact]
    p_top5: Optional[float] = Field(default=None, description="Share of uncertainty draws in which the event ranks in the top 5")
    median_rank: Optional[float] = None
    rank_iqr: Optional[list[float]] = None
    fragile: Optional[bool] = Field(default=None, description="p_top5 < 0.5 for an event ranked in the deterministic top 5 of its list")
    hazard_component: HazardComponent
    jrc_flood_check: Optional[str] = Field(default=None, description="Flood events only: whether the JRC 100-year river-flood map shows flooding near a directly hit entity")
    portfolio_network_impact_if_other_hit: Optional[float] = Field(default=None, description="Company view: upper end, non-F&B businesses hit like the modelled part")
    portfolio_network_impact_one_node: Optional[float] = Field(default=None, description="Company view: every company treated as one node")


class MatrixRow(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    worst_event_id: str
    total: float
    holdings_reached: int
    values: dict[str, float]


class SinglePointOfFailure(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    holdings: list[HoldingImpact]
    is_holding: bool


class FinderResult(BaseModel):
    n_events: int
    n_node_events: int
    n_footprint_events: int
    n_distinct_events: int
    n_hidden_only: int = Field(description="Distinct (collapsed) hidden-only events")
    runtime_seconds: float
    events: list[FinderEvent]
    hidden_only_events: list[FinderEvent]
    hidden_share_curve: list[dict]
    holdings: list[dict]
    matrix: list[MatrixRow]
    single_points_of_failure: list[SinglePointOfFailure]
    structural_bound: Optional[dict]
    stability: Optional[dict]
    hazard_layer: Optional[dict] = Field(default=None, description="Real-data plausibility check summary (JRC river flood)")
    holding_view: HoldingView = "company"
    structure_comparison: Optional[dict] = Field(default=None, description="Company view only: the same library scored with holdings as business units, "
                                                 "as companies, with non-F&B businesses hit, and as one node per company")
    parameters: dict
    units: dict[str, str]
    assumptions: list[str]
    limitations: list[str]


class PromoteRequest(BaseModel):
    hazard: HazardComponent
    label: str = Field(min_length=1, max_length=120)
    max_depth: int = Field(default=6, ge=1, le=10)


class OptimiseRequest(BaseModel):
    budget_musd: float = Field(default=5.0, gt=0, le=1000, description="Annualised budget, USD million per year (placeholder costs)")
    finder: FinderRequest = Field(default_factory=lambda: FinderRequest(stability_draws=0, include_pairs=False))
    tail_events: int = Field(default=10, ge=1, le=50, description="Objective = mean impact of the worst N events after the plan")
    candidates: Optional[list[Intervention]] = Field(default=None, max_length=20)
    max_candidates: int = Field(default=14, ge=2, le=20)
    exhaustive_check: bool = False
    robustness_draws: int = Field(default=0, ge=0, le=200)
    seed: int = Field(default=7, ge=0)
