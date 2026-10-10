"""Hidden Exposure Finder and resilience optimiser: planted answers, exhaustive checks, invariants, API."""
import itertools

import numpy as np
import pytest

from app.models import optimiser as opt
from app.models import reverse_stress as rs
from app.models.events import build_library
from app.models.propagation import compile_network
from app.schemas.mitigation import Intervention
from conftest import make_entity, make_rel


def planted_graph(seed: int):
    """Random layered graph with ONE bottleneck node 'hub' feeding every holding through a specific, unsubstitutable input."""
    rng = np.random.default_rng(seed)
    n_up, n_hold = 6, 4
    ents = [make_entity("hub", output_product="hubgood", latitude=0.0, longitude=0.0, flood_vulnerability=0.9)]
    rels = []
    for i in range(n_up):
        ents.append(make_entity(f"u{i}", output_product=f"good{i}", latitude=float(rng.uniform(20, 60)), longitude=float(rng.uniform(20, 60)),
                                flood_vulnerability=0.9))
    for h in range(n_hold):
        ents.append(make_entity(f"h{h}", output_product=f"final{h}", entity_type="manufacturer", latitude=-40.0, longitude=-40.0,
                                in_demo_portfolio=True, flood_vulnerability=0.0))
        rels.append(make_rel("hub", f"h{h}", dep=0.9, spec=1.0, sub=0.0, product="hubgood"))
        for i in rng.choice(n_up, 2, replace=False):
            rels.append(make_rel(f"u{i}", f"h{h}", dep=float(rng.uniform(0.1, 0.3)), spec=0.5, sub=0.4, product=f"good{i}"))
    return ents, rels


@pytest.mark.parametrize("seed", range(20))
def test_planted_bottleneck_ranks_first(seed):
    ents, rels = planted_graph(seed)
    net = compile_network(ents, rels)
    events = [e for e in build_library(ents, ("flood",), 0.8, (150.0,), 0.3) if e.kind == "node"]
    w = rs.weight_vector(net, {e.id: 1.0 / 4 for e in ents if e.in_demo_portfolio})
    d0, T = rs.direct_matrix(ents, events), rs.event_T(events)
    fin = rs.run_events(net, d0, T, rs.Params())
    _, p_net, _ = rs.score(d0, fin, T, w)
    assert events[int(np.argmax(p_net))].origin_id == "hub"


def test_pair_search_matches_brute_force_and_greedy_is_compared():
    ents, rels = planted_graph(3)
    net = compile_network(ents, rels)
    w = rs.weight_vector(net, {e.id: 0.25 for e in ents if e.in_demo_portfolio})
    nodes = [net.idx[e.id] for e in ents if not e.in_demo_portfolio]
    single = rs.outage_matrix(net, nodes, rs.Params())
    res = rs.worst_pairs(net, nodes, w, rs.Params(), single)
    brute = max((float((rs.run_events(net, _pair(net, nodes, a, b), np.array([rs.OUTAGE_T]), rs.Params()) @ w)[0] * rs.OUTAGE_T / 365), (a, b))
                for a, b in itertools.combinations(range(len(nodes)), 2))
    assert res["exhaustive"][0][1] == pytest.approx(brute[0])
    assert res["greedy"][1] <= res["exhaustive"][0][1] + 1e-12


def _pair(net, nodes, a, b):
    d0 = np.zeros((1, net.n))
    d0[0, nodes[a]] = d0[0, nodes[b]] = 1.0
    return d0


def test_invariants_on_real_library(client):
    from app.services.finder import screen
    from app.schemas.finder import FinderRequest
    from app.services.state import get_state
    sc = screen(get_state().dataset, FinderRequest())
    assert np.all(sc.p_net >= sc.p_loc - 1e-12)                      # network view never sees less than location-only
    assert np.all((sc.hid >= 0) & (sc.hid <= 1))
    assert len(set(e.id for e in sc.events)) == len(sc.events)          # deterministic, unique ids
    again = screen(get_state().dataset, FinderRequest())
    assert np.array_equal(sc.p_net, again.p_net)                        # deterministic


def test_larger_radius_never_reduces_impact():
    from app.services.state import get_state
    ds = get_state().dataset
    net = compile_network(ds.entities, ds.relations)
    lib = build_library(ds.entities, ("drought",), 0.8, (150.0, 350.0), 0.0, include_regions=False)
    small = {e.id.replace(":150:", ":"): e for e in lib if ":150:" in e.id}
    big = {e.id.replace(":350:", ":"): e for e in lib if ":350:" in e.id}
    common = sorted(set(small) & set(big))[:40]
    w = rs.weight_vector(net, ds.portfolio_weights)
    ev = [small[k] for k in common] + [big[k] for k in common]
    d0, T = rs.direct_matrix(ds.entities, ev), rs.event_T(ev)
    _, p_net, _ = rs.score(d0, rs.run_events(net, d0, T, rs.Params()), T, w)
    n = len(common)
    assert np.all(p_net[n:] >= p_net[:n] - 1e-9)


def test_zero_weight_holding_contributes_nothing():
    ents, rels = planted_graph(1)
    net = compile_network(ents, rels)
    events = build_library(ents, ("flood",), 0.8, (150.0,), 0.3)
    d0, T = rs.direct_matrix(ents, events), rs.event_T(events)
    fin = rs.run_events(net, d0, T, rs.Params())
    w1 = rs.weight_vector(net, {"h0": 1.0})
    w2 = rs.weight_vector(net, {"h0": 1.0, "h1": 0.0})
    assert np.allclose(rs.score(d0, fin, T, w1)[1], rs.score(d0, fin, T, w2)[1])


def test_collapse_groups_near_duplicates():
    ents, rels = planted_graph(2)
    events = build_library(ents, ("flood",), 0.8, (150.0, 350.0), 0.3)
    d0 = rs.direct_matrix(ents, events)
    reps, variants = rs.collapse(np.arange(len(events)), events, d0)
    assert len(reps) < len(events) and sum(len(v) for v in variants.values()) + len(reps) == len(events)


def test_optimiser_respects_budget_and_matches_exhaustive_on_small_problem():
    ents, rels = planted_graph(5)
    events = [e for e in build_library(ents, ("flood",), 0.8, (150.0,), 0.3)]
    cands = [Intervention(type="facility_protection", entity_ids=["hub"], magnitude=0.6),
             Intervention(type="inventory_buffer", entity_ids=["h0"], magnitude=30),
             Intervention(type="input_substitution", entity_ids=["h1"], magnitude=0.5),
             Intervention(type="input_substitution", entity_ids=["h2"], magnitude=0.5),
             Intervention(type="facility_protection", entity_ids=["u0"], magnitude=0.6)]
    pb = opt.make_problem(ents, rels, events, {f"h{i}": 0.25 for i in range(4)}, rs.Params(), 3, cands)
    budget = float(np.sort(pb.costs)[:2].sum()) + 1e-6          # can afford roughly two of the cheapest
    plan, _ = opt.greedy(pb, budget)
    plan = opt.local_search(pb, plan, budget)
    assert pb.costs[plan].sum() <= budget + 1e-9
    ex = opt.exhaustive(pb, budget, list(range(len(cands))))
    assert pb.evaluate(tuple(plan)) <= ex["best_objective"] + 1e-12 or pb.evaluate(tuple(plan)) == pytest.approx(ex["best_objective"])
    assert pb.evaluate(tuple(plan)) <= pb.evaluate(())


def test_finder_api_promote_reproduces_numbers(client):
    r = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 60, "seed": 1})
    assert r.status_code == 200
    j = r.json()
    assert j["n_events"] > 500 and j["n_distinct_events"] < j["n_events"] and j["events"][0]["rank"] == 1
    assert all(e["hidden_only"] and e["portfolio_location_impact"] == 0 for e in j["hidden_only_events"])
    assert all(0 <= e["p_top5"] <= 1 for e in j["events"][:5])
    assert j["stability"]["n_draws"] == 60 and j["structural_bound"]["greedy_matches"] in (True, False)
    assert client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 60, "seed": 1}).json()["events"] == j["events"]
    ev = j["hidden_only_events"][0]
    rec = client.post("/api/v1/analysis/reverse-stress/promote", json={"hazard": ev["hazard_component"], "label": ev["label"]}).json()
    run = client.post(f"/api/v1/scenarios/{rec['id']}/run").json()
    assert run["comparison"]["portfolio_network_impact"] == pytest.approx(ev["portfolio_network_impact"], abs=1e-6)
    assert run["comparison"]["portfolio_location_impact"] == pytest.approx(0, abs=1e-9)


def test_finder_api_validation(client):
    assert client.post("/api/v1/analysis/reverse-stress", json={"weights": {"ghost": 1.0}}).status_code == 422
    assert client.post("/api/v1/analysis/reverse-stress", json={"radii_km": [0]}).status_code == 422
    assert client.post("/api/v1/analysis/reverse-stress", json={"hazards": []}).status_code == 422
    assert client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 5000}).status_code == 422
    assert client.get("/api/v1/portfolio").json()["synthetic"] is True


def test_shortlist_size_does_not_change_the_top(client):
    a = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 80, "shortlist": 100, "seed": 9}).json()
    b = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 80, "shortlist": 200, "seed": 9}).json()
    for x, y in zip(a["events"][:5], b["events"][:5]):
        assert x["id"] == y["id"] and abs(x["p_top5"] - y["p_top5"]) <= 0.1


def test_optimise_api(client):
    r = client.post("/api/v1/mitigation/optimise", json={"budget_musd": 2, "exhaustive_check": True, "robustness_draws": 10})
    assert r.status_code == 200
    j = r.json()
    assert j["plan_cost_musd"] <= 2 + 1e-9 and j["plan_objective"] <= j["baseline_objective"]
    assert j["exhaustive"]["optimality_gap"] is None or 0 <= j["exhaustive"]["optimality_gap"] <= 1
    assert len(j["cost_sensitivity"]) == 2 and j["robustness"]["n_draws"] == 10
    assert client.post("/api/v1/mitigation/optimise", json={"budget_musd": -1}).status_code == 422


def test_jrc_flood_layer_is_real_cited_and_used(client):
    from app.services.state import get_state
    layer = get_state().dataset.hazard_layers.get("jrc_flood_rp100")
    assert layer and "CC BY 4.0" in layer["licence"] and "Baugh" in layer["citation"] and layer["return_period_years"] == 100
    assert all(0 <= v["flooded_share"] <= 1 and v["deep_share"] <= v["flooded_share"] for v in layer["entities"].values())
    d = client.get("/api/v1/entities/farm_rice_mk").json()
    assert d["jrc_flood_rp100"]["flooded_share"] > 0.5 and "synthetic" in d["jrc_flood_rp100"]["meaning"].lower()
    flag = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False}).json()
    drop = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False, "flood_check": "drop"}).json()
    assert flag["hazard_layer"]["flood_events_checked"] > 0
    assert drop["n_distinct_events"] <= flag["n_distinct_events"]
    assert all(e["jrc_flood_check"] is None for e in flag["events"] if e["hazard"] != "flood")
    sources = client.get("/api/v1/data/sources").json()
    assert any(d["id"] == "jrc_flood_rp100" and d["synthetic"] is False for d in sources["datasets"])


# ---- audit additions: behaviours that earlier tests only checked indirectly ------------------------------------------
def test_hidden_share_is_one_minus_location_over_network(client):
    j = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False, "top_k": 100}).json()
    checked = 0
    for e in j["events"] + j["hidden_only_events"]:
        if e["portfolio_network_impact"] > 1e-5:
            assert e["hidden_share"] == pytest.approx(1 - e["portfolio_location_impact"] / e["portfolio_network_impact"], abs=2e-4)
            checked += 1
        assert e["hidden_only"] == (e["portfolio_location_impact"] == 0 and e["portfolio_network_impact"] > 0)
    assert checked > 50
    assert any(e["hidden_share"] == 0 for e in j["events"]) or any(0 < e["hidden_share"] < 1 for e in j["events"])   # not all 0 / all 1


def test_optimiser_objective_is_mean_of_the_worst_n_events():
    ents, rels = planted_graph(4)
    events = build_library(ents, ("flood",), 0.8, (150.0,), 0.3)
    w = {f"h{i}": 0.25 for i in range(4)}
    cands = [Intervention(type="inventory_buffer", entity_ids=["h0"], magnitude=30)]
    for tail in (1, 3, 5):
        pb = opt.make_problem(ents, rels, events, w, rs.Params(), tail, cands)
        net = compile_network(ents, rels)
        d0, T = rs.direct_matrix(ents, events), rs.event_T(events)
        p_net = rs.score(d0, rs.run_events(net, d0, T, rs.Params()), T, rs.weight_vector(net, w))[1]
        assert pb.evaluate(()) == pytest.approx(float(np.sort(p_net)[::-1][:tail].mean()))
    assert opt.make_problem(ents, rels, events, w, rs.Params(), 1, cands).evaluate(()) > \
        opt.make_problem(ents, rels, events, w, rs.Params(), 5, cands).evaluate(())


def test_rank_stats_counts_exactly_the_top_five():
    even = [8, 7, 6, 5, 4, 3, 2, 1]               # event i has rank i+1
    odd = [8, 1.5, 6, 5, 4, 3, 2, 1.4]            # event 1 falls to rank 7, event 5 rises to rank 5, event 7 stays last
    draws = np.array([even, odd] * 5, dtype=float)
    st = rs.rank_stats(draws)
    assert st["p_top"].tolist() == [1.0, 0.5, 1.0, 1.0, 1.0, 0.5, 0.0, 0.0]
    assert st["median_rank"][0] == 1 and st["median_rank"][7] == 8
    assert st["q25"][1] <= st["median_rank"][1] <= st["q75"][1]


def test_stability_is_seeded_and_uses_the_requested_number_of_draws():
    from app.schemas.finder import FinderRequest
    from app.services.finder import _stability, screen
    from app.services.state import get_state
    ds = get_state().dataset
    sc = screen(ds, FinderRequest())

    class Q:
        shortlist, stability_draws = 40, 30

    runs = {}
    for seed in (1, 1, 2):
        q = Q(); q.seed = seed
        short, d = _stability(sc.net, ds.entities, sc.events, sc.reps, sc.w, sc.params, q)
        runs.setdefault(seed, []).append(d)
    assert runs[1][0].shape == (30, 40)                    # draws x shortlisted events
    assert np.array_equal(runs[1][0], runs[1][1])           # same seed reproduces exactly
    assert not np.allclose(runs[1][0], runs[2][0])          # a different seed changes the draws


def test_jrc_flag_marks_events_with_no_modelled_flooding(client):
    from app.services.finder import jrc_check
    from app.services.state import get_state
    ds = get_state().dataset
    from app.models.events import build_library as bl
    from app.models import reverse_stress as rs2
    events = bl(ds.entities, ("flood",), 0.8, (150.0,), 0.3)
    d0 = rs2.direct_matrix(ds.entities, events)
    ids = [e.id for e in ds.entities]
    real = ds.hazard_layers["jrc_flood_rp100"]
    try:
        fake = {"entities": {i: {"flooded_share": 0.0, "deep_share": 0.0} for i in ids}}
        ds.hazard_layers["jrc_flood_rp100"] = fake
        assert not any(jrc_check(ds, events, d0).values())                         # nothing flooded anywhere -> every event flagged
        fake["entities"] = {i: {"flooded_share": 0.3, "deep_share": 0.1} for i in ids}
        assert all(jrc_check(ds, events, d0).values())                             # everything flooded -> every event consistent
        one = events[0].origin_id
        fake["entities"] = {i: {"flooded_share": 0.3 if i == one else 0.0, "deep_share": 0.0} for i in ids}
        res = jrc_check(ds, events, d0)
        assert res[0] is True and any(v is False for v in res.values())            # only events hitting the flooded entity pass
    finally:
        ds.hazard_layers["jrc_flood_rp100"] = real


def test_finder_weights_are_normalised(client):
    a = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False, "weights": {"bakery_uk": 2, "retail_uk": 2}}).json()
    b = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False, "weights": {"bakery_uk": 0.5, "retail_uk": 0.5}}).json()
    assert [e["portfolio_network_impact"] for e in a["events"][:5]] == [e["portfolio_network_impact"] for e in b["events"][:5]]
    assert sum(h["weight"] for h in a["holdings"]) == pytest.approx(1.0)


def test_single_points_of_failure_meet_their_stated_threshold(client):
    j = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False}).json()
    assert j["single_points_of_failure"]
    for s in j["single_points_of_failure"]:
        assert not s["is_holding"] and all(h["network_disruption"] >= 0.2 for h in s["holdings"])
