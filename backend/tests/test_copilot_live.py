"""LIVE integration with the local Ollama model. Skipped unless FIN04_LIVE_OLLAMA=1 and Ollama is reachable:
    FIN04_LIVE_OLLAMA=1 ../.venv/bin/python -m pytest -q tests/test_copilot_live.py -s
These tests assert SAFETY invariants that must hold whatever the model writes. They do not assert a fixed acceptance rate (a model
may be rejected and replaced by templates), only that at least one real model reply is accepted so the integration is demonstrably live."""
import os
import re

import pytest

from app.config import get_settings
from app.copilot import service
from app.copilot.providers import OllamaProvider
from app.schemas.copilot import AskRequest, FinderEventFocus, MitigationFocus, ScenarioFocus
from app.schemas.finder import OptimiseRequest
from app.services.state import get_state

pytestmark = pytest.mark.skipif(os.environ.get("FIN04_LIVE_OLLAMA") != "1", reason="set FIN04_LIVE_OLLAMA=1 to run against local Ollama")
CASES = [
    (FinderEventFocus(event_id="node:grid_nl:drought"), "Explain why this matters, how it propagates, what could help and what is uncertain."),
    (ScenarioFocus(scenario_id="sc_rotterdam_port_flood"), "Which holdings are most exposed and why?"),
    (MitigationFocus(optimise=OptimiseRequest(budget_musd=3.0)), "Explain this plan for a board member."),
    (FinderEventFocus(event_id="node:grid_nl:drought"), "How likely is this, and how much would we save?"),
]


@pytest.fixture(scope="module")
def results(client):
    s = get_settings().model_copy(update={"llm_provider": "ollama", "llm_timeout_s": 150.0})
    st = OllamaProvider(s).status()
    if not (st["reachable"] and st["model_present"]):
        pytest.skip(f"Ollama model not available: {st}")
    ds = get_state().dataset
    return [service.ask(ds, AskRequest(focus=f, question=q, provider="ollama"), s) for f, q in CASES]


def test_live_model_is_used_and_at_least_one_reply_is_accepted(results):
    modes = [r.mode for r in results]
    print("\nlive modes:", modes, "latencies ms:", [r.latency_ms for r in results], "fallbacks:", [r.fallback_reason for r in results if r.fallback_reason])
    assert all(r.validation["attempted"] for r in results)
    assert "llm" in modes and all(r.model == "qwen3:8b" for r in results if r.mode == "llm")


def test_live_output_numbers_and_names_always_come_from_the_fact_sheet(results):
    for r in results:
        facts = {f.id: f for f in r.facts}
        for sents in r.sections.values():
            for s in sents:
                cited = " ".join(facts[c].rendered for c in s.cites)
                for num in re.findall(r"\$?\d[\d,]*\.?\d*[%M]?", s.text):
                    assert num in cited, (s.text, num)
                assert "empirically_validated" not in s.provenance


def test_live_unsupported_question_is_declined_by_the_server(results):
    from app.copilot.grounding import UNSUPPORTED_MESSAGES
    r = results[3]
    assert UNSUPPORTED_MESSAGES["probability"] in r.unsupported and UNSUPPORTED_MESSAGES["savings"] in r.unsupported
