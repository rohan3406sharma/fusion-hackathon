from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .scenario import ScenarioSpec

InterventionType = Literal["inventory_buffer", "supplier_diversification", "input_substitution", "facility_protection",
                           "cold_chain_resilience", "relocate_storage"]


class Intervention(BaseModel):
    type: InterventionType
    entity_ids: list[str] = Field(default_factory=list, max_length=100,
                                  description="Entities receiving the intervention (as customers for sourcing measures, as facilities for protection)")
    magnitude: Optional[float] = Field(default=None, ge=0, le=365,
                                       description="inventory_buffer: extra days; supplier_diversification: share of each supplier's flow moved (0-1); "
                                                   "input_substitution: substitutability increase (0-0.9); facility_protection / cold_chain_resilience / relocate_storage: vulnerability reduction (0-0.95)")
    label: str = ""


class MitigationRequest(BaseModel):
    scenario_id: Optional[str] = None
    scenario: Optional[ScenarioSpec] = None
    interventions: list[Intervention] = Field(min_length=1, max_length=12)
    annual_event_probability: float = Field(default=0.10, gt=0, le=1, description="Analyst-defined annual probability of the scenario (NOT an estimate)")
    horizon_years: int = Field(default=10, ge=1, le=50)
