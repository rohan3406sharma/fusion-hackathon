# FIN-04 Climate Exposure Graph: Food & Beverage

A network-aware climate stress-testing and decision-support prototype. It shows how a flood, heatwave or drought at one farm, plant, port or warehouse can propagate through a **synthetic** Food & Beverage supply chain, and compares a *location-only* estimate with a *network-aware* one.

> **Honesty notice.** All 102 entities and 240 relationships are synthetic demonstration data. Hazard footprints are synthetic indices, not hazard maps. Results are model estimates under stated assumptions: not forecasts, not calibrated, not validated. Third-order propagation and the network-vs-location comparison are model-dependent, not established empirical results. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

Scope: Food & Beverage only. The supplied Sectivia files (AI, energy, defence, medicine, quantum, finance) contain no food companies, weights or coordinates; they are used only to test generic graph tooling and audited on the *Data & methodology* page. Credit: *Supply-chain data: Sectivia (https://sectivia.com), CC BY 4.0.*

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
The dataset ships pre-generated (`backend/data/*.json`) and is loaded and validated automatically at API start-up; built-in scenarios are seeded into SQLite (`backend/fin04.db`). To regenerate it deterministically:
```bash
.venv/bin/python backend/data/generate_dataset.py
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
cd backend  && ../.venv/bin/python -m pytest -q      # 51 backend tests
cd frontend && npm test && npm run build              # 19 frontend tests, typecheck + production build
(cd scripts && npm install && npm run e2e)             # 19-step browser workflow; needs both servers running + Google Chrome (docs/TESTING.md)
(cd scripts && SHOT_DIR=/tmp/fin04-shots npm run screenshots)   # full-page screenshots of all 7 screens, desktop + mobile
```

## Demo walkthrough (about 5 minutes)
1. **Overview**: KPIs from the backend for *Punjab-Haryana Monsoon Flood*: direct vs network-aware loss, bottlenecks, evidence-labelled propagation orders.
2. **Supply-chain graph**: pan/zoom, search "coffee", filter by status. Drag the *propagation depth* slider (the model re-runs). Click *Ludhiana Flour Mills* to see upstream/downstream highlighting, hop depth, and its dominant propagation path.
3. **Scenario builder**: switch the active scenario to *Southeast Brazil Multi-Season Drought* (top bar) → *Scenario builder*: change hazard, footprint centre/radius, duration, inventory/substitution scales → **Run analysis**.
4. **Scenario results**: direct / 1st / 2nd / 3rd-order tables, loss by category/type/country, critical paths. **Location-only vs network-aware** table shows rank changes and *hidden exposures* in the 18-holding synthetic portfolio. Click **Run uncertainty analysis** (seeded; re-running gives identical numbers). Export CSV / JSON / Markdown report.
5. **Mitigation laboratory**: add *Increase inventory buffers* at *Paulinia Soft-Drink Bottler* and *Diversify suppliers* → **Compare with baseline**; see capacity-limited sourcing notes, cost, BCR and a ranked recommendation list.
6. **Entity intelligence** (click any entity name) and **Data & methodology** (dataset inventory, missing-data stats, Sectivia audit, formulas, limitations).

Most striking scenario for hidden exposure: *Rotterdam Terminal Flood (single node)*: one port, no direct portfolio loss, but downstream holdings light up.

## Troubleshooting
| Symptom | Fix |
|---|---|
| UI shows "Cannot reach the backend" | Start uvicorn on port 8000 (or set `VITE_BACKEND_URL`). |
| `ModuleNotFoundError: scipy` | `.venv/bin/pip install -r backend/requirements.txt` (SciPy is needed by NetworkX PageRank). |
| Port already in use | `lsof -i :8000` / `:5173`, stop the old process, or pass `--port`. |
| Stale scenarios after editing `scenarios.json` | Built-in scenarios are re-seeded at start; delete `backend/fin04.db` to clear custom ones. |
| `npm run build` warns chunk >500 kB | Expected (Cytoscape + Recharts); not an error. |

## Repository map
`backend/app/` (api, models, services, schemas, domain) · `backend/data/` (generator, dataset, manifest, reference) · `backend/tests/` · `frontend/src/` (pages, components, lib, state, api) · `docs/` · `scripts/e2e_smoke.mjs`.
