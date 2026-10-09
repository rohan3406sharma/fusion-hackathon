import pytest

SC = "sc_punjab_flood"


def test_health_and_metadata(client):
    assert client.get("/health").json()["status"] == "ok"
    m = client.get("/api/v1/metadata").json()
    assert m["domain"] == "food_and_beverage" and m["model_status"]["validated"] is False


def test_database_seeded_with_builtin_scenarios(client):
    items = client.get("/api/v1/scenarios").json()["items"]
    assert {i["id"] for i in items} >= {"sc_punjab_flood", "sc_brazil_drought", "sc_nweurope_compound"}
    assert client.get(f"/api/v1/scenarios/{SC}").json()["builtin"] is True


def test_graph_endpoint_shape(client):
    g = client.get("/api/v1/graph").json()
    assert g["n_nodes"] == len(g["nodes"]) and g["n_edges"] == len(g["edges"])
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    assert client.get("/api/v1/graph?include_financial=false").json()["n_edges"] < g["n_edges"]


def test_entities_filter_search_pagination(client):
    r = client.get("/api/v1/entities", params={"entity_type": "port_hub"}).json()
    assert r["total"] == 5 and all(i["entity_type"] == "port_hub" for i in r["items"])
    assert client.get("/api/v1/entities", params={"q": "rotterdam"}).json()["total"] >= 1
    p = client.get("/api/v1/entities", params={"page_size": 10, "page": 2}).json()
    assert len(p["items"]) == 10 and p["page"] == 2
    assert client.get("/api/v1/entities", params={"page_size": 1000}).status_code == 422


def test_entity_detail_dependencies_and_404(client):
    d = client.get("/api/v1/entities/dairy_pack_nl").json()
    assert d["in_degree"] > 0 and d["supplier_concentration_hhi"] is not None and d["synthetic"] is True
    dep = client.get("/api/v1/entities/dairy_pack_nl/dependencies").json()
    assert dep["suppliers"] and dep["customers"] and dep["n_upstream"] > 0
    assert client.get("/api/v1/entities/nope").status_code == 404
    assert client.get("/api/v1/entities/nope/dependencies").status_code == 404


def test_run_scenario_schema_and_invariants(client):
    r = client.post(f"/api/v1/scenarios/{SC}/run")
    assert r.status_code == 200
    j = r.json()
    s = j["summary"]
    assert s["total_loss_musd"] == pytest.approx(s["direct_loss_musd"] + s["indirect_loss_musd"], abs=0.01)
    assert sum(o["loss_musd"] for o in j["orders"]) == pytest.approx(s["total_loss_musd"], abs=0.05)
    assert s["n_exposed_facilities"] > 0 and j["limitations"] and j["comparison"]["network_aware_loss_musd"] >= j["comparison"]["location_only_loss_musd"]
    assert all(0 <= e["final_disruption"] <= 1 for e in j["entities"])


def test_depth_changes_results(client):
    d1 = client.post("/api/v1/analysis/propagation", json={"scenario_id": "sc_brazil_drought", "max_depth": 1}).json()["summary"]["total_loss_musd"]
    d6 = client.post("/api/v1/analysis/propagation", json={"scenario_id": "sc_brazil_drought", "max_depth": 6}).json()["summary"]["total_loss_musd"]
    assert d6 > d1


def test_inline_scenario_and_validation_errors(client):
    spec = {"name": "inline", "hazards": [{"hazard_type": "heat", "intensity": 0.7, "duration_days": 10, "affected_entity_ids": ["cold_ca"]}]}
    ok = client.post("/api/v1/analysis/propagation", json={"scenario": spec})
    assert ok.status_code == 200 and ok.json()["summary"]["n_exposed_facilities"] == 1
    bad = dict(spec, hazards=[dict(spec["hazards"][0], affected_entity_ids=["ghost"])])
    assert client.post("/api/v1/analysis/propagation", json={"scenario": bad}).status_code == 422
    assert client.post("/api/v1/analysis/propagation", json={}).status_code == 422
    assert client.post("/api/v1/analysis/propagation", json={"scenario_id": "zzz"}).status_code == 404
    assert client.post("/api/v1/scenarios", json={"name": "x", "hazards": []}).status_code == 422
    assert client.post("/api/v1/scenarios", json={"name": "x", "hazards": [{"hazard_type": "flood", "intensity": 2, "duration_days": 3, "regions": ["a"]}]}).status_code == 422


def test_create_and_run_custom_scenario(client):
    body = {"name": "My drought", "hazards": [{"hazard_type": "drought", "intensity": 0.5, "duration_days": 60, "center_lat": -21.5, "center_lon": -47, "radius_km": 300}]}
    c = client.post("/api/v1/scenarios", json=body)
    assert c.status_code == 201
    sid = c.json()["id"]
    assert client.post(f"/api/v1/scenarios/{sid}/run").json()["summary"]["total_loss_musd"] > 0
    assert any(i["id"] == sid for i in client.get("/api/v1/scenarios").json()["items"])


def test_monte_carlo_endpoint_reproducible_and_limits(client):
    req = {"scenario_id": "sc_ca_heatwave", "n_simulations": 100, "seed": 5}
    a = client.post("/api/v1/analysis/monte-carlo", json=req).json()
    b = client.post("/api/v1/analysis/monte-carlo", json=req).json()
    assert a == b and a["total_loss"]["p05"] <= a["total_loss"]["median"] <= a["total_loss"]["p95"]
    assert "not a formal confidence interval" in a["interpretation"].lower() or "NOT a formal confidence interval" in a["interpretation"]
    assert client.post("/api/v1/analysis/monte-carlo", json={**req, "n_simulations": 10**6}).status_code == 422
    assert client.post("/api/v1/analysis/monte-carlo", json={**req, "n_simulations": 5}).status_code == 422


def test_network_vs_location(client):
    c = client.post("/api/v1/analysis/network-vs-location", json={"scenario_id": "sc_rotterdam_port_flood"}).json()
    assert c["location_only_loss_musd"] > 0 and c["absolute_difference_musd"] > 0
    assert c["hidden_exposure_count"] >= 1 and all("rank_change" in r for r in c["portfolio_rows"])


def test_systemic_and_critical_paths(client):
    s = client.get("/api/v1/analysis/systemic-risk", params={"scenario_id": SC, "limit": 5}).json()
    assert len(s["rows"]) == 5 and s["rows"][0]["score"] >= s["rows"][-1]["score"] and "not a probability" in s["interpretation"]
    assert abs(s["rows"][0]["score"] - sum(s["rows"][0]["contributions"].values())) < 0.1
    p = client.get("/api/v1/analysis/critical-paths", params={"scenario_id": "sc_brazil_drought", "top": 3}).json()
    assert 1 <= len(p) <= 3 and all(len(x["entity_ids"]) >= 2 for x in p)


def test_entity_impact(client):
    j = client.get("/api/v1/entities/softdrink_br/impact", params={"scenario_id": "sc_brazil_drought"}).json()
    assert j["impact"]["status"] in ("direct", "propagated") and j["incoming_transmission"]
    assert client.get("/api/v1/entities/ghost/impact").status_code == 404


def test_mitigation_endpoints(client):
    body = {"scenario_id": "sc_brazil_drought", "interventions": [{"type": "inventory_buffer", "entity_ids": ["softdrink_br"], "magnitude": 30}]}
    j = client.post("/api/v1/mitigation/compare", json=body).json()
    assert j["options"][0]["effect"]["loss_reduction_musd"] >= 0 and "SYNTHETIC" in j["options"][0]["cost"]["basis"]
    assert client.post("/api/v1/mitigation/compare", json={**body, "interventions": [{"type": "inventory_buffer", "entity_ids": ["ghost"]}]}).status_code == 422
    assert client.post("/api/v1/mitigation/compare", json={**body, "interventions": []}).status_code == 422
    rec = client.get("/api/v1/mitigation/recommendations", params={"scenario_id": "sc_brazil_drought", "top": 4}).json()
    scores = [o["priority_score"] for o in rec["options"]]
    assert len(scores) == 4 and scores == sorted(scores, reverse=True)


def test_data_endpoints(client):
    q = client.get("/api/v1/data/quality").json()
    assert q["synthetic_entities"] == q["entities"] and q["observed_entities"] == 0 and q["validation"]["ok"]
    src = client.get("/api/v1/data/sources").json()
    assert src["reference_audit"]["food_and_beverage_segments_found"] == [] and "Sectivia" in src["required_attribution"]


def test_backtest_and_reports(client):
    r = client.post("/api/v1/analysis/backtest", json={"scenario_id": SC, "use_synthetic_demo": True}).json()
    assert "NOT validation" in r["label"]
    assert client.post("/api/v1/analysis/backtest", json={"scenario_id": SC, "observed": {"ghost": 0.5}}).status_code == 422
    assert client.post("/api/v1/analysis/backtest", json={"scenario_id": SC, "observed": {"farm_wheat_pb": 3}}).status_code == 422
    md = client.get(f"/api/v1/scenarios/{SC}/report")
    assert md.status_code == 200 and "SYNTHETIC" in md.text
    assert client.get(f"/api/v1/scenarios/{SC}/report", params={"format": "csv"}).text.startswith("scenario_id,scenario_name,data_status,entity_id,")
    assert client.get("/api/v1/scenarios/none/report").status_code == 404


def test_exports_carry_scenario_assumptions_and_uncertainty(client):
    csv_text = client.get(f"/api/v1/scenarios/{SC}/report", params={"format": "csv"}).text.splitlines()
    assert csv_text[1].startswith(f"{SC},Punjab-Haryana Monsoon Flood,synthetic,")
    md = client.get(f"/api/v1/scenarios/{SC}/report", params={"include_monte_carlo": True, "n_simulations": 100, "seed": 3}).text
    assert "## Assumptions" in md and "## Limitations" in md and "100 simulations, seed 3" in md and "not a formal confidence interval" in md.lower()
    plain = client.get(f"/api/v1/scenarios/{SC}/report").text
    assert "Monte Carlo" not in plain


def test_portfolio_ties_share_average_rank(client):
    rows = client.post("/api/v1/analysis/network-vs-location", json={"scenario_id": "sc_rotterdam_port_flood"}).json()["portfolio_rows"]
    unaffected = [r for r in rows if r["network_disruption"] == 0]
    assert len(unaffected) > 3
    assert len({r["rank_network"] for r in unaffected}) == 1 and all(r["rank_change"] == 0 for r in unaffected)   # ties are not "movers"
    assert all(r["rank_network"] > 1 for r in unaffected)
    hidden = [r for r in rows if r["hidden_exposure"]]
    assert hidden and all(r["rank_change"] > 0 for r in hidden)


def test_bottlenecks_expose_customer_counts(client):
    b = client.post(f"/api/v1/scenarios/{SC}/run").json()["bottlenecks"]
    assert b and all("out_degree" in x and "weighted_out_dependency" in x for x in b)


def test_recommendations_are_loadable_interventions(client):
    o = client.get("/api/v1/mitigation/recommendations", params={"scenario_id": "sc_brazil_drought", "top": 3}).json()["options"]
    assert all(x["interventions"] and x["interventions"][0]["type"] for x in o)
