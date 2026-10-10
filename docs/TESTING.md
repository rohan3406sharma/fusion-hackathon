# Testing

| Layer | Command | Covers |
|---|---|---|
| Backend (177 tests + 3 live-model tests) | `cd backend && ../.venv/bin/python -m pytest -q` | Dataset load/validation (bad refs, duplicates, impossible dependencies, cycles, isolated nodes); Sectivia reference loads in generic tooling; hand-checked 2-hop propagation (0.24 transmission); inventory/lead-time and substitution effects; no double counting (additive within an input, noisy-OR across inputs); cycle termination; empty/disconnected graphs; direct exposure monotonicity, footprint, duration, compound amplification; Monte Carlo reproducibility and quantile ordering; zero-denominator comparison; systemic score decomposition; back-test metrics; capacity-limited diversification; holdings as companies (structure, same-money weights, ordering of the three company readings, v0.3 equivalence, API, copilot); every API endpoint, schema invariants (orders sum to total), error cases (404/422), request limits, DB seeding |
| Frontend (31 tests) | `cd frontend && npm test` | Filter logic, formatting, CSV export escaping, layout, scenario-draft validation; page rendering from mocked API; error state with retry; search/status filtering + node selection updating the detail panel; builder disabled/enabled states; Monte Carlo empty→result states; holding-view switch re-runs the finder and scenario and persists; company panel and company rows with their business units |
| Typecheck/build | `npm run build` | `tsc --noEmit` + Vite production build |
| End-to-end (27 steps) | `cd scripts && npm install && npm run e2e` | Real browser (headless Chrome via puppeteer-core) against real servers: dashboard KPIs → graph renders 102 backend nodes → click facility updates panel → filter hides nodes → depth slider re-runs model → configure + run new scenario → orders/paths/comparison → Monte Carlo (and reproducibility) → exports download → mitigation compare + recommendations → entity and methodology pages → mobile nav, no horizontal overflow, no console errors; plus the guided Rotterdam journey (hidden exposure in the comparison, result path → graph selection, exports verified to contain scenario, assumptions and uncertainty, load-and-compare a recommended mitigation) |

`cd scripts && SHOT_DIR=/tmp/fin04-shots npm run screenshots` captures all seven screens at 1440 px and 390 px (default scenario: Rotterdam; set `SCENARIO`). The E2E also asserts no horizontal overflow on all seven screens at 390 px, scenario persistence across reload, and that CSV/JSON/Markdown exports carry scenario, assumptions, limitations and (when run) uncertainty.

E2E prerequisites: both servers running; Google Chrome (set `CHROME_PATH` if not at the macOS default); `scripts/package.json` installs puppeteer-core (it is not a dependency of the app itself). Screenshots are written to `SHOT_DIR` (default: a temp folder).

Results of the latest run are reported in the hand-off message; rerun the commands to reproduce.

## Audit-phase regressions
Tie-aware portfolio ranks, bottleneck customer counts, exports carrying scenario + assumptions + uncertainty (backend and client CSV), monotonicity of loss in intensity, inventory blocking storable transmission, `?select=` graph preselection, scenario persistence, fractional-rank rendering. Charts render with animation disabled (also honours reduced motion).
- the E2E smoke test saves two custom scenarios per run ('E2E Brazil drought' and 'Finder: <top hidden-only event>') into backend/fin04.db; delete them with: sqlite3 backend/fin04.db "delete from scenarios where builtin=0 and (name='E2E Brazil drought' or name like 'Finder:%')".

## v0.2: finder, optimiser and engine changes
- **Engine rules (hand-checked):** market alternatives apply only to the unmodelled share of an input. Graph relief comes from an alternative's spare capacity and disappears when that alternative is hit. Non-storable alternatives must be domestic. Feedback damping reaches the analytic fixed point 0.5/0.875. Per-run durations work.
- **Monte Carlo regression:** on the Brazil drought, indirect-loss sensitivity must rank dependency (ρ > 0.2) and substitutability (ρ < −0.2) among the top drivers. v0.1's per-link-only sampling reported ρ ≈ 0 for both.
- **Finder correctness:**
    - 20 generated graphs with a planted bottleneck; it must rank first in all 20.
    - The exhaustive pair search must equal brute force, with greedy reported beside it.
    - Invariants: P_net ≥ P_loc, hidden share in [0, 1], unique ids, determinism, a larger radius never reduces impact, zero weight contributes nothing.
    - Near-duplicates collapse.
- **Finder robustness:** a 200-event shortlist gives the same top 5 as 100, with P(top 5) within 0.1.
- **Integration:** promoting a finder event creates a scenario whose Results reproduce the finder's portfolio impact (also checked in the E2E, step F2).
- **Optimiser:** respects the budget; matches exhaustive search on a small problem; the API reports gap, cost sensitivity and robustness.
- **JRC layer:** cited, licensed, bounded values. Entity detail exposes it. `flood_check=drop` never adds events.
- **E2E steps F1–F3:** finder search and sort; promote, then check that Results show the same impact; optimiser with brute-force gap. Overflow check now covers 8 screens.

## Independent audit (9 October 2026)
Scripts were run outside the repository's code paths; results:
- **Reference implementation:** a scalar pure-Python model written from `METHODOLOGY.md` and the raw JSON matches the vectorised engine to about 1e-10 on all final disruptions for 24 events (top of both lists plus a random sample).
- **Consistency:** hidden share = 1 − P_loc/P_net, P_net ≥ P_loc and the hidden-only definition hold for all 200 listed events. Promoting an event reproduces its portfolio impact (max difference 6.5e-6, from 4 dp rounding of per-entity disruption in the run result).
- **Optimiser:** baseline 3.254% and plan 3.102% of annual value added (mean of the worst 10 of 50 distinct events), a 4.66% relative reduction, recomputed by the reference. Budget 2: 84 feasible plans in the 10-candidate pool (reproduced), 184 over all 14 candidates, same optimum. The plan does not make any of the 268 distinct events worse.
- **Stability:** a 200 × 100 draw matrix; same seed identical, other seeds and 1000 draws give the same top hidden-only event at 100%.
- **JRC layer:** raster classes are {1,2,3,4,255}; exact per-cell haversine resampling agrees to within 0.007; 4 of 100 windows are truncated at tile edges; the filter is lenient (92 of 100 entities pass).
- **Mutation testing:** 24 injected bugs in the finder, optimiser, engine and sampling. The original suite caught 17; after adding behavioural tests (hidden-share formula, tail objective, seed, top-5 window, JRC direction, weight normalisation, outage threshold) all 24 are caught. To repeat, copy `backend/`, apply a one-line change, run `pytest -x -q`.

## AI Climate Risk Copilot
- **Mocked providers** (`backend/tests/test_copilot.py`, 68 tests): grounded replies rendered with engine values compared to the API results; attempts to override numbers, add literals, unknown ids, invented entities and paths, advice, probabilities and savings are rejected and the engine values remain; malformed JSON, schema mismatch, timeout, unreachable, missing model, missing key and unexpected errors fall back to templates with a stated reason; unsupported questions are declined by the server even if the model answers; robust / fragile / real wording rules; every number and name in every rendered answer traces to a cited fact; the prompt hides names, numbers and notices from the model; the report is deterministic with an evidence table.
- **Live Ollama** (`backend/tests/test_copilot_live.py`, skipped unless `FIN04_LIVE_OLLAMA=1`): 4 real model replies through the full path; asserts safety invariants (traceable numbers, no "validated" provenance, server-side declines) and that at least one reply is accepted. Result on 9 October 2026: 3 passed, 4 of 4 replies accepted, latencies 7 to 34 s.
- **Frontend** (`copilot.test.tsx`, 7 tests): loading, grounded answer with provenance chips, fallback reason, unavailable-model state, declined questions, errors with retry, focus changes, report download.
- **Browser:** steps C1–C4 of `e2e_smoke.mjs` run the copilot against the live local model (engine impact present in the answer, unsupported question declined, executive summary download, scenario copilot); `e2e_copilot_fallback.mjs` runs against a second backend with Ollama unreachable and checks the template fallback and its stated reason.
- **Measured live behaviour:** 64 trials (32 tuned, 32 hold-out): 61 accepted, 3 fell back (4.7%). See `docs/COPILOT.md`.
- **Mutation testing** of the copilot (28 injected bugs in the validator, server-side rules, prompt masking, fact builder and provenance labels): the first suite caught 27; after adding a test for the word "real", all 28 are caught.

## v0.4: holdings as companies (`backend/tests/test_holdings.py`, 13 tests)
- **Structure:** company structures load and validate; segment shares follow value added and, with the non-F&B share, sum to 1; invalid structures (duplicate ids, an entity in two companies, unknown or financial units, out-of-range shares, ids colliding with entities) are reported and ignored.
- **Same money:** 18 held units become 16 companies with the same total weight; a company's weight is the sum of its held units' weights; the non-F&B share carries no entity weight; company ids are accepted only in the company view.
- **Invariants** (200 random companies): segment-weighted ≤ non-F&B-hit upper end ≤ one node; the upper end lies between the units' minimum and maximum; one node is the exact noisy-OR (two units each 50% down give 75%); a single-business holding equals its unit; an unaffected unit only dilutes.
- **Equivalence with v0.3:** the business-unit view gives exactly the v0.3 entity weights and portfolio scores (`np.array_equal`). A one-off field-by-field comparison against the v0.3 code (finder top 100 events with 200 draws, all six built-in scenarios, optimiser at budget 3 with brute force and 50 draws) found 0 differences.
- **API and copilot:** company-view finder rows equal the weighted average of their units, and the one-node value equals the noisy-OR of the units; the structure comparison has four views; a company's own units never appear as upstream nodes; promoting an event reproduces its impact in both views; comparison rows and `/portfolio` describe companies; entity pages report their company; copilot facts carry the structure with `synthetic_input` provenance and the template explains the weighting without new numbers.
- **Mutation testing:** six one-line bugs injected into the company logic (no dilution by the non-F&B share, merged units losing weight, an inverted upper end, one node as a maximum, comparison ignoring shares, own units treated as upstream). The first suite caught 5; after adding an exact noisy-OR check, all 6 are caught.
- **Browser:** step F4 of `e2e_smoke.mjs` checks the four-row comparison table and a company breakdown, switches to business units (hidden-only count changes and matches the table) and back. The full run is 27/27 against isolated servers (:8001 backend with a throwaway database, :5174 frontend).
- **Optimiser (company view):** enumerating every affordable plan over all 14 candidates confirms the greedy-plus-swap plan (166 plans at budget 2, 481 at budget 3).
