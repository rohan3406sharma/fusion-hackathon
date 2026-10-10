# Demo runbook: Hidden Exposure Finder (3 minutes)

Everything on screen is **synthetic** except the JRC flood layer (context only). Say that once, early. Numbers below come from the API on 10 October 2026 with the default data, seed 42 and 200 draws, in the default **company view** (holdings are companies; see the switch *Companies | Business units* in the top bar); they reproduce exactly. The explainer video and the 9 October numbers were recorded in the **business-unit view** (1.13%, 165 hidden-only): switch the top bar to *Business units* to reproduce them.

## Start (two terminals, from this folder)
```bash
cd backend  && ../.venv/bin/uvicorn app.main:app --port 8000      # check: curl localhost:8000/health  -> status ok, 102 entities
cd frontend && npm run dev                                         # open http://localhost:5173
```
First run only: `.venv/bin/pip install -r backend/requirements.txt && (cd frontend && npm install)`. Before presenting, run `(cd scripts && npm run e2e)` once (27 steps, a few minutes with the local model). Afterwards remove its test scenarios: `sqlite3 backend/fin04.db "delete from scenarios where builtin=0 and (name='E2E Brazil drought' or name like 'Finder:%')"`.

## Best reproducible path
Active scenario: leave on any; the finder does not depend on it. Seed 42, 200 draws, defaults.

| Time | Do | Say / show |
|---|---|---|
| 0:00 | Overview | "16 synthetic food and beverage companies; four own several business units. A normal screen checks whether their own sites flood. Which event would hurt most?" Point at the Synthetic labels. |
| 0:25 | **Hidden exposure finder** → Search | 780 events scored in about 0.4 s; 269 distinct; **152 hidden-only**: no company is hit at any of its own sites, yet the model has the portfolio losing value through supply links. |
| 0:50 | Hidden-only table, row 1 | **Drought at the Dutch regional grid operator**: 1.06% of annual value added (modelled), reaches 3 holdings (Lowlands Dairy Group, Rhineland Grocery Group, Manchester Ready-Meal Maker), **P(top 5) = 100%** across 200 draws. Rows 4 and 5 show 42% and 46% and are flagged *Fragile*. |
| 1:15 | **Companies, not just business units** panel | The judge's point: a holding is a company. Same 780 events scored four ways: business units 165 hidden-only, companies 152, every company as one node 153; the 10 worst events average 3.25%, 3.23% and 4.04%. 13 "hidden" events land on a unit the company owns. For the ITC-style example, open **Scenario results** for the built-in *Punjab-Haryana Monsoon Flood* → *Companies with several business units*: Five Rivers Consumer Group's biscuit unit is 69.6% disrupted and its flour mill 71.6%, its Mumbai cooking-oil unit 0%, and 55% of its value added is outside F&B (not modelled), so the company is **18.8%** disrupted (up to 41.9% if the non-F&B businesses were hit too, 91.3% as one node). |
| 1:45 | Sort by holdings reached; Single points of failure | The **Rotterdam terminal flood** reaches 7 holdings, the most of any hidden-only event, though it ranks only 16th by size. It is also the top single point of failure: a full outage alone disrupts Hamburg Coffee Roasters by 24% and Antwerp Chocolatier by 21%. |
| 2:05 | **Open as scenario** on row 1 | Results show the same 1.06%; company rows list their business units; propagation paths, *View in graph*, Monte Carlo and exports are the existing screens. |
| 2:25 | Back to the finder → **Optimise**, budget 3 | Plan costs $2.55M a year (placeholder costs); mean impact of the 10 worst events goes from 3.23% to 3.07% of annual value added (4.83% lower); brute force over 82 plans in its 10-candidate pool finds nothing better (gap 0.0%); reduction positive in 50 of 50 draws. At budget 2 it is 4.48%. |
| 2:45 | Close | "A ranking that survives our own parameter uncertainty, with every assumption on screen, holdings counted as the companies they are. It is not validated against real losses; the data for that is not public." |

## What is verified, and what is not
- **Software correctness (verified):** an independent scalar re-implementation of the model, written from the documented formulas, matches the engine to about 1e-10 on all 102 final disruptions for 24 events. Finder impact, hidden share and promoted-scenario impact agree for all 200 listed events (differences are display rounding, at most 6.5e-6). The optimiser's baseline and plan objective match the reference. Enumerating all 184 affordable plans over all 14 candidates at budget 2 confirms the optimum.
- **Company view (verified 10 October 2026):** the business-unit view reproduces every v0.3 output field by field (finder top 100 events with 200 draws, six scenarios, optimiser: 0 differences). Company-level disruption equals the value-added-weighted average of its units in every listed event and comparison row (tested), and six injected bugs in the company logic are all caught by the tests. Enumerating all affordable plans over all 14 candidates confirms the optimiser's plan (166 plans at budget 2, 481 at budget 3).
- **Robustness under assumptions (verified):** 200 draws are used, the seed is recorded and reproduces exactly, seeds 1, 7, 99 and 12345 and 1000 draws all give the same top hidden-only event at 100% (rechecked in the company view), and a shortlist of 300 gives the same top rows as 100.
- **Empirical validation (none):** no observed disruption or loss data was used, and the back-test demo is circular. Do not say "accurate", "validated" or "saves".

## Likely judge questions
**Is this real data?** No. Entities, links, coordinates, weights, vulnerabilities and costs are synthetic. The only real dataset is the JRC / Copernicus 100-year river-flood map, sampled around the synthetic coordinates. It is a lenient plausibility filter: 92 of 100 entities have some modelled flooding within 5 km, so passing it says little. It never feeds a loss figure.

**Is a loss of 1.06% a prediction?** No. It is the model's position-weighted share of annual value added lost over a 210-day window for a reference drought. There are no event probabilities, so events are ranked by consequence, not likelihood.

**What does 100% mean?** The event stays in the hidden-only top 5 in all 200 parameter draws (shared factors for intensity, damage steepness, recovery, vulnerability, dependency, substitutability, alternatives, spare capacity and inventory, plus per-entity and per-link noise). It shows the ranking is robust to those assumptions. It does not show the assumptions are right.

**How is this different from a climate dashboard?** A dashboard evaluates the scenario you chose. The finder searches for the scenarios that matter and reports the share a site-based screen cannot see. Reverse stress testing itself is established practice in bank supervision (EBA/GL/2018/04); applying it to a firm-level food supply graph is a product choice, not a research claim.

**Why trust the engine?** Its numbers match an independent re-implementation, and mutation testing (24 injected bugs, all caught by the test suite after additions) shows the tests check behaviour, not just that fields exist.

**Is the optimiser really optimal?** Within its model and costs, yes: greedy plus swap search, checked against exhaustive enumeration (company view at budget 2: 38 plans in its 10-candidate pool, 166 over all 14, same optimum; business-unit view: 84 and 184). Costs are placeholders and events are unweighted, so it is the best plan under stated assumptions, not a recommendation.

**Why does a hidden exposure count change with the threshold?** It does. At cut-offs of 1%, 2%, 5% and 10% the Rotterdam scenario shows 5, 5, 3 and 1 hidden exposures among companies (5, 4, 3 and 1 among business units), so the app shows the curve, not one number.

**Most companies have several businesses (ITC sells biscuits and cigarettes). Does a biscuit hit sink the stock?** That is why holdings are now companies. A company's disruption is the value-added-weighted average of its business units, so in Five Rivers Consumer Group (synthetic, ITC-like) the Punjab-Haryana flood that disrupts the biscuit unit by 69.6% disrupts the company by 18.8%. Its 55% outside food and beverage is not modelled: if those businesses were hit as hard, it would be 41.9%. Two caveats. First, we model no stock prices and no growth elsewhere, because offsetting a loss with growth is a forecast. Second, diversification is not immunity: studies find shocks travelling between a firm's own plants (Giroud & Mueller 2019; Seetharam 2018), so the app also shows the one-node extreme (91.3%). Treating every company as one node, which company-level supplier data implies, would overstate the 10 worst events by about 25% (4.04% vs 3.23%).

**What is missing?** Real supplier links, observed outcomes for back-testing, supplier rewiring, demand and price effects, time-to-impact, coastal and surface-water flooding, event probabilities, real company structures, profit-weighted (rather than value-added) company shares, and spillovers between a company's own units.
