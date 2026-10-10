# Architecture

Modular monolith: one FastAPI process, one React SPA, one SQLite file. No queues, containers or services.

```
frontend (React 19, Vite, Tailwind 4, Cytoscape, Recharts)
   │  /api/v1/*  (Vite dev proxy → :8000)
backend/app
   api/routes.py        thin HTTP layer; Pydantic request/response validation; 404/422 mapping
   services/            runner.py (one scenario run), scenarios.py (resolve/save/cache), state.py (dataset + LRU cache), report.py,
                        finder.py (Hidden Exposure Finder), optimise.py (resilience optimiser)
   models/              pure, unit-tested algorithms (no HTTP/DB):
                          climate.py      hazard-provider interface + direct exposure
                          propagation.py  graph compilation + multi-hop propagation (NumPy, batched over runs/events);
                                          graph-derived alternative suppliers, feedback-loop damping, per-run durations
                          events.py       generated event library for the Hidden Exposure Finder
                          reverse_stress.py batch scoring, collapsing, rank stability, outages, pair bound
                          optimiser.py    budget-constrained intervention optimiser (greedy + swap + exhaustive gap)
                          analytics.py    centralities, systemic score, dominant paths, structure
                          montecarlo.py   seeded uncertainty analysis
                          mitigation.py   interventions, capacity-limited re-sourcing, cost model, prioritisation
                          backtest.py     evaluation interface (+ explicitly circular synthetic demo)
   domain/dataset.py    load + validate F&B dataset (+ company structures), build NetworkX graph;  domain/reference.py Sectivia loader
   domain/holdings.py   holdings as companies: segment shares, entity weights w = AᵀW, company-level aggregation, v0.3 business-unit view
   schemas/             Pydantic models (domain, scenario, results, mitigation)
   db.py                SQLAlchemy/SQLite: user-defined scenarios (built-ins seeded from data/scenarios.json)
backend/data            generate_dataset.py → fnb_entities.json, fnb_relations.json, scenarios.json, portfolio.json, companies.json, reference_audit.json;
                        fetch_jrc_flood.py → hazard_layers/jrc_flood_rp100.json (offline, real data); manifest.json
```

## Endpoints added in v0.2
`GET /api/v1/portfolio` · `POST /api/v1/analysis/reverse-stress` (finder) · `POST /api/v1/analysis/reverse-stress/promote` (event → stored scenario) · `POST /api/v1/mitigation/optimise`. Report, entity-impact, critical-path and mitigation endpoints now accept `max_depth`, so every page and export honours the depth slider.

## AI copilot (v0.3)
`backend/app/copilot/`: `facts.py` (fact sheets with provenance and source fields, built from existing finder / scenario / optimiser results), `grounding.py` (validator + renderer), `providers.py` (Ollama, optional Anthropic), `narrative.py` (templates), `service.py` (orchestration and safe fallback). Routes: `GET /api/v1/copilot/status`, `POST /facts`, `/ask`, `/report`. Frontend: `components/CopilotPanel.tsx` used on the Finder and Scenario results pages. Design and limits: `docs/COPILOT.md`.

## Holdings as companies (v0.4)
`domain/holdings.py` defines a holding as a company made of business units (segments) plus an unmodelled share outside Food & Beverage. Every portfolio number is `disruption @ w`, so spreading company weights over their units (`w = AᵀW`) makes the finder, stability draws, pair bound, optimiser and scenario comparison company-aware without touching the propagation engine. Per-holding views (top holdings, who-can-hurt-whom, single points of failure, comparison rows) aggregate with the same matrix. `holding_view` (`company` default, `business_unit` = v0.3) is accepted by `POST /analysis/reverse-stress` (and so the optimiser and copilot finder focus), `POST /scenarios/{id}/run`, `/analysis/propagation`, `/analysis/network-vs-location`, `GET /scenarios/{id}/report`, `GET /portfolio` and the copilot scenario focus; the frontend holds it in `AppState` (persisted) and shows a switch in the top bar. All new response fields are additive.

## Key decisions
- **The finder is a search layer, not a new engine.** The ~780-event library becomes the leading row axis of the same `simulate` call used by a scenario run and by Monte Carlo, so the finder costs about 0.05 s deterministic and under 1 s with 500 stability draws. Any event can be promoted to an ordinary scenario, and the existing screens then reproduce its numbers.
- **Real data stays offline.** The JRC flood layer is sampled once by a script (`requirements-data.txt`: tifffile, imagecodecs) and shipped as a small JSON; the running app gains no GIS dependency.
- **Propagation is vectorised** with a compiled edge/group matrix, so one deterministic run and a 5 000-run Monte Carlo share the same code path (`propagate` takes a leading simulation axis). Measured on a laptop at 102 nodes / 232 supply edges: a deterministic run ≈ 1–10 ms, 5 000 Monte Carlo simulations ≈ 0.15 s (the API adds validation and serialisation overhead).
- **Caching:** an in-process LRU keyed by a hash of the scenario spec + options holds run results, Monte Carlo results and mitigation recommendations, so UI interactions (tab changes, re-renders) never recompute. Monte Carlo runs only on explicit request.
- **Hazard provider interface** (`HazardProvider.footprint_weights`) is the seam for real data (gridded rainfall/discharge/temperature). Only the labelled-synthetic provider is implemented; World Bank CCKP and Open-Meteo are *not* integrated.
- **Channels:** edges carry `channel` (`supply` | `financial`). Only `supply` edges propagate; lender/insurer edges are displayed and documented but separate, as the evidence review treats lender edges as a second channel.
- **Future industries:** entity types, products, vulnerability defaults and scenarios are data, not code, so another domain means a new generator + provider config. Nothing else is implemented.
- **Errors:** validation → 422 with readable messages; unknown ids → 404; unhandled errors → generic 500 (details only in server logs).
- **Frontend state:** one `AppProvider` holds metadata, graph, scenarios, the active scenario's run result and Monte Carlo result. Every page reads that or calls the API directly; there are no hard-coded figures.
