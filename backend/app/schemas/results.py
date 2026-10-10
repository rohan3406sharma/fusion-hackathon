"""Result schemas shared by API and services."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .scenario import ScenarioSpec

EntityStatus = Literal["direct", "propagated", "unaffected"]


class EntityImpact(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    food_category: str
    country: Optional[str]
    region: Optional[str]
    synthetic: bool
    status: EntityStatus
    hazard_intensity: float = Field(description="Max over hazards of intensity x footprint weight (index 0-1)")
    direct_disruption: float = Field(description="Direct operational disruption fraction 0-1 (proxy damage function)")
    final_disruption: float = Field(description="Disruption fraction after propagation 0-1")
    hop_order: Optional[int] = Field(description="0 = direct; k>=1 = first step at which propagated disruption appeared")
    value_added_musd: float
    direct_loss_musd: float
    indirect_loss_musd: float
    total_loss_musd: float
    loss_by_order_musd: dict[str, float]
    evidence_label: str


class Breakdown(BaseModel):
    key: str
    entities: int
    affected: int
    direct_loss_musd: float
    indirect_loss_musd: float
    total_loss_musd: float


class PathHop(BaseModel):
    source: str
    target: str
    product: str
    transmission: float


class CriticalPath(BaseModel):
    origin_id: str
    terminal_id: str
    entity_ids: list[str]
    names: list[str]
    hops: list[PathHop]
    cumulative_transmission: float
    terminal_total_loss_musd: float


class OrderSummary(BaseModel):
    order: str
    label: str
    entities: int
    loss_musd: float
    evidence: str


class RunSummary(BaseModel):
    n_entities: int
    n_exposed_facilities: int
    n_affected_downstream: int
    direct_loss_musd: float
    indirect_loss_musd: float
    total_loss_musd: float
    indirect_to_direct_ratio: Optional[float]
    iterations: int
    converged: bool
    effective_duration_days: float
    loss_period_fraction: float
    max_depth_used: int


class ComparisonRow(BaseModel):
    entity_id: str
    name: str
    location_disruption: float
    network_disruption: float
    location_loss_musd: float
    network_loss_musd: float
    rank_location: float = Field(description="1 = most disrupted; ties share the average rank")
    rank_network: float
    rank_change: float = Field(description="rank_location - rank_network; positive = moves up when network is considered; 0 for holdings unaffected in both views")
    hidden_exposure: bool
    weight: float = Field(description="Synthetic position weight of the holding")
    kind: Literal["single_business", "multi_segment"] = "single_business"
    primary_entity_id: Optional[str] = Field(default=None, description="Largest business unit (for links to an entity page)")
    other_businesses_share: Optional[float] = Field(default=None, description="Share of value added outside Food & Beverage; not modelled")
    network_disruption_if_other_hit: Optional[float] = Field(default=None, description="Upper end: non-F&B share hit like the modelled part")
    network_disruption_one_node: Optional[float] = Field(default=None, description="As one node: any segment's shortfall stops the whole company")
    segments: Optional[list[dict]] = Field(default=None, description="Business units: entity_id, name, segment, share, location/network disruption")


class Comparison(BaseModel):
    location_only_loss_musd: float
    network_aware_loss_musd: float
    absolute_difference_musd: float
    relative_difference: Optional[float]
    portfolio_location_loss_musd: float
    portfolio_network_loss_musd: float
    portfolio_absolute_difference_musd: float
    portfolio_relative_difference: Optional[float]
    portfolio_rows: list[ComparisonRow]
    hidden_exposure_count: int
    portfolio_location_impact: float = Field(description="Position-weighted share of annual value added lost, location-only")
    portfolio_network_impact: float = Field(description="Position-weighted share of annual value added lost, network-aware")
    portfolio_hidden_share: Optional[float] = Field(description="1 - location/network (weighted); null when no network impact")
    hidden_exposure_curve: list[dict] = Field(description="Hidden-exposure count at several propagated-disruption cut-offs")
    scope_note: str
    holding_view: Literal["company", "business_unit"] = "business_unit"
    portfolio_network_impact_if_other_hit: Optional[float] = Field(default=None, description="Company view: upper end, non-F&B businesses hit like the modelled part")
    portfolio_network_impact_one_node: Optional[float] = Field(default=None, description="Company view: every company treated as one node")


class RunResult(BaseModel):
    scenario: ScenarioSpec
    scenario_id: Optional[str]
    summary: RunSummary
    orders: list[OrderSummary]
    entities: list[EntityImpact]
    by_food_category: list[Breakdown]
    by_entity_type: list[Breakdown]
    by_region: list[Breakdown]
    critical_paths: list[CriticalPath]
    comparison: Comparison
    bottlenecks: list[dict]
    assumptions: list[str]
    limitations: list[str]
    units: dict[str, str]


class Quantiles(BaseModel):
    mean: float
    median: float
    p05: float
    p25: float
    p75: float
    p95: float
    min: float
    max: float


class SensitivityItem(BaseModel):
    parameter: str
    spearman_with_total_loss: float
    approx_variance_share: float = Field(default=0.0, description="rho^2 normalised over factors; approximate")
    description: str


class MonteCarloResult(BaseModel):
    n_simulations: int
    seed: int
    total_loss: Quantiles
    direct_loss: Quantiles
    indirect_loss: Quantiles
    network_minus_location: Quantiles
    histogram: list[dict]
    sensitivity: list[SensitivityItem]
    indirect_sensitivity: list[SensitivityItem] = Field(default_factory=list, description="Sensitivity of the indirect (network) loss")
    top_entities: list[dict]
    assumptions: list[str]
    interpretation: str
    deterministic_total_loss_musd: float


class SystemicRow(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    food_category: str
    score: float
    rank: int
    components: dict[str, float] = Field(description="Normalised 0-1 component values")
    contributions: dict[str, float] = Field(description="Points contributed to the 0-100 score")
    in_degree: int
    out_degree: int
    weighted_out_dependency: float
    betweenness: float
    pagerank_dependedness: float
    downstream_reach: int


class MitigationEffect(BaseModel):
    baseline_loss_musd: float
    mitigated_loss_musd: float
    loss_reduction_musd: float
    loss_reduction_fraction: Optional[float]
    baseline_direct_musd: float
    mitigated_direct_musd: float
    baseline_indirect_musd: float
    mitigated_indirect_musd: float
