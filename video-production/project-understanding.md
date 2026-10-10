# Project understanding (internal)

Written before production, from the repository, its docs, the two project documents in
`read this before building/`, and a live run of the app on 9 October 2026 (isolated backend on :8001
with a fresh database, frontend on :5174). Every number below was read from the running API.

## The central problem
Climate screens for investors usually check **where a company's own sites are**: is this factory in a
flood zone, too hot, too dry? But companies depend on suppliers, power, ports, cold storage and
hauliers they do not own. A hazard at one of those upstream nodes can disrupt a holding whose own
sites are untouched. The FIN-04 brief calls this **hidden climate exposure**: risk the portfolio has
but a location-only check cannot see.

Why it matters: the direction of the effect is well documented (a disaster at a supplier cuts its
customers' output; Barrot & Sauvagnat 2016, Carvalho et al. 2021), but the links themselves are
mostly undisclosed, and the evidence review found **no study comparing network-aware and
location-only exposure on the same portfolio**.

## Audience and pain points
Portfolio climate-risk analysts, risk managers and stress-testing teams (and hackathon judges).
Pain points: site-level screens miss supply-chain routes; scenario tools make you guess the scenario;
indirect-loss "multipliers" are unstable across studies (1.4x to 30x); real supplier data is sparse.

## How the application works (input to output)
1. **Data** (all synthetic except one layer): 102 food-and-beverage entities, 240 relationships (232
   supply, 8 financial), an 18-holding portfolio with synthetic weights. One real dataset: the JRC /
   Copernicus 100-year river-flood map, sampled at the synthetic coordinates as context and a
   plausibility filter, never as a loss input.
2. **Event library**: about 780 synthetic climate events (single-node shocks plus 150 km and 350 km
   footprints) for flood, heat and drought.
3. **Direct exposure**: hazard intensity x exposed asset share x vulnerability, through a saturating
   damage proxy and a duration factor.
4. **Propagation**: a vectorised NumPy engine pushes disruption hop by hop along supply edges. Each
   edge's transmission depends on dependency, input specificity, substitutability, inventory, graph
   alternatives with spare capacity, and feedback-loop damping; shocks shrink each hop.
5. **Hidden Exposure Finder** (portfolio reverse stress test): scores every event against the
   portfolio, collapses near-duplicates, reports the hidden share (the part a location-only screen
   misses), re-ranks under 200 seeded uncertainty draws (P(top 5), fragile flags), builds a
   "who can hurt whom" matrix and a single-points-of-failure list.
6. **Promote to scenario**: any finder event becomes an ordinary scenario; the results page shows
   losses by propagation order (each with its evidence strength), critical paths, View in graph,
   location-only vs network-aware comparison with rank changes, Monte Carlo and exports.
7. **Resilience optimiser**: picks interventions under a budget to cut the mean impact of the worst
   10 events, checked against brute force.
8. **AI copilot** (optional, local Ollama): explains results in plain language but never calculates;
   every number is filled in by the server and validated.

Stack: FastAPI + NetworkX/NumPy/SciPy + SQLite backend; React 19 + Vite + Tailwind + Cytoscape +
Recharts frontend. 164 backend tests, 29 frontend tests, 26-step browser E2E (per docs/TESTING.md).

## Strongest real features (verified live)
| Feature | Live result (default data, seed 42, 200 draws) |
|---|---|
| Finder search | 780 events scored in 0.41 s; 268 distinct; **165 hidden-only** |
| Top hidden-only event | **Drought at Dutch Regional Grid Operator**: portfolio impact **1.13%** of annual value added; location-only **0.00%**; reaches 3 holdings; **P(top 5) = 100%** |
| Fragility | rows 4 and 5 (Daloa cocoa 39%, San-Pedro cocoa 38%) flagged *Fragile* |
| Broadest hidden-only event | Flood at Rotterdam Terminal Operator reaches **7 holdings** (rank 18 by size) |
| Top single point of failure | Rotterdam Terminal Operator: 60-day outage disrupts Hamburg Coffee Roasters **24%**, Antwerp Chocolatier **21%** |
| Promoted scenario (grid drought) | grid operator 30.2% disrupted; path **Grid -> Utrecht Cheese and Yogurt Maker (25.7%) -> Rhineland Grocery Group (6.7%)**; portfolio 0.00% -> 1.13%; Utrecht rank 9.5 -> 1 |
| Optimiser, budget $3M/yr | plan $2.46M/yr; tail impact **3.25% -> 3.09%** (4.98% lower); brute force over 197 plans: gap 0%; positive in 50 of 50 draws |
| Ranking stability | Kendall tau of top 20 = 0.98 across 200 draws |

## Most visually interesting demonstration
Finder search -> the hidden-only table (1.13% vs 0.00%) -> Open as scenario -> the critical path
from a power utility, through a cheese maker, to a grocery chain -> View in graph. Then the
optimiser closing the loop.

## What makes it distinctive
- It **searches for the events that matter** (reverse stress test) instead of evaluating a scenario
  the user picked, and reports how much of each loss is invisible to a location-only screen.
- Honesty is built in: synthetic labels everywhere, per-hop evidence strength, uncertainty draws,
  fragile flags, a lenient real-data plausibility check stated as lenient, an optimiser checked
  against brute force, and a copilot that cannot compute.
- No universal indirect-loss multiplier: the ratio is an output of each scenario.

## Limitations to state honestly in the video
- All entities, links, coordinates, weights, vulnerabilities and costs are **synthetic**. The only
  real data is the JRC river-flood layer, used as context.
- Results are model estimates: **not calibrated, not validated, not forecasts**. Events carry no
  probabilities, so rankings are by consequence, not likelihood.
- Stability under parameter draws shows internal consistency, not real-world accuracy.
- Missing: real supplier links, observed outcomes for back-testing, rewiring after shocks, demand
  and price effects, coastal/surface-water flooding, event probabilities.
