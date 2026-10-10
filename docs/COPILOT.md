# AI Climate Risk Copilot

Explains hidden exposures, scenarios and mitigation plans in plain language **without ever calculating anything**. All numbers, names, paths and rankings come from the deterministic engine; a language model (optional) only chooses which cited facts to mention and in what words.

## Design in one picture
```
 Finder / scenario run / optimiser  (unchanged maths)
              │  existing results
              ▼
   FACT SHEET  (copilot/facts.py)         every fact: id · value · unit · provenance label · source API field
              │
     ┌────────┴─────────────────────────┐
     ▼                                  ▼
 deterministic templates          language model (Ollama qwen3:8b by default; Anthropic optional)
 (copilot/narrative.py)           sees ids + hidden values, writes sentences with {{fact_id}} placeholders + cites
     │                                  │  raw JSON
     │                                  ▼
     │                          GROUNDING VALIDATOR (copilot/grounding.py)  ── any doubt ──► reject whole reply
     ▼                                  ▼
          server renders every value / name / path from the fact sheet  ── fallback ◄── templates
```

## What the model is allowed to do
It returns JSON: sentences containing only connective words and `{{fact_id}}` placeholders, plus the ids each sentence cites. It never sees names or numbers (the prompt shows `<name>`, `<number>`, `<notice>`; ranking stability is shown as a band; labels contain no digits), so it cannot copy them. The server substitutes the real values.

## What the validator rejects (whole reply, then fall back)
Literal digits, number words, `% $` symbols; unknown or uncited fact ids; any capitalised word that is not a placeholder (entity names, invented paths); arrows or markup; forbidden vocabulary (probability, likely, forecast, predict, save/savings, guarantee, accurate, validated, verified, observed, empirical, certain, profit, should/must/recommend/advise); "robust/stable/reliable/confident" unless the sentence cites a ranking-stability fact, never together with a loss magnitude, and never when the cited stability value is below 90%; "fragile" unless the `fragile` fact says yes; "real" unless it cites the real hazard-context fact; mitigation sentences that cite no mitigation fact; missing answer or uncertainty section; malformed JSON or schema.

One harmless normalisation is applied first: a placeholder used but not listed in `cites` is added to `cites` (cites only drive the provenance chips; unknown ids are still rejected).

## What the server always adds, whatever the model wrote
- A ranking-stability statement (robust, fragile or uncertain according to the actual P(top 5) / draw results), worded separately from loss amounts.
- The statement that loss magnitudes are uncalibrated and have no empirical validation, and the synthetic-data / real-hazard-context statement.
- A "(modelled value, not validated)" hedge on any sentence that states a loss, impact or cost without already saying it is modelled.
- Plain refusals for questions the facts cannot answer: probability / likelihood, forecasts, savings or returns, "is it validated / accurate", advice ("what should we do"), worst-case losses, and evidence the sheet lacks (for example holdings on a plan-only sheet). These come from the server's own question classifier, so the model cannot remove them.

## Provenance labels
`synthetic_input` · `model_assumption` · `real_hazard_context` (the JRC flood layer; context only) · `unvalidated_model_output` (every loss, impact and cost figure) · `model_robustness` (ranking stability under the model's own parameter draws, **not** validation). The label `empirically_validated` exists in the schema and is never emitted: nothing in this project has been empirically validated.

## API
| Endpoint | Purpose |
|---|---|
| `GET /api/v1/copilot/status` | Which provider is configured and whether Ollama / a key is available |
| `POST /api/v1/copilot/facts` | The fact sheet for a focus: `finder_event`, `scenario` or `mitigation_plan` (inspectable evidence) |
| `POST /api/v1/copilot/ask` | Grounded explanation; `mode` is `llm` or `deterministic`, with `fallback_reason`, validator outcome, per-sentence provenance and cites |
| `POST /api/v1/copilot/report` | Executive summary as Markdown with an evidence table and standing notes; `use_model` optional |

The optimiser response gained one additive field, `residual_events` (the five events that still hurt most after the plan). Nothing else in the existing API or maths changed.

## Providers and cost
| Provider | Default | Cost |
|---|---|---|
| Deterministic templates | always available; used on any failure | free |
| Local Ollama, `qwen3:8b` | **yes** (`FIN04_LLM_PROVIDER=ollama`) | free, nothing leaves the machine |
| Anthropic API, `claude-haiku-5-5` | **off**; only if `FIN04_LLM_PROVIDER=anthropic` and `FIN04_ANTHROPIC_API_KEY` are set in `backend/.env` | paid; never required. The key stays on the server and is never sent to the browser. The integration is covered by mocked tests only; it has not been run against the live API |

Set `FIN04_LLM_PROVIDER=deterministic` to turn the model off entirely.

## Startup
```bash
ollama serve                    # if not already running; model: ollama pull qwen3:8b
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm run dev      # Finder page → Explain / Ask; Scenario results → AI copilot panel
```
The first model request can take about 90 s while Ollama loads the model (82 s measured); later requests take 7–40 s. If Ollama is down the panel says so and answers from templates.

## Proof of concept and measured behaviour (local `qwen3:8b`, 9 October 2026)
Method: the real Ollama path (`tools/copilot_poc.py`), temperature 0, fixed seed; each (fact sheet, question) is one trial. Set A: 8 fact sheets (4 finder events, 2 scenarios, 2 optimiser plans) × 4 questions, two of them unsupported-claim probes. Set B (hold-out): 4 fact sheets × 8 questions not used while tuning.

| Stage | Replies accepted | Fell back to templates | Sentences failing validation | Median latency |
|---|---|---|---|---|
| Prompt v1 (set A) | 4 / 32 (12%) | 28 (88%) | 29% | 31 s |
| Prompt v2: names, numbers and notices hidden from the model (set A) | 14 / 32 (44%) | 18 (56%) | 9% | 10.5 s |
| Prompt v3: + digit-free labels, empty answer allowed when declining (set A) | 30 / 32 (94%) | 2 (6%) | 2% | 9.6 s |
| Hold-out (set B, not used for tuning, prompt v3) | 31 / 32 (97%) | 1 (3%) | 1% | 10.2 s |
| **Final code** (after hedge, advice and evidence-gap rules), set A | 30 / 32 (94%) | 2 (6%) | 2% | 9.5 s |
| **Final code**, hold-out set B | 31 / 32 (97%) | 1 (3%) | 2% | 8.8 s |
| **Final code, both sets combined** | **61 / 64 (95%)** | **3 (4.7%)** | 2% | 9.2 s |

- **The 3 final fallbacks:** two were a plan-only fact sheet asked "which holdings" (the model invented the id `holding_1`), one used a number word. All three were correctly rejected.
- **JSON compliance:** every model reply parsed and matched the schema in every run (Ollama structured output); all failures were validator rejections, not malformed JSON.
- **Safety under failure:** every rejected reply was replaced by templates; nothing unvalidated was ever shown.
- **Tuning caveat:** prompts v2–v3 were tuned on set A, so its numbers are optimistic; set B is the fairer estimate, and both come from 32 trials with a single model at temperature 0.
- **A semantic misread that passed validation (live, found in the browser run):** the model wrote "3 holdings are disrupted, with 1 directly impacted", citing the count of entities hit directly (here the grid operator, not a holding), which contradicts "no holding is hit directly". Every number was traceable, so the validator accepted it. The ambiguous fact is now hidden from the model (still shown in the evidence list) and the location-only label states what zero means, but similar misreadings remain possible: this is the main reason every sentence is shown with its cited facts.
- **Defects found by reading accepted answers** (the validator checks wording and citations, not reasoning), and fixed: loss amounts stated as fact ("causes $159.6M loss"), invented advice ("a risk manager should first…"), and a question about "worst case" the model has no concept of.

## Company structure (v0.4)
In the company view a holding can be a company with several business units. For such a holding the fact sheet adds `holding_{i}_structure` (text, `synthetic_input`), `holding_{i}_other_share` (the share outside Food & Beverage, `synthetic_input`) and `holding_net_{i}_if_other_hit` (the upper end, `unvalidated_model_output`, so any sentence using it gets the modelled-value hedge). The template adds one sentence: the company's disruption is the value-added-weighted average of its business units, or the upper end if its other businesses were hit as hard. Paths count as reaching a holding when they end at any unit a held company owns. No new number is computed for the copilot; every value comes from the finder or comparison rows.

## Remaining limitations
- **Validation is not reasoning.** A model reply can pass every rule and still be poorly reasoned (for example attach the wrong intervention to a sentence, or order facts oddly); the validator cannot detect that. Every sentence therefore shows its provenance chips and a one-click list of the facts it cites.
- **Proper-noun check is heuristic.** Capitalised words are blocked; an uncapitalised invented noun would pass.
- **Stability wording is rule-based** (p ≥ 90% for "robust"); the threshold is a project choice.
- **Hallucination is reduced, not eliminated.** The design limits what a model can state and rejects what it can detect; when validation is uncertain the answer is replaced by templates.
- **Small local model.** `qwen3:8b` is slow (about 15 tokens/s here) and its acceptance rate is measured on 64 trials only; other models or hardware will differ.
- **Anthropic path untested against the live API.**
- **No empirical validation, real-world savings or probability** appear anywhere; all figures are synthetic-data model outputs.

## Tests
`backend/tests/test_copilot.py` (stub providers: grounding against API results, override attempts, malformed JSON, timeouts, unavailable providers, missing evidence, wording rules, traceability of every number and name, report), `backend/tests/test_copilot_live.py` (real Ollama; run with `FIN04_LIVE_OLLAMA=1`), `frontend/src/components/copilot.test.tsx`, browser steps C1–C4 in `scripts/e2e_smoke.mjs`, and `scripts/e2e_copilot_fallback.mjs` (a second backend with Ollama unreachable: `FIN04_OLLAMA_URL=http://127.0.0.1:9 FIN04_DATABASE_URL=sqlite:////tmp/fallback.db uvicorn app.main:app --port 8001` and `VITE_BACKEND_URL=http://127.0.0.1:8001 npx vite --port 5174`, then `APP_URL=http://localhost:5174 node scripts/e2e_copilot_fallback.mjs`).
