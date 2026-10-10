"""Copilot orchestration: fact sheet -> (optional language model) -> grounding validation -> rendered answer, with safe fallback."""
from __future__ import annotations

import hashlib
import re
import time

from ..config import Settings, get_settings
from ..domain.dataset import FnbDataset
from ..domain.holdings import build_holdings
from ..schemas.copilot import (AskRequest, AskResponse, FactOut, FactsResponse, FinderEventFocus, MitigationFocus, ReportResponse,
                               ScenarioFocus, SECTIONS, StatusResponse)
from ..schemas.finder import FinderRequest
from ..schemas.scenario import ScenarioSpec
from ..services import scenarios as sc
from ..services.finder import run_finder
from ..services.optimise import run_optimise
from ..services.runner import build_run_result
from ..services.state import get_state
from . import grounding, narrative
from .facts import NOTICES, UNITS, FactSheet, finder_event_sheet, mitigation_sheet, scenario_sheet
from .providers import ProviderError, get_provider


class FocusNotFound(LookupError):
    pass


def _hash(model) -> str:
    return hashlib.sha256(model.model_dump_json().encode()).hexdigest()    # same key scheme as the API routes, so results are shared


def build_sheet(ds: FnbDataset, focus) -> FactSheet:
    st = get_state()
    if isinstance(focus, FinderEventFocus):
        req = focus.finder.model_copy(update={"top_k": 100})
        res = st.cache.get_or_set("finder:" + _hash(req), lambda: run_finder(ds, req))
        ev_h = next((e for e in res.hidden_only_events if e.id == focus.event_id), None)
        ev_a = next((e for e in res.events if e.id == focus.event_id), None)
        ev = ev_h or ev_a            # a hidden-only event is described by its rank and stability among hidden-only events
        if ev is None:
            raise FocusNotFound(f"event '{focus.event_id}' is not in the finder results for these settings")
        spec = ScenarioSpec(name=ev.label[:120], hazards=[ev.hazard_component], propagation_max_depth=focus.finder.max_depth)
        hs = build_holdings(ds, focus.finder.weights, focus.finder.holding_view)
        run = build_run_result(ds.entities, ds.relations, spec, None, 50, focus.finder.max_depth, ds.portfolio_weights, hs)
        return finder_event_sheet(ds, focus, res, hs.owned, run, spec, ev, "hidden-only events" if ev_h else "all events", ev_a.rank if (ev_h and ev_a) else None)
    if isinstance(focus, ScenarioFocus):
        try:
            sid, spec = sc.resolve(focus.scenario_id, None)
        except Exception as e:  # noqa: BLE001
            raise FocusNotFound(f"scenario '{focus.scenario_id}' not found") from e
        run = sc.run(spec, sid, focus.max_depth, 50, focus.holding_view)
        mc = sc.monte_carlo(spec, max(20, spec.monte_carlo_runs or 500), spec.monte_carlo_seed, focus.max_depth)
        return scenario_sheet(ds, focus, run, mc, build_holdings(ds, None, focus.holding_view).owned)
    assert isinstance(focus, MitigationFocus)
    opt = st.cache.get_or_set("opt:" + _hash(focus.optimise), lambda: run_optimise(ds, focus.optimise))
    return mitigation_sheet(ds, focus, opt)


def facts_out(sheet: FactSheet) -> list[FactOut]:
    return [FactOut(id=f.id, label=f.label, value=f.value, rendered=f.rendered, unit=UNITS[f.kind], provenance=f.provenance, source=f.source)  # type: ignore[arg-type]
            for f in sheet.facts.values()]


def standing_notes() -> list[str]:
    return [v[1] for v in NOTICES.values()] + [
        "Where a ranking-stability figure is shown it supports the ranking under the model's own parameter draws; loss magnitudes remain uncalibrated, "
        "unvalidated model outputs. A language model, when used, only chooses and phrases cited facts; every value, name and path is filled in by the server."]


def get_facts(ds: FnbDataset, focus) -> FactsResponse:
    sheet = build_sheet(ds, focus)
    return FactsResponse(title=sheet.title, focus_kind=sheet.focus_kind, facts=facts_out(sheet), standing_notes=standing_notes())


def _template_answer(sheet: FactSheet, question: str):
    ans = narrative.build(sheet, question)
    rendered = {sec: [grounding.render_sentence(sheet, s.text, s.cites, template=True) for s in ans.sections.get(sec, [])] for sec in SECTIONS}
    if not rendered["mitigations"]:
        rendered["mitigations"] = [grounding.render_sentence(sheet, "No mitigation evidence is available for this focus, so none is proposed.", ["notice_unvalidated"], template=True)]
    return rendered


_HOLDINGS_Q = re.compile(r"\b(holding|holdings|portfolio|exposed|exposure|affected)\b", re.I)
_PATH_Q = re.compile(r"\b(path|propagat\w*|spread\w*|chain|route)\b", re.I)
_MIT_Q = re.compile(r"\b(mitigat\w*|intervention\w*|protect\w*|plan|help|do first|should)\b", re.I)


def evidence_gaps(sheet: FactSheet, question: str) -> list[str]:
    """Deterministic check that the fact sheet contains the evidence a question needs; if not, the server says so (model-independent)."""
    gaps = []
    if _HOLDINGS_Q.search(question) and not sheet.has("holding_1_name") and sheet.focus_kind == "mitigation_plan":
        gaps.append("other_no_evidence")
    if _PATH_Q.search(question) and not (sheet.has("path_1") or sheet.focus_kind == "mitigation_plan"):
        gaps.append("other_no_evidence")
    if _MIT_Q.search(question) and not any(k.startswith(("mit_", "plan_")) for k in sheet.facts):
        gaps.append("other_no_evidence")
    return sorted(set(gaps))


def status(settings: Settings | None = None) -> StatusResponse:
    s = settings or get_settings()
    return StatusResponse(configured_provider=s.llm_provider, ollama=get_provider("ollama", s).status(), anthropic=get_provider("anthropic", s).status())


def ask(ds: FnbDataset, req: AskRequest, settings: Settings | None = None, provider_obj=None) -> AskResponse:
    s = settings or get_settings()
    sheet = build_sheet(ds, req.focus)
    unsupported = sorted(set(grounding.classify_question(req.question)) | set(evidence_gaps(sheet, req.question)))
    name = req.provider or s.llm_provider
    t0 = time.perf_counter()
    mode, fallback_reason, model, validation = "deterministic", None, None, {"attempted": False}
    rendered = None
    prov = provider_obj if provider_obj is not None else get_provider(name, s)
    if prov is None:
        fallback_reason = "deterministic provider selected" if name == "deterministic" else f"unknown provider '{name}'"
    else:
        try:
            gen = prov.generate(sheet, req.question)
            model = gen.model
            ans, err = grounding.parse_llm_json(gen.text)
            if ans is None:
                fallback_reason = f"model reply rejected: {err}"
                validation = {"attempted": True, "accepted": False, "violations": [err.split(":")[0]], "sentences_checked": 0, "sentences_failed": 0}
            else:
                v = grounding.validate(sheet, grounding.normalise(ans))
                validation = {"attempted": True, "accepted": v.ok, "violations": v.codes(), "sentences_checked": v.sentences_checked, "sentences_failed": v.sentences_failed,
                              "details": [f"{x.section}: {x.code} {x.detail}".strip() for x in v.violations[:6]]}
                if v.ok:
                    rendered = grounding.render_answer(sheet, ans)
                    for sec in SECTIONS:
                        rendered.setdefault(sec, [])
                    unsupported = sorted(set(unsupported) | set(ans.unsupported))
                    if not rendered["answer"]:                      # the model declined: the server states what the facts do support
                        rendered["answer"] = _template_answer(sheet, req.question)["answer"]
                    mode = "llm"
                else:
                    fallback_reason = "model reply failed grounding validation: " + ", ".join(v.codes())
        except ProviderError as e:
            fallback_reason = f"provider unavailable ({e.code})"
            validation = {"attempted": True, "accepted": False, "violations": [e.code], "sentences_checked": 0, "sentences_failed": 0}
        except Exception as e:  # noqa: BLE001  -- fail safe: never surface an unvalidated model answer
            fallback_reason = f"unexpected provider error ({type(e).__name__})"
            validation = {"attempted": True, "accepted": False, "violations": ["unexpected_error"], "sentences_checked": 0, "sentences_failed": 0}
    if rendered is None:
        rendered = _template_answer(sheet, req.question)
    else:
        if not rendered["mitigations"]:
            rendered["mitigations"] = _template_answer(sheet, req.question)["mitigations"]
        # server-written statements are always added, whatever the model wrote: ranking stability vs unvalidated magnitudes, and data status
        server_unc = [grounding.render_sentence(sheet, x.text, x.cites, template=True) for x in narrative._uncertainty(sheet)]
        rendered["uncertainty"] = server_unc + [s for s in rendered["uncertainty"] if s.text not in {t.text for t in server_unc}]
    msgs = [grounding.UNSUPPORTED_MESSAGES[c] for c in unsupported if c in grounding.UNSUPPORTED_MESSAGES]
    return AskResponse(title=sheet.title, question=req.question, mode=mode, provider=name if mode == "llm" else "deterministic", model=model if mode == "llm" else None,
                       fallback_reason=fallback_reason, latency_ms=int((time.perf_counter() - t0) * 1000), sections=rendered, unsupported=msgs,
                       standing_notes=standing_notes(), facts=facts_out(sheet), validation=validation)


def report(ds: FnbDataset, focus, settings: Settings | None = None, use_model: bool = False, provider_obj=None) -> ReportResponse:
    """Executive summary as Markdown. Deterministic by default; with use_model the model-phrased answer is used only if it passes validation."""
    sheet = build_sheet(ds, focus)
    mode, reason, answer = "deterministic", None, None
    if use_model:
        r = ask(ds, AskRequest(focus=focus, question="Explain why this matters, how it propagates, what could help and what is uncertain."), settings, provider_obj)
        if r.mode == "llm":
            mode, answer = "llm", r.sections
        else:
            reason = r.fallback_reason
    if answer is None:
        answer = _template_answer(sheet, "executive summary")
    heads = {"answer": "Summary", "why_it_matters": "Why it matters", "how_it_propagates": "How it propagates", "holdings_affected": "Holdings affected",
             "mitigations": "Mitigations the model can evaluate", "uncertainty": "What remains uncertain"}
    L = [f"# Executive summary: {sheet.title}", "",
         "> Synthetic demonstration data. Values below are model outputs, not forecasts, and have not been validated against observed losses.", ""]
    for sec in SECTIONS:
        if answer.get(sec):
            L += [f"## {heads[sec]}", ""] + [f"- {s.text} *[{', '.join(s.provenance)}]*" for s in answer[sec]] + [""]
    L += ["## Evidence table", "", "| Fact | Value | Provenance | Source |", "|---|---|---|---|"]
    for f in sheet.facts.values():
        if not f.id.startswith("notice_"):
            L.append(f"| {f.label} | {f.rendered} | {f.provenance} | `{f.source}` |")
    L += ["", "## Standing notes", ""] + [f"- {n}" for n in standing_notes()]
    L += ["", f"*Generated by the {'language-model phrasing (validated)' if mode == 'llm' else 'deterministic template'} layer; all numbers, names and paths come from the deterministic engine.*"]
    return ReportResponse(title=sheet.title, mode=mode, fallback_reason=reason, markdown="\n".join(L) + "\n")  # type: ignore[arg-type]
