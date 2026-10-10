"""Holdings as companies (multi-segment holdings): structure, invariants, equivalence with v0.3 and API/copilot wiring."""
import numpy as np
import pytest

from app.domain.holdings import Holding, Holdings, Segment, build_holdings, validate_companies
from app.models import reverse_stress as rs
from app.schemas.finder import FinderRequest
from app.services.finder import screen
from app.services.state import get_state

from conftest import make_entity


@pytest.fixture(scope="module")
def ds(client):
    return get_state().dataset


def test_company_structures_load_and_shares_follow_value_added(ds):
    assert ds.validation.ok and len(ds.company_by_id) == 4
    hs = build_holdings(ds)
    five = next(h for h in hs.holdings if h.id == "co_five_rivers")
    assert five.multi_segment and five.other_share == pytest.approx(0.55)
    assert sum(s.share for s in five.segments) + five.other_share == pytest.approx(1.0)
    va = {s.entity_id: ds.by_id[s.entity_id].value_added_musd for s in five.segments}
    for s in five.segments:                                  # modelled shares are proportional to value added
        assert s.share == pytest.approx(va[s.entity_id] / sum(va.values()) * 0.45)
    assert five.primary_entity_id == max(va, key=va.get)


def test_company_view_keeps_the_same_money_in_the_same_places(ds):
    units, comps = build_holdings(ds, None, "business_unit"), build_holdings(ds, None, "company")
    assert len(units.holdings) == 18 and len(comps.holdings) == 16 and comps.n_multi_segment == 4
    assert sum(h.weight for h in comps.holdings) == pytest.approx(1.0)
    w = {h.id: h.weight for h in units.holdings}
    lone = next(h for h in comps.holdings if h.id == "co_lone_star")
    assert lone.weight == pytest.approx(w["snack_us"] + w["softdrink_us"] + w["juice_us"])
    five = next(h for h in comps.holdings if h.id == "co_five_rivers")
    assert five.weight == pytest.approx(w["biscuit_in"])           # the flour mill and oil packer were not held: same position size
    ew = comps.entity_weights()                                       # spread over segments; the non-F&B share carries no entity weight
    assert sum(ew.values()) == pytest.approx(1.0 - five.weight * 0.55)
    assert {"mill_pb", "cookoil_in", "mill_ks", "dairy_proc_fr"} <= comps.owned


def test_weights_accept_company_ids_only_in_the_company_view(ds):
    assert [h.id for h in build_holdings(ds, {"co_five_rivers": 1.0}).holdings] == ["co_five_rivers"]
    assert [h.id for h in build_holdings(ds, {"biscuit_in": 1.0}).holdings] == ["co_five_rivers"]    # an owned unit counts towards its company
    with pytest.raises(ValueError, match="holding_view='company'"):
        build_holdings(ds, {"co_five_rivers": 1.0}, "business_unit")
    with pytest.raises(ValueError, match="unknown holdings"):
        build_holdings(ds, {"ghost": 1.0})
    with pytest.raises(ValueError, match="holding_view"):
        build_holdings(ds, None, "sector")


def _toy(shares, other=0.0):
    ents = {f"e{i}": i for i in range(len(shares))}
    h = Holding("co", "Co", 1.0, tuple(Segment(f"e{i}", f"e{i}", "x", s) for i, s in enumerate(shares)), other)
    return Holdings("company", [h]).compile(ents, len(shares))


def test_company_disruption_orders_segment_weighted_upper_end_and_one_node():
    rng = np.random.default_rng(3)
    for _ in range(200):
        n = int(rng.integers(1, 5))
        other = float(rng.uniform(0, 0.9))
        raw = rng.uniform(0.1, 1, n)
        hm = _toy(raw / raw.sum() * (1 - other), other)
        D = rng.uniform(0, 1, (7, n))
        seg, up, one = hm.segment_weighted(D)[:, 0], hm.if_other_hit(D)[:, 0], hm.one_node(D)[:, 0]
        assert np.all(seg <= up + 1e-12) and np.all(up <= one + 1e-12) and np.all((seg >= 0) & (one <= 1))
        assert np.all(up <= D.max(axis=1) + 1e-12) and np.all(up >= D.min(axis=1) - 1e-12)   # a weighted average of the units


def test_single_business_holding_is_its_unit_and_an_unhit_segment_only_dilutes():
    hm1 = _toy([1.0])
    D = np.array([[0.3], [0.8]])
    for f in (hm1.segment_weighted, hm1.if_other_hit, hm1.one_node):
        assert np.allclose(f(D)[:, 0], D[:, 0])
    hm2 = _toy([0.6, 0.4])
    D2 = np.array([[0.3, 0.0], [0.8, 0.0]])                  # the added unit is not hit
    assert np.all(hm2.segment_weighted(D2)[:, 0] <= D[:, 0])
    # one node: any unit's shortfall stops the whole company (noisy-OR), so two units each half down leave it 75% down, not 50%
    assert np.allclose(hm2.one_node(np.array([[0.5, 0.5], [0.2, 0.0]]))[:, 0], [0.75, 0.2])
    half = _toy([0.5], 0.5)                                  # one unit carrying half the value added, the rest outside F&B
    assert np.allclose(half.segment_weighted(D)[:, 0], 0.5 * D[:, 0]) and np.allclose(half.if_other_hit(D)[:, 0], D[:, 0])


def test_business_unit_view_reproduces_the_v03_portfolio_scores(ds):
    sc = screen(ds, FinderRequest(holding_view="business_unit"))
    w_v03 = rs.weight_vector(sc.net, {k: v / sum(ds.portfolio_weights.values()) for k, v in ds.portfolio_weights.items()})
    assert np.array_equal(sc.w, w_v03)
    _, p_net, _ = rs.score(sc.d0, sc.fin, sc.T, w_v03)
    assert np.array_equal(sc.p_net, p_net)


def test_company_view_portfolio_is_the_weighted_sum_of_company_disruptions(ds):
    sc = screen(ds, FinderRequest())
    pf = np.minimum(1.0, sc.T / 365.0)
    assert np.allclose(sc.p_net, (sc.hm.segment_weighted(sc.fin) @ sc.hm.W) * pf, atol=1e-15)
    assert np.all(sc.p_net >= sc.p_loc - 1e-12)


def test_finder_api_company_view_reports_structure_and_bounds(client):
    j = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False, "top_k": 100}).json()
    assert j["holding_view"] == "company" and len(j["holdings"]) == 16
    assert sum(h["weight"] for h in j["holdings"]) == pytest.approx(1.0, abs=1e-5)
    for e in j["events"] + j["hidden_only_events"]:
        assert e["portfolio_network_impact"] <= e["portfolio_network_impact_if_other_hit"] + 1e-7 <= e["portfolio_network_impact_one_node"] + 2e-7
        for h in e["top_holdings"]:
            if h["kind"] == "multi_segment":
                seg = sum(s["share"] * s["network_disruption"] for s in h["segments"])
                assert h["network_disruption"] == pytest.approx(seg, abs=3e-4)
                assert h["network_disruption"] <= h["network_disruption_if_other_hit"] + 1e-4 <= h["network_disruption_one_node"] + 2e-4
                one = 1 - np.prod([1 - s["network_disruption"] for s in h["segments"]])
                assert h["network_disruption_one_node"] == pytest.approx(one, abs=3e-4)
    cmp_ = j["structure_comparison"]
    views = {v["view"]: v for v in cmp_["views"]}
    assert set(views) == {"business_unit", "company", "company_if_other_hit", "company_one_node"}
    assert views["company"]["n_hidden_only"] == j["n_hidden_only"] and views["business_unit"]["n_holdings"] == 18
    assert views["company_one_node"]["mean_top10_impact"] >= views["company"]["mean_top10_impact"]
    assert cmp_["n_multi_segment"] == 4 and cmp_["hidden_only_events_on_own_sites"] >= 1
    owned = get_state().dataset.company_of
    assert all(m["entity_id"] not in owned for m in j["matrix"])                      # a company's own units are not "upstream"
    bu = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False, "holding_view": "business_unit"}).json()
    assert bu["structure_comparison"] is None and len(bu["holdings"]) == 18
    assert all(h["kind"] == "single_business" for e in bu["events"] for h in e["top_holdings"])
    assert client.post("/api/v1/analysis/reverse-stress", json={"holding_view": "sector"}).status_code == 422


def test_promote_reproduces_the_finder_in_both_views(client):
    for view in ("company", "business_unit"):
        j = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 0, "include_pairs": False, "holding_view": view}).json()
        ev = j["hidden_only_events"][0]
        rec = client.post("/api/v1/analysis/reverse-stress/promote", json={"hazard": ev["hazard_component"], "label": ev["label"]}).json()
        run = client.post(f"/api/v1/scenarios/{rec['id']}/run", json={"holding_view": view}).json()
        assert run["comparison"]["holding_view"] == view
        assert run["comparison"]["portfolio_network_impact"] == pytest.approx(ev["portfolio_network_impact"], abs=1e-6)


def test_comparison_rows_are_companies_with_segments(client):
    c = client.post("/api/v1/analysis/network-vs-location", json={"scenario_id": "sc_punjab_flood"}).json()
    assert c["holding_view"] == "company" and len(c["portfolio_rows"]) == 16
    five = next(r for r in c["portfolio_rows"] if r["entity_id"] == "co_five_rivers")
    assert five["kind"] == "multi_segment" and five["other_businesses_share"] == pytest.approx(0.55) and five["primary_entity_id"]
    assert five["network_disruption"] == pytest.approx(sum(s["share"] * s["network_disruption"] for s in five["segments"]), abs=2e-4)
    assert five["network_disruption"] < five["network_disruption_if_other_hit"] < five["network_disruption_one_node"]
    assert c["portfolio_network_impact"] <= c["portfolio_network_impact_if_other_hit"] <= c["portfolio_network_impact_one_node"]
    assert "companies" in c["scope_note"]
    bu = client.post("/api/v1/analysis/network-vs-location", json={"scenario_id": "sc_punjab_flood", "holding_view": "business_unit"}).json()
    assert len(bu["portfolio_rows"]) == 18 and bu["portfolio_network_impact_one_node"] is None


def test_portfolio_and_entity_endpoints_describe_company_structure(client):
    p = client.get("/api/v1/portfolio").json()
    assert p["holding_view"] == "company" and p["n_business_units"] == 18 and p["n_multi_segment"] == 4 and len(p["holdings"]) == 16
    five = next(h for h in p["holdings"] if h["entity_id"] == "co_five_rivers")
    assert {s["entity_id"] for s in five["segments"]} == {"biscuit_in", "mill_pb", "cookoil_in"}
    assert len(client.get("/api/v1/portfolio", params={"holding_view": "business_unit"}).json()["holdings"]) == 18
    mill = client.get("/api/v1/entities/mill_pb").json()["company"]
    assert mill["id"] == "co_five_rivers" and mill["in_demo_portfolio"] and mill["synthetic"] and 0 < mill["share"] < 0.2
    assert client.get("/api/v1/entities/bakery_uk").json()["company"] is None


def test_invalid_company_structures_are_reported_not_used():
    ents = {e.id: e for e in [make_entity("a"), make_entity("b"), make_entity("bank", entity_type="financial")]}
    errs = validate_companies([
        {"id": "c1", "segments": [{"entity_id": "a"}], "other_businesses_share": 0.2},
        {"id": "c1", "segments": [{"entity_id": "a"}, {"entity_id": "ghost"}, {"entity_id": "bank"}], "other_businesses_share": 1.5},
        {"id": "b", "segments": []},
    ], ents)
    text = " ".join(errs)
    for needle in ("duplicate id", "belongs to two companies", "unknown segment entity 'ghost'", "financial entity 'bank'",
                   "other_businesses_share", "collides with an entity id", "no segments"):
        assert needle in text, needle
    from app.domain.dataset import FnbDataset
    ds2 = FnbDataset(list(ents.values()), [], [], {}, {})
    ds2.set_companies({"companies": [{"id": "c1", "segments": [{"entity_id": "ghost"}]}]})
    assert not ds2.validation.ok and ds2.company_by_id == {} and ds2.company_of == {}


def test_copilot_explains_company_structure_without_new_numbers(ds):
    from app.copilot import service
    from app.schemas.copilot import AskRequest, FinderEventFocus, ScenarioFocus
    from app.config import get_settings
    sheet = service.build_sheet(ds, ScenarioFocus(scenario_id="sc_punjab_flood"))
    i = next(k for k in range(1, 6) if sheet.facts.get(f"holding_{k}_name") and sheet.facts[f"holding_{k}_name"].value == "Five Rivers Consumer Group")
    assert sheet.facts[f"holding_{i}_structure"].provenance == "synthetic_input"
    assert sheet.facts[f"holding_{i}_other_share"].value == pytest.approx(0.55)
    assert sheet.facts[f"holding_net_{i}_if_other_hit"].provenance == "unvalidated_model_output"
    r = service.ask(ds, AskRequest(focus=FinderEventFocus(event_id="fp:ent:retail_in:350:drought")), get_settings(), provider_obj=None)
    txt = " ".join(s.text for s in r.sections["holdings_affected"])
    assert "Five Rivers Consumer Group is a company with several business units" in txt and "value-added-weighted average" in txt
    assert "if those other businesses were hit as hard" in txt and "modelled" in txt
