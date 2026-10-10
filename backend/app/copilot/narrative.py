"""Deterministic template narrative. Produces exactly the same structure as an accepted model reply (placeholders + cites), so it is
rendered and validated by the same code. Used as the always-available fallback and as the default when no provider is reachable."""
from __future__ import annotations

from ..schemas.copilot import SECTIONS
from .facts import FactSheet
from .grounding import LLMAnswer, LLMSentence


def _s(text: str, *cites: str) -> LLMSentence:
    return LLMSentence(text=text, cites=list(cites))


def _present(sheet: FactSheet, *ids: str) -> bool:
    return all(sheet.has(i) for i in ids)


def _holdings(sheet: FactSheet, k: int = 2):
    out = []
    for i in range(1, k + 1):
        if _present(sheet, f"holding_{i}_name", f"holding_net_{i}"):
            out.append(i)
    return out


def _uncertainty(sheet: FactSheet) -> list[LLMSentence]:
    out: list[LLMSentence] = []
    if sheet.has("fragile") and sheet.facts["fragile"].value is True:
        out.append(_s("The ranking of this event is fragile: it keeps a leading rank in {{p_top5}} of {{stability_draws}} parameter draws.", "fragile", "p_top5", "stability_draws"))
    elif sheet.has("p_top5") and sheet.facts["p_top5"].value >= 0.9:
        out.append(_s("The ranking is robust under the model's own parameter draws: the event keeps a leading rank among {{ranking_list}} in {{p_top5}} of {{stability_draws}} draws.", "ranking_list", "p_top5", "stability_draws"))
    elif sheet.has("p_top5"):
        out.append(_s("Under the model's own parameter draws the event keeps a leading rank among {{ranking_list}} in only {{p_top5}} of {{stability_draws}} draws, so its position is uncertain.", "ranking_list", "p_top5", "stability_draws"))
    elif sheet.has("robust_positive"):
        word = "robust" if sheet.facts["robust_positive"].value >= 0.9 else "uncertain"
        out.append(_s("The plan's benefit is " + word + " under the parameter draws: it lowers the tail impact in {{robust_positive}} of {{robust_draws}} draws, a result about the plan and not a measured outcome.", "robust_positive", "robust_draws"))
    elif sheet.has("mc_runs"):
        out.append(_s("Across {{mc_runs}} draws the modelled scenario loss runs from {{loss_mc_p05}} to {{loss_mc_p95}}, a scenario-uncertainty range and not a confidence interval.", "mc_runs", "loss_mc_p05", "loss_mc_p95"))
    out.append(_s("{{notice_unvalidated}}", "notice_unvalidated"))
    if sheet.has("jrc_check"):
        out.append(_s("The JRC river-flood map is real hazard context and is lenient here: {{jrc_check}}, and only {{jrc_base_rate}} entities show any modelled flooding.", "jrc_check", "jrc_base_rate"))
    else:
        out.append(_s("{{notice_synthetic}}", "notice_synthetic"))
    return out[:3]


def build(sheet: FactSheet, question: str) -> LLMAnswer:
    sec: dict[str, list[LLMSentence]] = {k: [] for k in SECTIONS}
    k = sheet.focus_kind
    if k == "finder_event":
        sec["answer"] = [_s("In the model, {{event_label}} takes {{impact_network}} of annual value added from the portfolio, of which {{hidden_share}} would not show up in a location-only check.",
                            "event_label", "impact_network", "hidden_share")]
        if sheet.facts["hidden_only"].value is True:
            sec["why_it_matters"] = [_s("No holding is hit directly, yet {{holdings_affected}} holdings are disrupted through supply links, so a screen of the holdings' own sites would show {{impact_location}}.",
                                        "hidden_only", "holdings_affected", "impact_location")]
        else:
            sec["why_it_matters"] = [_s("Direct damage accounts for {{impact_location}} of the portfolio and propagation through supply links extends it to {{impact_network}}, reaching {{holdings_affected}} holdings.",
                                        "impact_location", "impact_network", "holdings_affected")]
        if sheet.has("path_1"):
            sec["how_it_propagates"] = [_s("The dominant path runs {{path_1}}, with a cumulative transmission of {{path_1_transmission}}, a path diagnostic and not a share of the loss.", "path_1", "path_1_transmission")]
        elif sheet.has("no_path"):
            sec["how_it_propagates"] = [_s("{{no_path}}.", "no_path")]
    elif k == "scenario":
        sec["answer"] = [_s("In the model, {{scenario_name}} causes {{loss_total}} of value-added loss across the network, of which {{loss_indirect_total}} arrives through supply links.",
                            "scenario_name", "loss_total", "loss_indirect_total")]
        sec["why_it_matters"] = [_s("A location-only view gives the portfolio {{impact_location}} while the network-aware view gives {{impact_network}}, with {{holdings_hidden_count}} holdings carrying hidden exposure.",
                                    "impact_location", "impact_network", "holdings_hidden_count")]
        if sheet.has("path_1"):
            sec["how_it_propagates"] = [_s("The dominant path to a holding runs {{path_1}}, with a cumulative transmission of {{path_1_transmission}}, a diagnostic and not a share of the loss.", "path_1", "path_1_transmission")]
        else:
            sec["how_it_propagates"] = [_s("Propagation reaches {{entities_downstream}} entities only through supply links; first-order evidence: {{evidence_order1}}", "entities_downstream", "evidence_order1")]
    else:  # mitigation_plan
        sec["answer"] = [_s("Within a budget of {{budget}}, the plan lowers the mean portfolio impact of the worst events from {{tail_before}} to {{tail_after}} in the model, at a placeholder cost of {{cost_plan}}.",
                            "budget", "tail_before", "tail_after", "cost_plan")]
        sec["why_it_matters"] = [_s("It was searched against {{events_considered}} distinct synthetic events, and the plan has {{plan_size}} interventions.", "events_considered", "plan_size")]
        if sheet.has("exhaustive_plans"):
            sec["how_it_propagates"] = [_s("Brute force over {{exhaustive_plans}} affordable plans within the stated pool finds nothing better, an optimality gap of {{optimality_gap}}.", "exhaustive_plans", "optimality_gap")]
    hs = _holdings(sheet)
    if hs:
        i, j = hs[0], hs[-1]
        txt = "The most affected holding is {{holding_%d_name}} at {{holding_net_%d}} disruption" % (i, i)
        cites = [f"holding_{i}_name", f"holding_net_{i}"]
        if j != i:
            txt += ", followed by {{holding_%d_name}} at {{holding_net_%d}}" % (j, j)
            cites += [f"holding_{j}_name", f"holding_net_{j}"]
        sec["holdings_affected"] = [_s(txt + ".", *cites)]
        m = next((x for x in hs if sheet.has(f"holding_{x}_structure")), None)     # first company among them with several business units
        if m is not None:
            txt = ("{{holding_%d_name}} is {{holding_%d_structure}}, so its disruption is the value-added-weighted average of its business units" % (m, m))
            cites = [f"holding_{m}_name", f"holding_{m}_structure"]
            if sheet.has(f"holding_net_{m}_if_other_hit"):
                txt += ", or {{holding_net_%d_if_other_hit}} if those other businesses were hit as hard" % m
                cites.append(f"holding_net_{m}_if_other_hit")
            sec["holdings_affected"].append(_s(txt + ".", *cites))
    if sheet.has("mit_1_label") and sheet.has("mit_1_reduction"):
        sec["mitigations"] = [_s("In the model, {{mit_1_label}} lowers the scenario value-added loss by {{mit_1_reduction}} at an annualised placeholder cost of {{mit_1_cost}}.", "mit_1_label", "mit_1_reduction", "mit_1_cost")]
        if sheet.has("residual_loss"):
            sec["mitigations"].append(_s("With no intervention the scenario loss stays at {{residual_loss}}.", "residual_loss"))
    elif k == "mitigation_plan" and sheet.has("mit_1_label"):
        sec["mitigations"] = [_s("The plan starts with {{mit_1_label}} at an annualised placeholder cost of {{mit_1_cost}}.", "mit_1_label", "mit_1_cost")]
        if sheet.has("residual_1_label"):
            sec["mitigations"].append(_s("The largest residual event is {{residual_1_label}}, still at {{residual_1_after}} after the plan, down from {{residual_1_before}}.",
                                         "residual_1_label", "residual_1_after", "residual_1_before"))
    sec["uncertainty"] = _uncertainty(sheet)
    return LLMAnswer(sections=sec, unsupported=[])
