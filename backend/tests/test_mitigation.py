import pytest

from app.models.mitigation import apply_interventions, evaluate_interventions
from app.schemas.mitigation import Intervention
from app.schemas.scenario import HazardComponent, ScenarioSpec
from conftest import make_entity, make_rel


def setup():
    ents = [make_entity("a", output_product="flour", spare_capacity_fraction=0.5, revenue_musd=100, value_added_musd=50),
            make_entity("alt", output_product="flour", spare_capacity_fraction=0.1, revenue_musd=100, latitude=10.5, longitude=10.5),
            make_entity("b", entity_type="manufacturer", inventory_days=0.0, revenue_musd=200, value_added_musd=60)]
    rels = [make_rel("a", "b", dep=0.8, spec=1.0, sub=0.0, storable=True, lead=0.0, annual_flow_musd=40.0)]
    spec = ScenarioSpec(name="m", hazards=[HazardComponent(hazard_type="flood", intensity=0.9, duration_days=20, affected_entity_ids=["a"])])
    return ents, rels, spec


def test_inventory_buffer_reduces_loss():
    ents, rels, spec = setup()
    out = evaluate_interventions(ents, rels, spec, [Intervention(type="inventory_buffer", entity_ids=["b"], magnitude=60)], 0.1, 10)
    assert out["options"][0]["effect"]["loss_reduction_musd"] > 0
    assert out["options"][0]["effect"]["mitigated_direct_musd"] == out["options"][0]["effect"]["baseline_direct_musd"]


def test_diversification_is_capacity_limited():
    ents, rels, spec = setup()
    ids = {e.id: i for i, e in enumerate(ents)}
    import numpy as np
    _, new_rels, notes = apply_interventions(ents, rels, [Intervention(type="supplier_diversification", entity_ids=["b"], magnitude=1.0)], np.zeros(3), ids)
    # alt spare = 100*0.1 = 10 < flow 40 -> only 25% of the flow can move
    assert notes[0]["shifted_musd"] == pytest.approx(10.0) and notes[0]["note"] == "capacity-limited"
    deps = {r.source: r.dependency for r in new_rels}
    assert deps["a"] == pytest.approx(0.8 * 0.75) and deps["alt"] == pytest.approx(0.2) and sum(deps.values()) == pytest.approx(0.8)
    assert [r for r in new_rels if r.source == "alt"][0].status == "modelled"


def test_diversification_useless_when_alternative_is_hit():
    ents, rels, spec = setup()
    import numpy as np
    _, new_rels, notes = apply_interventions(ents, rels, [Intervention(type="supplier_diversification", entity_ids=["b"])], np.array([0.0, 0.9, 0.0]), {"a": 0, "alt": 1, "b": 2})
    assert notes[0]["shifted_musd"] == 0.0


def test_protection_cuts_direct_loss_and_costs_money():
    ents, rels, spec = setup()
    out = evaluate_interventions(ents, rels, spec, [Intervention(type="facility_protection", entity_ids=["a"], magnitude=0.5)], 0.1, 10)
    o = out["options"][0]
    assert o["effect"]["mitigated_direct_musd"] < o["effect"]["baseline_direct_musd"] and o["cost"]["annualised_cost_musd"] > 0
    assert 0 <= o["priority_score"] <= 100 and o["bcr_low"] < o["benefit_cost_ratio"] < o["bcr_high"]
