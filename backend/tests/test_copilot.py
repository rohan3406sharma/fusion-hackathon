"""AI Climate Risk Copilot: grounding, fallback, wording rules. Language-model behaviour is tested with STUB providers; the real
Ollama integration is tested separately (tests/test_copilot_live.py, skipped unless FIN04_LIVE_OLLAMA=1)."""
import json
import re

import pytest

from app.copilot import grounding, narrative, service
from app.copilot.providers import Generation, ProviderError
from app.config import get_settings
from app.schemas.copilot import AskRequest, FinderEventFocus, MitigationFocus, ScenarioFocus
from app.schemas.finder import OptimiseRequest
from app.services.state import get_state

TOP = "node:grid_nl:drought"          # top hidden-only event on the default data
FRAGILE = "node:farm_cocoa_ci:drought"


class Stub:
    name = "stub"

    def __init__(self, text=None, exc=None):
        self.text, self.exc = text, exc

    def generate(self, sheet, question):
        if self.exc:
            raise self.exc
        return Generation(self.text if isinstance(self.text, str) else json.dumps(self.text), "stub-model", 5)


def reply(**sections):
    base = {s: [] for s in ("answer", "why_it_matters", "how_it_propagates", "holdings_affected", "mitigations", "uncertainty")}
    for k, v in sections.items():
        base[k] = [{"text": t, "cites": c} for t, c in v]
    return {"sections": base, "unsupported": []}


GOOD = reply(answer=[("{{event_label}} takes {{impact_network}} of annual value added from the portfolio in the model.", ["event_label", "impact_network"])],
             uncertainty=[("{{notice_unvalidated}}", ["notice_unvalidated"])])


@pytest.fixture(scope="module")
def ds(client):
    return get_state().dataset


@pytest.fixture(scope="module")
def top_pct(client):
    """The engine's portfolio impact for TOP as the finder API reports it (default settings), rendered as the copilot shows it."""
    api = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 200, "top_k": 100}).json()
    ev = next(e for e in api["hidden_only_events"] if e["id"] == TOP)
    return f"{ev['portfolio_network_impact'] * 100:.2f}%"


def ask(ds, text=None, exc=None, focus=None, question=None):
    req = AskRequest(focus=focus or FinderEventFocus(event_id=TOP), **({"question": question} if question else {}))
    return service.ask(ds, req, get_settings(), provider_obj=Stub(text, exc))


def all_text(r):
    return " ".join(s.text for v in r.sections.values() for s in v)


# ---- grounding against known API results ---------------------------------------------------------------------------------
def test_grounded_reply_is_rendered_with_engine_values(client, ds):
    api = client.post("/api/v1/analysis/reverse-stress", json={"stability_draws": 200, "top_k": 100}).json()
    ev = next(e for e in api["hidden_only_events"] if e["id"] == TOP)
    r = ask(ds, GOOD)
    assert r.mode == "llm" and r.validation["accepted"] and r.model == "stub-model"
    assert f"{ev['portfolio_network_impact'] * 100:.2f}%" in r.sections["answer"][0].text
    assert ev["label"] in r.sections["answer"][0].text
    f = {x.id: x for x in r.facts}
    assert f["impact_network"].value == ev["portfolio_network_impact"] and f["impact_network"].source.endswith("portfolio_network_impact")
    assert f["p_top5"].value == ev["p_top5"] and f["hidden_share"].value == ev["hidden_share"]


def test_fact_values_match_scenario_and_optimiser_results(client, ds):
    run = client.post("/api/v1/scenarios/sc_rotterdam_port_flood/run").json()
    facts = {f["id"]: f for f in client.post("/api/v1/copilot/facts", json={"focus": {"kind": "scenario", "scenario_id": "sc_rotterdam_port_flood"}}).json()["facts"]}
    assert facts["loss_total"]["value"] == run["summary"]["total_loss_musd"] and facts["impact_network"]["value"] == run["comparison"]["portfolio_network_impact"]
    opt = client.post("/api/v1/mitigation/optimise", json={"budget_musd": 3.0, "exhaustive_check": True, "robustness_draws": 50}).json()
    mf = {f["id"]: f for f in client.post("/api/v1/copilot/facts", json={"focus": {"kind": "mitigation_plan", "optimise": {"budget_musd": 3.0, "exhaustive_check": True, "robustness_draws": 50}}}).json()["facts"]}
    assert mf["tail_before"]["value"] == opt["baseline_objective"] and mf["tail_after"]["value"] == opt["plan_objective"] and mf["cost_plan"]["value"] == opt["plan_cost_musd"]
    assert mf["residual_1_label"]["value"] == opt["residual_events"][0]["label"]


def test_optimiser_residual_events_is_additive(client):
    opt = client.post("/api/v1/mitigation/optimise", json={"budget_musd": 2.0}).json()
    assert len(opt["residual_events"]) == 5 and {"baseline_impact", "after_impact", "label"} <= set(opt["residual_events"][0])
    assert {"baseline_objective", "plan_objective", "reduction_fraction", "plan", "exhaustive", "cost_sensitivity", "robustness"} <= set(opt)   # existing keys intact


# ---- the model cannot override or invent ----------------------------------------------------------------------------------
@pytest.mark.parametrize("bad,code", [
    (reply(answer=[("{{event_label}} costs the portfolio 9.9 of value.", ["event_label"])]), "literal_number"),
    (reply(answer=[("{{event_label}} costs the portfolio {{impact_network}} which is 50% worse.", ["event_label", "impact_network"])]), "literal_number"),
    (reply(answer=[("{{event_label}} costs the portfolio a hundred of value.", ["event_label"])]), "number_word"),
    (reply(answer=[("{{event_label}} costs the portfolio $5M in value.", ["event_label"])]), "literal_unit_symbol"),
    (reply(answer=[("{{ghost_fact}} matters.", ["ghost_fact"])]), "unknown_placeholder"),
    (reply(answer=[("{{event_label}} matters here.", ["event_label", "ghost"])]), "unknown_cite"),
    (reply(answer=[("{{event_label}} hurts Nestle Holdings badly.", ["event_label"])]), "proper_noun_not_from_facts"),
    (reply(answer=[("{{event_label}} is likely to repeat.", ["event_label"])]), "forbidden_claim_word"),
    (reply(answer=[("{{event_label}} is a forecast of loss.", ["event_label"])]), "forbidden_claim_word"),
    (reply(answer=[("{{event_label}} saves the portfolio money.", ["event_label"])]), "forbidden_claim_word"),
    (reply(answer=[("The result is empirically validated.", ["notice_unvalidated"])]), "forbidden_claim_word"),
    (reply(answer=[("It spreads from the supplier to a retailer -> and onwards.", ["event_label"])]), "markup_or_url"),
])
def test_invalid_reply_is_rejected_and_engine_values_remain(ds, top_pct, bad, code):
    bad["sections"]["uncertainty"] = [{"text": "{{notice_unvalidated}}", "cites": ["notice_unvalidated"]}]
    r = ask(ds, bad)
    assert r.mode == "deterministic" and code in r.validation["violations"] and r.fallback_reason.startswith("model reply failed grounding validation")
    txt = all_text(r)
    assert "9.9" not in txt and "50%" not in txt and "Nestle" not in txt and "$5M" not in txt
    assert top_pct in r.sections["answer"][0].text      # the engine's number is what the user sees


def test_placeholder_missing_from_cites_is_normalised_but_unknown_ones_are_not(ds, top_pct):
    unc = [("{{notice_unvalidated}}", ["notice_unvalidated"])]
    r = ask(ds, reply(answer=[("{{event_label}} matters {{impact_network}}.", ["event_label"])], uncertainty=unc))
    assert r.mode == "llm" and top_pct in r.sections["answer"][0].text and "impact_network" in r.sections["answer"][0].cites
    assert "unvalidated_model_output" in r.sections["answer"][0].provenance       # the added cite drives the provenance label
    assert ask(ds, reply(answer=[("{{ghost_fact}} matters.", ["event_label"])], uncertainty=unc)).mode == "deterministic"


def test_server_always_adds_stability_and_validation_statements_to_model_answers(ds):
    r = ask(ds, GOOD)
    unc = [s for s in r.sections["uncertainty"]]
    assert all(s.template for s in unc[:2]) and "no empirical validation" in " ".join(s.text for s in unc).lower()
    assert "robust" in unc[0].text.lower() and "model_robustness" in unc[0].provenance


def test_prompt_hides_names_numbers_and_notices_from_the_model(ds):
    from app.copilot.providers import build_prompt
    sheet = service.build_sheet(ds, FinderEventFocus(event_id=TOP))
    prompt = build_prompt(sheet, "Explain.")
    fact_part = prompt.split("QUESTION:")[0]
    assert "Utrecht" not in fact_part and "Dutch Regional" not in fact_part and "1.13" not in fact_part and "$" not in fact_part
    assert "path_1 |" in fact_part and "<name>" in fact_part and "<notice>" in fact_part
    assert re.search(r"p_top5 \| .* \| RANK-STABILITY \| high", fact_part)          # stability is a band, not a number


def test_invented_graph_path_is_rejected(ds):
    bad = reply(how_it_propagates=[("The shock flows from Hamburg Coffee Roasters to Antwerp Chocolatier and then to Albion Supermarkets.", ["path_1"])],
                answer=[("{{event_label}} matters.", ["event_label"])], uncertainty=[("{{notice_unvalidated}}", ["notice_unvalidated"])])
    r = ask(ds, bad)
    assert r.mode == "deterministic" and "proper_noun_not_from_facts" in r.validation["violations"]
    assert "Hamburg Coffee Roasters to" not in all_text(r)


def test_required_sections_are_enforced(ds):
    r = ask(ds, reply(answer=[("{{event_label}} matters.", ["event_label"])]))          # no uncertainty section
    assert r.mode == "deterministic" and "missing_uncertainty_section" in r.validation["violations"]
    r = ask(ds, reply(uncertainty=[("{{notice_unvalidated}}", ["notice_unvalidated"])]))   # no answer
    assert "missing_answer" in r.validation["violations"]


def test_mitigation_sentence_must_cite_mitigation_evidence(ds):
    bad = reply(answer=[("{{event_label}} matters.", ["event_label"])], mitigations=[("Protecting the grid would help.", ["event_label"])],
                uncertainty=[("{{notice_unvalidated}}", ["notice_unvalidated"])])
    assert "mitigation_without_mitigation_fact" in ask(ds, bad).validation["violations"]


# ---- failure modes: malformed, timeout, unavailable ------------------------------------------------------------------------
@pytest.mark.parametrize("text,exc,reason", [
    ("this is not json", None, "invalid_json"),
    ('{"sections": {"answer": "oops"}}', None, "schema_mismatch"),
    (json.dumps({"sections": {"nonsense": [{"text": "x y z", "cites": ["event_label"]}]}}), None, "schema_mismatch"),
    ("```json\n{broken", None, "invalid_json"),
    (None, ProviderError("timeout", "no reply within 90s"), "provider unavailable (timeout)"),
    (None, ProviderError("unreachable", "ConnectError"), "provider unavailable (unreachable)"),
    (None, ProviderError("model_missing", "qwen3:8b"), "provider unavailable (model_missing)"),
    (None, ProviderError("not_configured", "no key"), "provider unavailable (not_configured)"),
    (None, RuntimeError("boom"), "unexpected provider error"),
])
def test_provider_failures_fall_back_safely(ds, top_pct, text, exc, reason):
    r = ask(ds, text, exc)
    assert r.mode == "deterministic" and reason in r.fallback_reason and r.provider == "deterministic" and r.model is None
    assert r.validation["attempted"] and r.validation["accepted"] is False
    assert top_pct in r.sections["answer"][0].text and all(s.template for v in r.sections.values() for s in v)


def test_fenced_json_is_accepted_when_valid(ds):
    assert ask(ds, "```json\n" + json.dumps(GOOD) + "\n```").mode == "llm"


def test_api_without_a_model_is_deterministic_and_reports_status(client):
    j = client.post("/api/v1/copilot/ask", json={"focus": {"kind": "finder_event", "event_id": TOP}}).json()
    assert j["mode"] == "deterministic" and j["fallback_reason"] == "deterministic provider selected"
    st = client.get("/api/v1/copilot/status").json()
    assert st["configured_provider"] == "deterministic" and st["deterministic"] is True and "reachable" in st["ollama"] and st["anthropic"]["configured"] is False
    j = client.post("/api/v1/copilot/ask", json={"focus": {"kind": "finder_event", "event_id": TOP}, "provider": "anthropic"}).json()
    assert j["mode"] == "deterministic" and "not_configured" in j["fallback_reason"]       # paid provider is never required


def test_api_errors(client):
    assert client.post("/api/v1/copilot/ask", json={"focus": {"kind": "finder_event", "event_id": "node:ghost:flood"}}).status_code == 404
    assert client.post("/api/v1/copilot/ask", json={"focus": {"kind": "scenario", "scenario_id": "nope"}}).status_code == 404
    assert client.post("/api/v1/copilot/ask", json={"focus": {"kind": "bogus"}}).status_code == 422
    assert client.post("/api/v1/copilot/ask", json={"focus": {"kind": "scenario", "scenario_id": "sc_punjab_flood"}, "question": "x"}).status_code == 422
    assert client.post("/api/v1/copilot/ask", json={"focus": {"kind": "scenario", "scenario_id": "sc_punjab_flood"}, "provider": "gpt"}).status_code == 422
    assert client.post("/api/v1/copilot/facts", json={"focus": {"kind": "mitigation_plan", "optimise": {"budget_musd": -1}}}).status_code == 422


# ---- missing evidence, unsupported questions -------------------------------------------------------------------------------
@pytest.mark.parametrize("q,code", [
    ("How likely is this to happen?", "probability"), ("What is the probability of this drought?", "probability"),
    ("Can you forecast next year?", "forecast"), ("How much money would we save?", "savings"), ("What is the ROI of the plan?", "savings"),
    ("Is this validated against real losses?", "real_world_validation"), ("How accurate is this?", "real_world_validation"),
    ("What should a risk manager do first?", "advice"), ("What do you recommend?", "advice"), ("What is the worst-case loss?", "worst_case"),
])
def test_unsupported_questions_are_declined_by_the_server(ds, q, code):
    r = ask(ds, None, ProviderError("timeout"), question=q)          # even with no model the server classifies the question
    assert grounding.UNSUPPORTED_MESSAGES[code] in r.unsupported


def test_model_cannot_remove_the_server_side_decline(ds):
    r = ask(ds, GOOD, question="How much would we save and how likely is it?")
    assert r.mode == "llm" and grounding.UNSUPPORTED_MESSAGES["savings"] in r.unsupported and grounding.UNSUPPORTED_MESSAGES["probability"] in r.unsupported


def test_no_mitigation_evidence_is_stated_not_invented(ds):
    sheet = service.build_sheet(ds, FinderEventFocus(event_id=TOP))
    for k in [k for k in sheet.facts if k.startswith(("mit_", "residual_loss"))]:
        del sheet.facts[k]
    out = service._template_answer(sheet, "x")
    assert len(out["mitigations"]) == 1 and "No mitigation evidence" in out["mitigations"][0].text


# ---- robust rankings vs unvalidated magnitudes -----------------------------------------------------------------------------
def test_robust_wording_requires_a_stability_fact_and_no_magnitude(ds):
    unc = [("{{notice_unvalidated}}", ["notice_unvalidated"])]
    assert ask(ds, reply(answer=[("The ranking is robust under the draws: {{p_top5}} of {{stability_draws}}.", ["p_top5", "stability_draws"])], uncertainty=unc)).mode == "llm"
    for text, cites, code in [
        ("The ranking is robust.", ["event_label"], "stability_claim_without_stability_fact"),
        ("The loss of {{impact_network}} is robust, with {{p_top5}} of draws.", ["impact_network", "p_top5"], "stability_claim_mixed_with_magnitude"),
        ("{{event_label}} is a stable loss estimate.", ["event_label"], "stability_claim_without_stability_fact"),
    ]:
        r = ask(ds, reply(answer=[(text, cites)], uncertainty=unc))
        assert r.mode == "deterministic" and code in r.validation["violations"], (text, r.validation)


def test_robust_claim_contradicted_by_a_low_stability_value_is_rejected(ds):
    unc = [("{{notice_unvalidated}}", ["notice_unvalidated"])]
    r = ask(ds, reply(answer=[("The ranking is robust with {{p_top5}} of draws.", ["p_top5"])], uncertainty=unc), focus=FinderEventFocus(event_id=FRAGILE))
    assert r.mode == "deterministic" and "stability_claim_contradicted_by_value" in r.validation["violations"]


def test_fragile_wording_only_for_events_flagged_fragile(ds):
    unc = [("{{notice_unvalidated}}", ["notice_unvalidated"])]
    txt = [("This event is fragile in the ranking.", ["fragile"])]
    assert ask(ds, reply(answer=txt, uncertainty=unc), focus=FinderEventFocus(event_id=FRAGILE)).mode == "llm"
    r = ask(ds, reply(answer=txt, uncertainty=unc), focus=FinderEventFocus(event_id=TOP))
    assert r.mode == "deterministic" and "fragile_claim_unsupported" in r.validation["violations"]


def test_template_wording_matches_stability_of_the_event(ds):
    top = service._template_answer(service.build_sheet(ds, FinderEventFocus(event_id=TOP)), "x")
    frag = service._template_answer(service.build_sheet(ds, FinderEventFocus(event_id=FRAGILE)), "x")
    t_top = " ".join(s.text for s in top["uncertainty"]).lower()
    t_frag = " ".join(s.text for s in frag["uncertainty"]).lower()
    assert "robust" in t_top and "fragile" not in t_top
    assert "fragile" in t_frag and "robust" not in t_frag
    for out in (top, frag):
        assert "no empirical validation" in " ".join(s.text for s in out["uncertainty"]).lower()           # magnitudes are always declared unvalidated


def test_magnitude_sentences_are_labelled_unvalidated_model_output_and_nothing_is_called_validated(ds):
    for focus in (FinderEventFocus(event_id=TOP), ScenarioFocus(scenario_id="sc_brazil_drought"), MitigationFocus(optimise=OptimiseRequest(budget_musd=3.0))):
        r = service.ask(ds, AskRequest(focus=focus), get_settings(), provider_obj=None)
        for sents in r.sections.values():
            for s in sents:
                assert "empirically_validated" not in s.provenance
                if any(re.search(r"\$|%", s.text) for _ in [0]) and any(c.startswith(("impact_", "loss_", "tail_")) for c in s.cites):
                    assert "unvalidated_model_output" in s.provenance
        assert all(f.provenance != "empirically_validated" for f in r.facts)


def test_synthetic_and_real_data_are_distinguished(ds):
    r = service.ask(ds, AskRequest(focus=FinderEventFocus(event_id="node:port_rtm:flood")), get_settings(), provider_obj=None)
    prov = {f.id: f.provenance for f in r.facts}
    assert prov["jrc_check"] == "real_hazard_context" and prov["holding_1_name"] == "synthetic_input" and prov["event_intensity"] == "model_assumption"
    assert prov["impact_network"] == "unvalidated_model_output" and prov["p_top5"] == "model_robustness"
    assert any(s.text.startswith("The JRC") and "real_hazard_context" in s.provenance for s in r.sections["uncertainty"])


# ---- nothing fabricated: every number, name and path traces to a fact -----------------------------------------------------
@pytest.mark.parametrize("focus", [FinderEventFocus(event_id=TOP), FinderEventFocus(event_id=FRAGILE), FinderEventFocus(event_id="node:port_rtm:flood"),
                                    ScenarioFocus(scenario_id="sc_rotterdam_port_flood"), ScenarioFocus(scenario_id="sc_brazil_drought"),
                                    MitigationFocus(optimise=OptimiseRequest(budget_musd=3.0, exhaustive_check=True, robustness_draws=30))])
def test_every_rendered_number_and_name_comes_from_a_cited_fact(ds, focus):
    r = service.ask(ds, AskRequest(focus=focus), get_settings(), provider_obj=None)
    facts = {f.id: f for f in r.facts}
    for sec, sents in r.sections.items():
        for s in sents:
            cited_text = " ".join(facts[c].rendered for c in s.cites)
            for num in re.findall(r"\$?\d[\d,]*\.?\d*[%M]?|\d", s.text):
                assert num in cited_text, (sec, s.text, num)
            for tok in re.findall(r"\b[A-Z][a-z]{2,}\b", s.text):
                assert tok in cited_text or s.text.startswith(tok) or tok in ("JRC",), (sec, tok, s.text)
    # templates pass the same validator a model reply would
    sheet = service.build_sheet(ds, focus)
    assert grounding.validate(sheet, narrative.build(sheet, "x")).ok


def test_paths_come_from_the_engine_not_the_text(ds):
    sheet = service.build_sheet(ds, FinderEventFocus(event_id=TOP))
    run_paths = sheet.facts["path_1"].value
    assert run_paths.startswith("Dutch Regional Grid Operator") and "→" in run_paths
    r = service.ask(ds, AskRequest(focus=FinderEventFocus(event_id=TOP)), get_settings(), provider_obj=None)
    assert run_paths in r.sections["how_it_propagates"][0].text


# ---- executive report ------------------------------------------------------------------------------------------------------
def test_report_is_deterministic_with_evidence_table_and_caveats(client, top_pct):
    j = client.post("/api/v1/copilot/report", json={"focus": {"kind": "finder_event", "event_id": TOP}}).json()
    md = j["markdown"]
    assert j["mode"] == "deterministic" and md.startswith("# Executive summary: Hidden exposure")
    assert "## Evidence table" in md and "`events[].portfolio_network_impact`" in md and "## Standing notes" in md and top_pct in md
    assert "not forecasts" in md and "validated against observed losses" in md and "empirically_validated" not in md


def test_report_with_model_uses_it_only_if_valid(ds, top_pct):
    ok = service.report(ds, FinderEventFocus(event_id=TOP), get_settings(), use_model=True, provider_obj=Stub(GOOD))
    assert ok.mode == "llm" and f"takes {top_pct} of annual value added" in ok.markdown
    bad = service.report(ds, FinderEventFocus(event_id=TOP), get_settings(), use_model=True, provider_obj=Stub(reply(answer=[("It costs 5 dollars.", ["event_label"])])))
    assert bad.mode == "deterministic" and "grounding validation" in bad.fallback_reason and "5 dollars" not in bad.markdown


def test_facts_endpoint_exposes_provenance_and_sources(client):
    j = client.post("/api/v1/copilot/facts", json={"focus": {"kind": "finder_event", "event_id": "node:port_rtm:flood"}}).json()
    assert j["focus_kind"] == "finder_event" and len(j["standing_notes"]) == 4
    assert all(f["source"] and f["provenance"] in ("synthetic_input", "model_assumption", "real_hazard_context", "unvalidated_model_output", "model_robustness") for f in j["facts"])


def test_model_declining_an_unsupported_question_is_accepted_and_server_answers(ds, top_pct):
    declined = reply(uncertainty=[("{{notice_unvalidated}}", ["notice_unvalidated"])])
    declined["unsupported"] = ["probability", "savings"]
    r = ask(ds, declined, question="How likely is it and how much would we save?")
    assert r.mode == "llm" and r.sections["answer"] and r.sections["answer"][0].template and top_pct in r.sections["answer"][0].text
    assert grounding.UNSUPPORTED_MESSAGES["probability"] in r.unsupported and grounding.UNSUPPORTED_MESSAGES["savings"] in r.unsupported
    # an empty answer WITHOUT declining anything is still rejected
    assert "missing_answer" in ask(ds, reply(uncertainty=[("{{notice_unvalidated}}", ["notice_unvalidated"])])).validation["violations"]
    # a bogus unsupported code is rejected
    bad = reply(uncertainty=[("{{notice_unvalidated}}", ["notice_unvalidated"])]); bad["unsupported"] = ["because"]
    assert "bad_unsupported_code" in ask(ds, bad).validation["violations"]


def test_prompt_labels_and_values_contain_no_digits(ds):
    from app.copilot.providers import build_prompt
    for focus in (FinderEventFocus(event_id=TOP), ScenarioFocus(scenario_id="sc_brazil_drought"), MitigationFocus(optimise=OptimiseRequest(budget_musd=3.0))):
        lines = build_prompt(service.build_sheet(ds, focus), "Explain.").split("FACT SHEET")[1].split("QUESTION")[0].strip().split("\n")[1:]
        assert len(lines) > 15
        for ln in lines:
            _id, label, tag, value = ln.split(" | ")
            assert not re.search(r"\d", label + value), ln          # ids may contain digits (holding_1); labels and values never do


def test_magnitude_sentences_always_carry_a_modelled_value_hedge(ds):
    unc = [("{{notice_unvalidated}}", ["notice_unvalidated"])]
    r = ask(ds, reply(answer=[("{{event_label}} causes {{loss_total}} through network effects.", ["event_label", "loss_total"])], uncertainty=unc))
    assert r.mode == "llm" and "modelled value, not validated" in r.sections["answer"][0].text and "$159.6M" in r.sections["answer"][0].text
    ok = ask(ds, reply(answer=[("In the model, {{event_label}} takes {{impact_network}} from the portfolio.", ["event_label", "impact_network"])], uncertainty=unc))
    assert "modelled value" not in ok.sections["answer"][0].text            # already hedged by its own wording: not doubled
    nomag = ask(ds, reply(answer=[("{{event_label}} is a synthetic reference event.", ["event_label"])], uncertainty=unc))
    assert "modelled value" not in nomag.sections["answer"][0].text


def test_advice_and_recommendation_words_are_forbidden_in_model_text(ds):
    unc = [("{{notice_unvalidated}}", ["notice_unvalidated"])]
    for txt in ("A manager should first review {{event_label}}.", "We recommend protecting {{event_label}}.", "{{event_label}} must be addressed."):
        r = ask(ds, reply(answer=[(txt, ["event_label"])], uncertainty=unc))
        assert r.mode == "deterministic" and "forbidden_claim_word" in r.validation["violations"], txt


def test_server_declines_advice_and_worst_case_even_when_the_model_answers(ds):
    r = ask(ds, GOOD, question="What should we do first, and what is the worst-case loss?")
    assert grounding.UNSUPPORTED_MESSAGES["advice"] in r.unsupported and grounding.UNSUPPORTED_MESSAGES["worst_case"] in r.unsupported


def test_mitigation_focus_without_holdings_declares_missing_evidence(ds):
    r = service.ask(ds, AskRequest(focus=MitigationFocus(optimise=OptimiseRequest(budget_musd=3.0)), question="Which holdings are most exposed?"), get_settings(), provider_obj=None)
    assert grounding.UNSUPPORTED_MESSAGES["other_no_evidence"] in r.unsupported


def test_word_real_requires_a_real_hazard_context_citation(ds):
    unc = [("{{notice_unvalidated}}", ["notice_unvalidated"])]
    focus = FinderEventFocus(event_id="node:port_rtm:flood")
    bad = ask(ds, reply(answer=[("{{event_label}} reflects a real disruption.", ["event_label"])], uncertainty=unc), focus=focus)
    assert bad.mode == "deterministic" and "real_claim_without_real_data_fact" in bad.validation["violations"]
    ok = ask(ds, reply(answer=[("The hazard map gives real context here: {{jrc_check}}.", ["jrc_check"])], uncertainty=unc), focus=focus)
    assert ok.mode == "llm" and "real_hazard_context" in ok.sections["answer"][0].provenance


def test_prompt_omits_the_ambiguous_direct_hit_count(ds):
    from app.copilot.providers import build_prompt
    sheet = service.build_sheet(ds, FinderEventFocus(event_id=TOP))
    assert sheet.has("entities_hit_directly") and "entities_hit_directly" not in build_prompt(sheet, "Explain.")     # kept as evidence, hidden from the model
    assert "zero means no holding is hit directly" in sheet.facts["impact_location"].label
