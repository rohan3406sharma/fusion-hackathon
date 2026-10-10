"""Scenario specification schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

HazardType = Literal["flood", "heat", "drought"]
HoldingView = Literal["company", "business_unit"]     # how a portfolio holding is defined (see domain/holdings.py)


class HazardComponent(BaseModel):
    hazard_type: HazardType
    intensity: float = Field(ge=0, le=1, description="Dimensionless scenario intensity index in [0,1] (synthetic; NOT flood depth, degrees C or rainfall)")
    duration_days: float = Field(ge=1, le=730)
    center_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    center_lon: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_km: Optional[float] = Field(default=None, gt=0, le=5000)
    regions: list[str] = Field(default_factory=list, max_length=50, description="Entity region names fully inside the footprint")
    affected_entity_ids: list[str] = Field(default_factory=list, max_length=200)
    label: str = ""

    @model_validator(mode="after")
    def _locator(self):
        circ = [self.center_lat, self.center_lon, self.radius_km]
        if any(c is not None for c in circ) and not all(c is not None for c in circ):
            raise ValueError("center_lat, center_lon and radius_km must be given together")
        if not (all(c is not None for c in circ) or self.regions or self.affected_entity_ids):
            raise ValueError("hazard needs a footprint (centre+radius), regions, or affected_entity_ids")
        return self


class ScenarioSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    hazards: list[HazardComponent] = Field(min_length=1, max_length=4)
    time_horizon_year: int = Field(default=2035, ge=2020, le=2100)
    data_source: Literal["synthetic_footprint"] = "synthetic_footprint"
    propagation_max_depth: int = Field(default=6, ge=1, le=10)
    inventory_scale: float = Field(default=1.0, ge=0, le=3)
    substitution_scale: float = Field(default=1.0, ge=0, le=2)
    dependency_scale: float = Field(default=1.0, ge=0.25, le=1.5)
    compound_amplification: float = Field(default=0.0, ge=0, le=0.5, description="Analyst-set uplift when >1 hazard overlaps; not an estimate")
    use_graph_alternatives: bool = Field(default=True, description="Relief from modelled same-product producers, limited by their spare capacity and their own disruption")
    cycle_damping: float = Field(default=0.5, ge=0, le=1, description="Multiplier on links inside feedback loops (1 = undamped); an assumption")
    monte_carlo_runs: int = Field(default=500, ge=0, le=5000)
    monte_carlo_seed: int = Field(default=42, ge=0, le=2**31 - 1)


class ScenarioRecord(ScenarioSpec):
    id: str
    builtin: bool = False
    synthetic: bool = True
    created_at: Optional[str] = None


class RunOptions(BaseModel):
    max_depth: Optional[int] = Field(default=None, ge=1, le=10)
    top_paths: int = Field(default=10, ge=0, le=50)
    holding_view: HoldingView = "company"
