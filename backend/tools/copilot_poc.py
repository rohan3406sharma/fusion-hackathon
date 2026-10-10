"""Proof of concept: real Ollama through the full ask() path (fact sheet -> model -> grounding validator -> fallback).
Usage:  cd backend && PYTHONPATH=. ../.venv/bin/python tools/copilot_poc.py out.json [--repeat N]
Records, per (fact sheet, question): JSON parse, schema, validator outcome and violation codes, sentence-level pass rate, fallback."""
import json, sys, time
from collections import Counter
from app.config import get_settings
from app.domain.dataset import FnbDataset
from app.copilot import service
from app.schemas.copilot import AskRequest, FinderEventFocus, MitigationFocus, ScenarioFocus
from app.schemas.finder import FinderRequest, OptimiseRequest
from app.services.finder import run_finder

ds = FnbDataset.load(get_settings().data_dir)
res = run_finder(ds, FinderRequest(stability_draws=200, top_k=100))
hid = {e.id: e for e in res.hidden_only_events}
fragile = next(e for e in res.hidden_only_events if e.fragile)
focuses = {
    "finder: top hidden-only (grid drought)": FinderEventFocus(event_id=res.hidden_only_events[0].id),
    "finder: fragile hidden-only": FinderEventFocus(event_id=fragile.id),
    "finder: Rotterdam terminal flood (JRC check)": FinderEventFocus(event_id="node:port_rtm:flood"),
    "finder: overall #1 (all-events list)": FinderEventFocus(event_id=res.events[0].id),
    "scenario: Rotterdam terminal flood": ScenarioFocus(scenario_id="sc_rotterdam_port_flood"),
    "scenario: Brazil drought": ScenarioFocus(scenario_id="sc_brazil_drought"),
    "mitigation: budget 3": MitigationFocus(optimise=OptimiseRequest(budget_musd=3.0, exhaustive_check=True, robustness_draws=50)),
    "mitigation: budget 2": MitigationFocus(optimise=OptimiseRequest(budget_musd=2.0, exhaustive_check=True, robustness_draws=50)),
}
questions = {
    "explain": "Explain why this matters, how it propagates, what could help and what is uncertain.",
    "holdings": "Which holdings are most exposed and why?",
    "unsupported_prob_savings": "How likely is this to happen, and how much money would we save by mitigating it?",
    "unsupported_validation": "Is this result validated against real losses?",
}
if "--holdout" in sys.argv:       # questions NOT used while tuning the prompt, on a subset of the sheets
    questions = {
        "board_summary": "Summarise this for a board member in plain language.",
        "why_ranked": "Why is this ranked where it is?",
        "first_action": "What should a risk manager do first?",
        "worst_case": "What is the worst-case loss?",
        "next_summer": "Will this drought happen next summer?",
        "reliable": "Are these numbers reliable?",
        "compare": "Compare the options the model evaluated.",
        "path": "Which supply path matters most?",
    }
    focuses = {k: v for k, v in focuses.items() if k.split(":")[0] in ("finder", "scenario", "mitigation") and any(t in k for t in ("top hidden-only", "fragile", "Brazil", "budget 3"))}
repeat = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 1
rows = []
for fname, focus in focuses.items():
    for qname, q in questions.items():
        for rep in range(repeat):
            t = time.time()
            r = service.ask(ds, AskRequest(focus=focus, question=q, provider="ollama"))
            rows.append(dict(focus=fname, question=qname, rep=rep, mode=r.mode, fallback_reason=r.fallback_reason, latency_s=round(time.time() - t, 1),
                             validation=r.validation, unsupported=len(r.unsupported), n_sentences=sum(len(v) for v in r.sections.values()),
                             text={k: [x.text for x in v] for k, v in r.sections.items()}, unsupported_msgs=r.unsupported))
            print(f"{fname[:44]:44s} {qname:26s} {r.mode:13s} {r.latency_ms/1000:5.1f}s {r.validation.get('details')}", flush=True)
            json.dump(rows, open(sys.argv[1], "w"), indent=1)
n = len(rows); acc = sum(1 for r in rows if r["mode"] == "llm")
chk = sum(r["validation"].get("sentences_checked", 0) for r in rows); bad = sum(r["validation"].get("sentences_failed", 0) for r in rows)
print(f"\nresponses {n}: accepted {acc} ({acc/n:.0%}), fell back {n-acc} ({(n-acc)/n:.0%}); sentences checked {chk}, failed {bad} ({bad/max(chk,1):.0%})")
print("violation codes:", Counter(c for r in rows for c in r["validation"].get("violations", [])).most_common())
print("median latency s:", sorted(r["latency_s"] for r in rows)[n // 2])
