# Architecture

Modular monolith: one FastAPI process, one React SPA, one SQLite file. No queues, containers or services.

```
frontend (React 19, Vite, Tailwind 4, Cytoscape, Recharts)
   │  /api/v1/*  (Vite dev proxy → :8000)
backend/app
   api/routes.py        thin HTTP layer; Pydantic request/response validation; 404/422 mapping
   services/            runner.py (one scenario run), scenarios.py (resolve/save/cache), state.py (dataset + LRU cache), report.py
   models/              pure, unit-tested algorithms (no HTTP/DB):
                          climate.py      hazard-provider interface + direct exposure
                          propagation.py  graph compilation + multi-hop propagation (NumPy, batched over simulations)
                          analytics.py    centralities, systemic score, dominant paths, structure
                          montecarlo.py   seeded uncertainty analysis
                          mitigation.py   interventions, capacity-limited re-sourcing, cost model, prioritisation
                          backtest.py     evaluation interface (+ explicitly circular synthetic demo)
   domain/dataset.py    load + validate F&B dataset, build NetworkX graph;  domain/reference.py Sectivia loader
   schemas/             Pydantic models (domain, scenario, results, mitigation)
   db.py                SQLAlchemy/SQLite: user-defined scenarios (built-ins seeded from data/scenarios.json)
backend/data            generate_dataset.py → fnb_entities.json, fnb_relations.json, scenarios.json, reference_audit.json; manifest.json
```

## Key decisions
- **Propagation is vectorised** with a compiled edge/group matrix, so one deterministic run and a 5 000-run Monte Carlo share the same code path (`propagate` takes a leading simulation axis). Measured on a laptop at 102 nodes / 232 supply edges: a deterministic run ≈ 1–10 ms, 5 000 Monte Carlo simulations ≈ 0.15 s (the API adds validation and serialisation overhead).
- **Caching:** an in-process LRU keyed by a hash of the scenario spec + options holds run results, Monte Carlo results and mitigation recommendations, so UI interactions (tab changes, re-renders) never recompute. Monte Carlo runs only on explicit request.
- **Hazard provider interface** (`HazardProvider.footprint_weights`) is the seam for real data (gridded rainfall/discharge/temperature). Only the labelled-synthetic provider is implemented; World Bank CCKP and Open-Meteo are *not* integrated.
- **Channels:** edges carry `channel` (`supply` | `financial`). Only `supply` edges propagate; lender/insurer edges are displayed and documented but separate, as the evidence review treats lender edges as a second channel.
- **Future industries:** entity types, products, vulnerability defaults and scenarios are data, not code, so another domain means a new generator + provider config. Nothing else is implemented.
- **Errors:** validation → 422 with readable messages; unknown ids → 404; unhandled errors → generic 500 (details only in server logs).
- **Frontend state:** one `AppProvider` holds metadata, graph, scenarios, the active scenario's run result and Monte Carlo result. Every page reads that or calls the API directly; there are no hard-coded figures.
