"""Entity / relationship schemas for the Food & Beverage graph."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

EntityType = Literal[
    "agricultural_producer", "agricultural_input", "processor", "manufacturer", "packaging_supplier",
    "cold_storage", "transport_operator", "port_hub", "distribution_centre", "wholesaler", "retailer",
    "utility", "financial",
]
Confidence = Literal["low", "medium", "high"]
RelationStatus = Literal["disclosed", "inferred", "synthetic", "modelled"]
Channel = Literal["supply", "financial"]

unit = Field(ge=0.0, le=1.0)


class Entity(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str
    synthetic: bool = True
    entity_type: EntityType
    food_category: str
    output_product: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    location_status: str = "unknown"
    facility_type: Optional[str] = None
    revenue_musd: float = Field(ge=0)
    value_added_musd: float = Field(ge=0)
    capacity_tonnes_per_year: Optional[float] = Field(default=None, ge=0)
    inventory_days: float = Field(ge=0, le=365)
    alternative_supplier_availability: float = unit
    operational_criticality: float = unit
    spare_capacity_fraction: float = unit
    exposed_asset_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    flood_vulnerability: float = unit
    heat_vulnerability: float = unit
    drought_vulnerability: float = unit
    provenance: str
    confidence: Confidence = "low"
    in_demo_portfolio: bool = False

    @field_validator("latitude", "longitude")
    @classmethod
    def _round(cls, v):
        return v


class Relation(BaseModel):
    id: str
    source: str
    target: str
    product: str
    channel: Channel = "supply"
    relationship_type: str
    dependency: float = unit
    input_specificity: float = unit
    substitutability: float = unit
    storable: bool = True
    lead_time_days: float = Field(default=0.0, ge=0, le=365)
    annual_flow_musd: float = Field(default=0.0, ge=0)
    distance_km: Optional[float] = Field(default=None, ge=0)
    status: RelationStatus = "synthetic"
    confidence: float = unit
    provenance: str


class EntityDetail(Entity):
    in_degree: int
    out_degree: int
    supplier_concentration_hhi: Optional[float] = Field(description="Herfindahl index of incoming supply shares (null if no suppliers)")
    single_source_inputs: list[str]
    missing_fields: list[str]


class Page(BaseModel):
    total: int
    page: int
    page_size: int
