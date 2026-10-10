import os

os.environ["FIN04_DATABASE_URL"] = "sqlite://"   # in-memory
os.environ["FIN04_LLM_PROVIDER"] = "deterministic"   # tests never call a real model unless they inject a provider explicitly

import pytest
from fastapi.testclient import TestClient

from app.schemas.domain import Entity, Relation


def make_entity(eid: str, **kw) -> Entity:
    base = dict(id=eid, name=eid, synthetic=True, entity_type="processor", food_category="grains", output_product="flour",
                country="X", region="R", latitude=10.0, longitude=10.0, location_status="synthetic_approximate", facility_type="plant",
                revenue_musd=100.0, value_added_musd=20.0, inventory_days=0.0, alternative_supplier_availability=0.0,
                operational_criticality=0.5, spare_capacity_fraction=0.1, exposed_asset_share=1.0, flood_vulnerability=0.5,
                heat_vulnerability=0.5, drought_vulnerability=0.5, provenance="test", confidence="low")
    base.update(kw)
    return Entity(**base)


def make_rel(s: str, t: str, dep=0.5, spec=1.0, sub=0.0, product="flour", storable=False, lead=0.0, **kw) -> Relation:
    base = dict(id=f"{s}->{t}", source=s, target=t, product=product, channel="supply", relationship_type="product_supply", dependency=dep,
                input_specificity=spec, substitutability=sub, storable=storable, lead_time_days=lead, annual_flow_musd=10.0, status="synthetic",
                confidence=0.5, provenance="test")
    base.update(kw)
    return Relation(**base)


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c
