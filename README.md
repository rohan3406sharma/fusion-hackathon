# FIN-04 Climate Exposure Graph: Food & Beverage

*Repository `fusion-hackathon`: climate risk intelligence for investment portfolios using interactive dependency graphs, cascading risk simulation, and financial exposure analysis.*

A network-aware climate stress-testing prototype for a **synthetic** Food & Beverage supply chain. Its centre is the **Hidden Exposure Finder**, a portfolio reverse stress test. Instead of asking you to guess a scenario, it scores about 780 generated climate events against an 18-holding portfolio. It ranks the events that hurt the portfolio most, and shows how much of each loss a location-only screen would miss. A budget-constrained optimiser then picks interventions against those events. Holdings are **companies**: a company that owns several business units is disrupted by the value-added-weighted average of its units, and any share of its business outside Food & Beverage is shown but not modelled.

> **Honesty notice.** All 102 entities, 240 relationships, the portfolio weights, the company structures, intervention costs and hazard scenarios are synthetic demonstration data. The one real dataset is the JRC / Copernicus 100-year river-flood map, sampled at the synthetic coordinates and used only as context and a plausibility filter. Results are model estimates under stated assumptions: not forecasts, not calibrated, not validated. Rankings that stay stable under parameter uncertainty show internal consistency, not real-world accuracy. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

Scope: Food & Beverage only. The supplied Sectivia files (AI, energy, defence, medicine, quantum, finance) contain no food companies, weights or coordinates; they are used only to test generic graph tooling and audited on the *Data & methodology* page. Credit: *Supply-chain data: Sectivia (https://sectivia.com), CC BY 4.0.* Flood hazard: *Baugh et al. (2024), JRC / Copernicus CEMS global river flood hazard maps v2.1.2, © European Union, CC BY 4.0.*

## Requirements
Python 3.11+ (tested on 3.14), Node 20+ (tested on 25), npm. No API keys, no GPU, no paid services.

## Setup
```bash
# from this folder
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
cp .env.example backend/.env      # optional; defaults work
```

## Load the demo data
Everything ships pre-generated in `backend/data/` and is loaded and validated at API start-up; built-in scenarios are seeded into SQLite (`backend/fin04.db`).
```bash
.venv/bin/python backend/data/generate_dataset.py          # regenerate the synthetic dataset and portfolio (deterministic)

# optional: re-sample the real JRC flood layer (needs network; ~60 MB of tiles cached under backend/data/hazard_layers/cache/)
.venv/bin/pip install -r backend/requirements-data.txt
cd backend && ../.venv/bin/python data/fetch_jrc_flood.py && cd ..
```

## Run
```bash
# terminal 1: backend  (http://127.0.0.1:8000, docs at /docs)
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000

# terminal 2: frontend (http://localhost:5173; /api is proxied to the backend)
cd frontend && npm run dev
```

## Test
```bash
cd backend  && ../.venv/bin/python -m pytest -q          # 177 backend tests (+3 live-model tests, see below)
cd frontend && npm test && npm run build                  # 31 frontend tests, typecheck + production build
(cd scripts && npm install && npm run e2e)                # 27-step browser workflow (uses the local model if Ollama runs); needs both servers + Chrome
cd backend && FIN04_LIVE_OLLAMA=1 ../.venv/bin/python -m pytest -q tests/test_copilot_live.py -s   # real Ollama, separate from mocked tests
(cd scripts && SHOT_DIR=/tmp/fin04-shots npm run screenshots)   # all 8 screens, desktop + mobile
```

## Demo walkthrough (about 3 minutes)
1. **Overview.** The finder card states the largest hidden-only exposure across about 780 synthetic events. With the current data that is a drought at the Dutch regional grid operator. No company is hit at any of its own sites, yet the model has the portfolio losing 1.06% of annual value added (synthetic, uncalibrated; 1.13% with holdings counted as business units), and the event stays in the hidden-only top 5 in 100% of 200 uncertainty draws.
2. **Hidden exposure finder.** Click **Search**.
    - The *Hidden-only* table lists those events, with P(top 5) and fragile flags.
    - Switch *Sort by holdings reached*: the Rotterdam terminal flood reaches 7 holdings, the broadest of any hidden-only event.
    - The *Who can hurt whom* matrix and *Single points of failure* show the shared upstream dependencies. The Rotterdam terminal is the top single point of failure, for Hamburg Coffee Roasters and Antwerp Chocolatier.
3. **Companies, not just business units.** Four of the 16 holdings own several business units (synthetic structures in `backend/data/companies.json`). The finder's *Companies, not just business units* panel scores the same library four ways: as business units (165 hidden-only events), as companies (152), with non-F&B businesses hit too, and with every company as one node (the 10 worst events average 4.04% instead of 3.23%). On *Scenario results* for the *Punjab-Haryana Monsoon Flood*, Five Rivers Consumer Group (a synthetic diversified consumer group) shows its biscuit unit 69.6% disrupted but the company 18.8%, up to 41.9% if its 55% outside Food & Beverage were hit as hard. The *Companies | Business units* switch in the top bar returns to the v0.3 view, which reproduces earlier numbers exactly.
4. **Open as scenario** on any event. It becomes a normal scenario: **Scenario results** shows the same portfolio impact, the propagation paths, *View in graph*, Monte Carlo and exports.
5. **Protect against these events.** Set a budget (for example $3M a year) and click **Optimise**. You get the plan, the tail-impact reduction, the gap against brute force, cost sensitivity and robustness across draws.
6. **Data & methodology.** Formulas, the real-data plausibility check, evidence strength and limitations.

The rest of the app is unchanged: graph exploration, scenario builder, entity intelligence, mitigation laboratory.

## AI Climate Risk Copilot (optional language model)
Explains the selected hidden exposure, scenario or optimiser plan in plain language. **It never calculates**: every value, name and path is filled in by the server from the deterministic engine; a local model only chooses and phrases cited facts, and its replies are validated (or replaced by templates). Default model: local Ollama `qwen3:8b` (free, nothing leaves your machine). Without it, deterministic templates answer. A paid Anthropic option exists but is **off** unless you configure a key.
```bash
ollama pull qwen3:8b && ollama serve        # optional; skip to use deterministic templates only
```
Use it on the **Hidden exposure finder** (*Explain* on any event, or ask about the optimiser plan) and on **Scenario results** (*AI copilot*). Each sentence shows provenance chips (synthetic input, model assumption, real hazard context, unvalidated model output, ranking stability) and the facts it cites; *Executive summary* downloads a Markdown report with an evidence table. First model request can take about 90 s while the model loads. Details, measured fallback rate and limitations: [docs/COPILOT.md](docs/COPILOT.md).

## Troubleshooting
| Symptom | Fix |
|---|---|
| UI shows "Cannot reach the backend" | Start uvicorn on port 8000 (or set `VITE_BACKEND_URL`). |
| `ModuleNotFoundError: scipy` | `.venv/bin/pip install -r backend/requirements.txt` (SciPy is needed by NetworkX PageRank and Kendall τ). |
| `ModuleNotFoundError: tifffile` | Only `data/fetch_jrc_flood.py` needs it: `.venv/bin/pip install -r backend/requirements-data.txt`. |
| Copilot says "Language model not available" | Run `ollama serve` and `ollama pull qwen3:8b`, or ignore it: templates answer. `FIN04_LLM_PROVIDER=deterministic` in `backend/.env` turns the model off. |
| Port already in use | `lsof -i :8000` / `:5173`, stop the old process, or pass `--port`. |
| Stale scenarios after editing `scenarios.json` | Built-in scenarios are re-seeded at start; custom ones stay in `backend/fin04.db`. |
| `npm run build` warns chunk >500 kB | Expected (Cytoscape + Recharts); not an error. |

## Repository map
`backend/app/` (api, models, services, schemas, domain) · `backend/data/` (generator, dataset, portfolio, company structures, JRC layer and fetch script, manifest, reference) · `backend/tests/` · `frontend/src/` (pages, components, lib, state, api) · `docs/` · `scripts/` (E2E and screenshots).
