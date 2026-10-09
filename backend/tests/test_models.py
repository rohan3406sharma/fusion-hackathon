import numpy as np
import pytest

from app.models import analytics, backtest
from app.models.climate import build_direct_inputs, direct_disruption, PROVIDERS
from app.models.montecarlo import run_monte_carlo
from app.models.propagation import compile_network, propagate, transmission
from app.schemas.scenario import HazardComponent, ScenarioSpec
from app.services.runner import build_comparison, execute
from conftest import make_entity, make_rel


def spec(**kw):
    h = dict(hazard_type="flood", intensity=0.8, duration_days=14, affected_entity_ids=["a"])
    h.update(kw.pop("h", {}))
    return ScenarioSpec(name="t", hazards=[HazardComponent(**h)], **kw)


def chain():
    ents = [make_entity("a"), make_entity("b", alternative_supplier_availability=0.2), make_entity("c")]
    rels = [make_rel("a", "b", dep=0.5, spec=0.8, sub=0.25), make_rel("b", "c", dep=1.0, spec=1.0, sub=0.0)]
    return ents, rels


def test_hand_checked_two_hop_propagation():
    ents, rels = chain()
    net = compile_network(ents, rels)
    tr = transmission(net, T=30)
    assert tr[0, 0] == pytest.approx(0.5 * 0.8 * (1 - 0.2) * (1 - 0.25))          # 0.24
    hist, conv = propagate(net, np.array([[1.0, 0, 0]]), tr, max_depth=5)
    assert hist[1][0].tolist() == pytest.approx([1, 0.24, 0])
    assert hist[2][0].tolist() == pytest.approx([1, 0.24, 0.24])                 # B->C fully dependent
    assert conv


def test_depth_limits_reach():
    ents, rels = chain()
    net = compile_network(ents, rels)
    hist, _ = propagate(net, np.array([[1.0, 0, 0]]), transmission(net, 30), max_depth=1)
    assert hist[-1][0, 2] == 0


def test_inventory_and_lead_time_reduce_transmission():
    ents, rels = chain()
    ents[1] = make_entity("b", inventory_days=20, alternative_supplier_availability=0.2)
    rels[0] = make_rel("a", "b", dep=0.5, spec=0.8, sub=0.25, storable=True, lead=5)
    net = compile_network(ents, rels)
    t_long, t_short, t_inv = transmission(net, T=100)[0, 0], transmission(net, T=20)[0, 0], transmission(net, T=100, inventory_scale=2)[0, 0]
    assert t_short == 0.0                                        # buffer (25d) covers 20d disruption
    assert t_inv < t_long
    assert t_long == pytest.approx(0.24 * (100 - 25) / 100)


def test_substitution_scale_reduces_transmission():
    ents, rels = chain()
    net = compile_network(ents, rels)
    assert transmission(net, 30, substitution_scale=1.5)[0, 0] < transmission(net, 30)[0, 0]


def test_no_double_counting_two_suppliers_same_input():
    ents = [make_entity("a1"), make_entity("a2"), make_entity("t")]
    rels = [make_rel("a1", "t", dep=0.5), make_rel("a2", "t", dep=0.5)]
    net = compile_network(ents, rels)
    hist, _ = propagate(net, np.array([[1.0, 1.0, 0]]), transmission(net, 30), 3)
    assert hist[-1][0, 2] == pytest.approx(1.0, abs=1e-6) and hist[-1].max() <= 1.0     # additive within one input, capped at 1


def test_noisy_or_across_different_inputs():
    ents = [make_entity("a1"), make_entity("a2", output_product="sugar"), make_entity("t")]
    rels = [make_rel("a1", "t", dep=0.5), make_rel("a2", "t", dep=0.5, product="sugar")]
    net = compile_network(ents, rels)
    hist, _ = propagate(net, np.array([[1.0, 1.0, 0]]), transmission(net, 30), 3)
    assert hist[-1][0, 2] == pytest.approx(1 - 0.5 * 0.5)


def test_cycle_terminates_and_is_bounded():
    ents = [make_entity("a"), make_entity("b")]
    rels = [make_rel("a", "b", dep=1.0), make_rel("b", "a", dep=1.0)]
    net = compile_network(ents, rels)
    hist, conv = propagate(net, np.array([[0.5, 0.0]]), transmission(net, 30), max_depth=50)
    assert conv and 0 <= hist[-1].min() and hist[-1].max() <= 1.0 and len(hist) <= 51


def test_empty_and_disconnected_graphs():
    net = compile_network([make_entity("a"), make_entity("b")], [])
    hist, conv = propagate(net, np.array([[0.7, 0.0]]), transmission(net, 30), 4)
    assert conv and hist[-1][0].tolist() == [0.7, 0.0]
    net0 = compile_network([], [])
    hist0, _ = propagate(net0, np.zeros((1, 0)), transmission(net0, 30), 3)
    assert hist0[-1].shape == (1, 0)


def test_direct_exposure_monotone_bounded_and_footprint():
    ents, _ = chain()
    ents.append(make_entity("far", latitude=60, longitude=60))
    lo = direct_disruption(build_direct_inputs(ents, spec(h=dict(intensity=0.3, affected_entity_ids=[], center_lat=10, center_lon=10, radius_km=100))))
    hi = direct_disruption(build_direct_inputs(ents, spec(h=dict(intensity=0.9, affected_entity_ids=[], center_lat=10, center_lon=10, radius_km=100))))
    assert (hi >= lo).all() and (hi <= 1).all() and (lo >= 0).all()
    assert hi[0, 0] > hi[0, 3] == pytest.approx(0.0)           # far entity unaffected


def test_duration_and_vulnerability_matter():
    ents = [make_entity("a")]
    short = direct_disruption(build_direct_inputs(ents, spec(h=dict(duration_days=2))))[0, 0]
    long = direct_disruption(build_direct_inputs(ents, spec(h=dict(duration_days=60))))[0, 0]
    assert long > short > 0
    ents0 = [make_entity("a", flood_vulnerability=0.0)]
    assert direct_disruption(build_direct_inputs(ents0, spec()))[0, 0] == 0.0


def test_compound_amplification():
    ents = [make_entity("a")]
    h = [HazardComponent(hazard_type="heat", intensity=0.6, duration_days=14, affected_entity_ids=["a"]),
         HazardComponent(hazard_type="drought", intensity=0.5, duration_days=60, affected_entity_ids=["a"])]
    base = direct_disruption(build_direct_inputs(ents, ScenarioSpec(name="x", hazards=h)))[0, 0]
    amp = direct_disruption(build_direct_inputs(ents, ScenarioSpec(name="x", hazards=h, compound_amplification=0.2)))[0, 0]
    assert amp == pytest.approx(min(1, base * 1.2))


def test_provider_registry_labels_synthetic():
    assert PROVIDERS["synthetic_footprint"].is_synthetic


def test_scenario_validation():
    with pytest.raises(ValueError):
        HazardComponent(hazard_type="flood", intensity=0.5, duration_days=5)           # no locator
    with pytest.raises(ValueError):
        HazardComponent(hazard_type="flood", intensity=1.5, duration_days=5, regions=["x"])
    with pytest.raises(ValueError):
        HazardComponent(hazard_type="flood", intensity=0.5, duration_days=5, center_lat=1.0)


def test_network_vs_location_and_zero_denominator():
    ents, rels = chain()
    ex = execute(ents, rels, spec())
    d, t = ex.losses()
    assert t.sum() >= d.sum() > 0
    ents0 = [e.model_copy(update={"flood_vulnerability": 0.0}) for e in ents]
    ex0 = execute(ents0, rels, spec())
    rows = [dict(direct_disruption=0, final_disruption=0, direct_loss_musd=0, total_loss_musd=0)] * 3
    cmp0 = build_comparison(ents0, rows, *ex0.losses())
    assert cmp0["relative_difference"] is None and cmp0["location_only_loss_musd"] == 0


def test_monte_carlo_reproducible_and_ordered():
    ents, rels = chain()
    s = spec()
    det = float(execute(ents, rels, s).losses()[1].sum())
    a = run_monte_carlo(ents, rels, s, 200, 1, det)
    b = run_monte_carlo(ents, rels, s, 200, 1, det)
    c = run_monte_carlo(ents, rels, s, 200, 2, det)
    assert a["total_loss"] == b["total_loss"] and a["total_loss"] != c["total_loss"]
    q = a["total_loss"]
    assert q["p05"] <= q["median"] <= q["p95"] and q["min"] <= q["p05"] and a["n_simulations"] == 200
    assert sum(h["count"] for h in a["histogram"]) == 200


def test_systemic_scores_bounded_and_decomposed():
    ents, rels = chain()
    rows = analytics.systemic_scores(ents, rels)
    assert all(0 <= r["score"] <= 100 for r in rows)
    r0 = rows[0]
    assert r0["score"] == pytest.approx(sum(r0["contributions"].values()), abs=0.05)
    assert r0["contributions"]["direct_exposure"] == 0.0          # no scenario -> no exposure component


def test_backtest_metrics_and_guard():
    sim = {"a": 0.9, "b": 0.5, "c": 0.0, "d": 0.2}
    perfect = backtest.evaluate(sim, dict(sim))
    assert perfect["metrics"]["mae"] == 0 and perfect["metrics"]["spearman"] == pytest.approx(1.0)
    assert backtest.evaluate(sim, {"a": 0.1})["metrics"] is None


def test_total_loss_monotone_in_intensity_and_zero_without_dependency():
    ents, rels = chain()
    losses = [execute(ents, rels, spec(h=dict(intensity=i))).losses()[1].sum() for i in (0.2, 0.5, 0.8, 1.0)]
    assert losses == sorted(losses) and losses[0] > 0
    no_dep = execute(ents, rels, spec(dependency_scale=0.25)).losses()
    full = execute(ents, rels, spec()).losses()
    assert (no_dep[1] - no_dep[0]).sum() <= (full[1] - full[0]).sum()          # weaker dependency -> no more indirect loss


def test_large_inventory_blocks_storable_transmission():
    ents = [make_entity("a"), make_entity("b", inventory_days=100), make_entity("c")]
    rels = [make_rel("a", "b", storable=True, lead=3), make_rel("b", "c", storable=True)]
    ex = execute(ents, rels, spec(h=dict(duration_days=10)))
    assert ex.final[1] == 0 and ex.final[2] == 0 and ex.d0[0] > 0


def test_monte_carlo_samples_alternatives():
    ents, rels = chain()
    out = run_monte_carlo(ents, rels, spec(), 100, 1, 1.0)
    assert "alternatives" in {s["parameter"] for s in out["sensitivity"]}
