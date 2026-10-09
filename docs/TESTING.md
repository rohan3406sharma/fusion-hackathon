# Testing

| Layer | Command | Covers |
|---|---|---|
| Backend (51 tests) | `cd backend && ../.venv/bin/python -m pytest -q` | Dataset load/validation (bad refs, duplicates, impossible dependencies, cycles, isolated nodes); Sectivia reference loads in generic tooling; hand-checked 2-hop propagation (0.24 transmission); inventory/lead-time and substitution effects; no double counting (additive within an input, noisy-OR across inputs); cycle termination; empty/disconnected graphs; direct exposure monotonicity, footprint, duration, compound amplification; Monte Carlo reproducibility and quantile ordering; zero-denominator comparison; systemic score decomposition; back-test metrics; capacity-limited diversification; every API endpoint, schema invariants (orders sum to total), error cases (404/422), request limits, DB seeding |
| Frontend (19 tests) | `cd frontend && npm test` | Filter logic, formatting, CSV export escaping, layout, scenario-draft validation; page rendering from mocked API; error state with retry; search/status filtering + node selection updating the detail panel; builder disabled/enabled states; Monte Carlo empty→result states |
| Typecheck/build | `npm run build` | `tsc --noEmit` + Vite production build |
| End-to-end (19 steps) | `cd scripts && npm install && npm run e2e` | Real browser (headless Chrome via puppeteer-core) against real servers: dashboard KPIs → graph renders 102 backend nodes → click facility updates panel → filter hides nodes → depth slider re-runs model → configure + run new scenario → orders/paths/comparison → Monte Carlo (and reproducibility) → exports download → mitigation compare + recommendations → entity and methodology pages → mobile nav, no horizontal overflow, no console errors; plus the guided Rotterdam journey (hidden exposure in the comparison, result path → graph selection, exports verified to contain scenario, assumptions and uncertainty, load-and-compare a recommended mitigation) |

`cd scripts && SHOT_DIR=/tmp/fin04-shots npm run screenshots` captures all seven screens at 1440 px and 390 px (default scenario: Rotterdam; set `SCENARIO`). The E2E also asserts no horizontal overflow on all seven screens at 390 px, scenario persistence across reload, and that CSV/JSON/Markdown exports carry scenario, assumptions, limitations and (when run) uncertainty.

E2E prerequisites: both servers running; Google Chrome (set `CHROME_PATH` if not at the macOS default); `scripts/package.json` installs puppeteer-core (it is not a dependency of the app itself). Screenshots are written to `SHOT_DIR` (default: a temp folder).

Results of the latest run are reported in the hand-off message; rerun the commands to reproduce.

## Audit-phase regressions
Tie-aware portfolio ranks, bottleneck customer counts, exports carrying scenario + assumptions + uncertainty (backend and client CSV), monotonicity of loss in intensity, inventory blocking storable transmission, `?select=` graph preselection, scenario persistence, fractional-rank rendering. Charts render with animation disabled (also honours reduced motion).
- the E2E smoke test saves one custom scenario named 'E2E Brazil drought' into backend/fin04.db per run; delete it with: sqlite3 backend/fin04.db "delete from scenarios where name='E2E Brazil drought' and builtin=0".
