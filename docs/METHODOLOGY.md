# Methodology

Every formula below is implemented in `backend/app/models/` and covered by tests. Parameters are configurable proxies, **not** calibrated or validated values. Notation: *d* = disruption fraction in [0,1] (share of normal output lost), *u→v* = supplier→customer.

## 1. Direct exposure (`models/climate.py`)
Kept distinct: hazard intensity **H** (dimensionless scenario index 0–1 from the provider, at the facility), exposure **E** (share of the entity's asset base inside the footprint, `exposed_asset_share`), vulnerability **V** (per-hazard sensitivity, synthetic).

```
s_c  = 1 − exp(−k_h · H_ic · E_i · V_ih)          saturating severity
D_c  = 1 − exp(−duration_c / τ_h)                  duration factor
f_c  = s_c · D_c
d0_i = 1 − Π_c (1 − f_c)       × (1 + amp) if ≥2 hazards overlap (analyst-set amp, default 0), capped at 1
```
Hazard constants: flood k=3, τ=10 d, recovery 21 d · heat k=2.5, τ=7 d, recovery 7 d · drought k=2.5, τ=90 d, recovery 90 d. Footprint (synthetic): weight 1 inside radius R, Gaussian fall-off `exp(−((d−R)/0.5R)²)` beyond; or named regions; or explicit entity ids. **Not** a validated damage function; a hazard score is not a probability of loss.

## 2. Weighted directed graph
Edge u→v, product p. Separate attributes: `dependency` (share of v's input of p supplied by u; Σ ≤ 1 per (v,p), remainder = unmodelled suppliers), `input_specificity` (how essential), `substitutability` (a different input could replace it), `confidence`, `status` (disclosed | inferred | synthetic | modelled), `provenance`, `lead_time_days`, `storable`. No single blended weight.

## 3. Multi-hop propagation (`models/propagation.py`)
Per-edge transmission (v0.2):
```
τ_e(d) = dep_e · spec_e · (1 − sub_e) · inv_e · damp_e · (1 − a_mkt,e) · (1 − a_graph,e(d))
inv_e    = clip((T − (I_v + L_e)) / T, 0, 1)                 if the good is storable, else 1
damp_e   = cycle_damping (default 0.5) if the link lies inside a feedback loop (strongly connected component), else 1
a_mkt,e  = alt_v · (1 − Σ modelled dependency shares of that input)          suppliers OUTSIDE the graph (assumption)
a_graph,e(d) = min(0.95, Σ_w spare_w · (1 − d_w) / (n_w · flow_e))          modelled same-product producers w
```
`T` = event + recovery days; `I_v` = v's input inventory days; `L_e` = lead time (pipeline stock keeps arriving). `spare_w` = revenue × spare-capacity fraction of an eligible alternative producer w (same product, not the supplier or customer; non-storable goods and services only from the customer's country). `n_w` = number of links w could serve, so its spare capacity is shared rather than counted once per customer. Because `a_graph` falls as the alternatives themselves are disrupted, a regional drought that hits every producer of a crop leaves little relief. Each relief mechanism is capped at 0.95. Scenario scales multiply inventory, both alternative terms and substitution, and dependency. `use_graph_alternatives=false` restores the v0.1 rule (alt_v applied to the whole input).

**Why v0.2 changed this.** In v0.1 `alt_v` was a free number per entity, uncorrelated (r = 0.02) with the number of same-product producers in the graph, and 85 of 232 inputs had no alternative producer yet still received relief. Feedback loops were undamped: a two-node loop at dependency 1.0 drove disruption from 0.5 to about 1.0.

State update (bounded, no double counting):
```
g_{v,p}   = min(1, Σ_{e into v, product p} d_u · τ_e)        additive within one input
d_in_v    = 1 − Π_p (1 − g_{v,p})                            noisy-OR across different inputs
d_v(t+1)  = 1 − (1 − d0_v)(1 − d_in_v(d(t)))                  direct and input shortfall never exceed 1
```
Iteration *t* equals propagation through *t* hops, so first/second/third-order effects are state differences `d(t) − d(t−1)`. The map is monotone and bounded, so cycles (e.g. cold store ↔ reefer fleet, flagged by validation and kept) converge to a fixed point or stop at the depth cap (default 6, max 10, tolerance 1e-6). Loss = `value_added × d × min(1, T/365)`; value added (not revenue) limits chain double counting. Hop order of an entity = first step at which its propagated disruption exceeds 1e-4. Shocks shrink naturally with each hop (τ_e < 1), in line with the attenuation reported by Carvalho et al.

## 4. Alternative sourcing & substitution (`models/mitigation.py`)
Diversification moves a share of a supplier's flow to other producers of the same product, limited by their spare capacity `revenue × spare_fraction × (1 − 2·d0)` (affected suppliers cannot help; non-storable goods/services stay within the supplier's country). New edges are labelled `modelled`. Substitution raises `sub_e`. Inventory adds days to `I_v`. Protection/cold-chain/relocation reduce vulnerability. Baseline vs mitigated runs use the same engine.

## 5. Graph analytics & systemic vulnerability score (`models/analytics.py`)
In/out-degree, weighted out-dependency, betweenness (distance `−log(dep·spec)`), PageRank on the reversed graph (high = heavily depended upon), downstream reach, weak components, cycles, single-source dependencies (sole supplier of an input with dep ≥ 0.6). Score (0–100) = Σ w_k · minmax(component_k), default weights: direct exposure .25 (dropped if no scenario), downstream reach .20, weighted dependency .15, lack of alternatives .15, inventory fragility .10, criticality .15. Components and point contributions are returned. It is a ranking aid; **never** converted to money; centrality ≠ climate risk.

## 6. Monte Carlo (`models/montecarlo.py`)
Seeded (`numpy.random.default_rng`). Every input group has a **shared (global) factor** per draw and, where it varies by item, a **local** factor: intensity × Triangular(0.7,1,1.3); damage steepness k × LogNormal(0,0.2); recovery days × Uniform(0.5,1.5); vulnerability × LogNormal(0,0.25) shared × LogNormal(0,0.15) per entity; dependency × LogNormal(0,0.15) shared × LogNormal(0,0.15) per link (input groups rescaled if > 1); substitutability + N(0,0.08) shared + N(0,0.08) per link; market alternatives + N(0,0.08) shared + N(0,0.08) per entity; graph-alternative relief × LogNormal(0,0.3) shared; inventory × LogNormal(0,0.2) shared × LogNormal(0,0.2) per entity. Sensitivity = Spearman correlation of each **shared** factor with total loss and with indirect loss, plus ρ² normalised as an approximate variance share.

**Why v0.2 changed this.** v0.1 sampled only independent per-link noise. Averaged over 232 links it had almost no variance, so the panel reported dependency and substitutability as irrelevant (ρ ≈ −0.01, −0.06). Yet a ±30% global change in substitution moved indirect loss from $184M to $64M. On the Brazil drought the repaired engine gives indirect-loss ρ = 0.54 for dependency and −0.45 for substitutability (regression-tested). Damage steepness and recovery time were not sampled at all; ±30% on k moved the total from $413M to $613M.

The p05–p95 range is a *scenario-uncertainty range under analyst-defined input ranges*, not a confidence interval; structural model error is excluded.

## 7. Network-aware vs location-only
Location-only = Σ direct losses. Network-aware = Σ direct + modelled indirect. Reported for the whole network (USD M) and for the synthetic portfolio (16 companies by default, 18 business units in the business-unit view; §7c) as a **position-weighted share of annual value added lost**: `Σ_h w_h · d_h · T/365`, with `d_h` the holding's disruption (company level: §7c). Weights are in `data/portfolio.json`, proportional to the √revenue proxy; they are synthetic, not market caps. Relative difference is null when the denominator is zero. Rank changes use disruption fractions; ties share the average rank, and holdings untouched in both views report no rank change. *Hidden exposure* = holding with direct disruption < 1% but propagated ≥ 5%. Because that count depends on the cut-off, a curve at 1%, 2%, 5% and 10% is reported beside it. This is a model comparison; the evidence review found **no** study comparing the two on the same portfolio.

## 7a. Hidden Exposure Finder: portfolio reverse stress test (`models/events.py`, `models/reverse_stress.py`, `services/finder.py`)
Reverse stress testing starts from the outcome and searches for the events that cause it (EBA/GL/2018/04, definition 10). Here:

1. **Event library (synthetic).** Every non-financial entity as a single-node shock (if its vulnerability to the hazard is ≥ 0.3), plus circular footprints of 150 and 350 km around every located entity and every region centroid, for flood, heat and drought. Footprints that reach nothing vulnerable are dropped; identical footprints are de-duplicated. Reference intensity 0.8 and durations of 21, 14 and 120 days are analyst choices. About 780 events; no probabilities, so events are ranked by consequence, not likelihood.
2. **Batch scoring.** Every event runs through the same direct-exposure proxy and propagation engine, as rows of one array (about 0.05 s for the library). For event e: `P_net(e) = Σ_h w_h d*_h T(e)/365`, `P_loc(e) = Σ_h w_h d0_h T(e)/365`, hidden share `H(e) = 1 − P_loc/P_net`. *Hidden-only* = no holding is hit directly (`P_loc = 0`) but `P_net > 0`.
3. **Near-duplicates collapsed.** In rank order, an event joins an earlier one of the same hazard if their directly hit entity sets have Jaccard ≥ 0.6 (about 780 events become about 270 distinct ones).
4. **Stability.** The top 100 distinct events are re-ranked under joint draws of the Monte Carlo factors: per event, P(top 5), median rank and interquartile range, and Kendall τ of the top 20, for all events and for hidden-only events separately. A test checks that a 200-event shortlist gives the same top 5. An event in the deterministic top 5 with P(top 5) < 0.5 is labelled *fragile*.
5. **Who can hurt whom.** For each node the portfolio does not own, its worst single-node climate event gives a row of losses per holding; rows with several dark cells are shared upstream dependencies.
6. **Single points of failure (structural).** A full 60-day outage of one upstream node; a node is listed if it disrupts a holding by ≥ 20%. Dominator trees, proposed in the review, were not used: they treat any path as sufficient supply, but a mill needs wheat *and* power, which the simulation respects.
7. **Structural bound.** Exhaustive search over all pairs of upstream outages (3,321 pairs), compared with greedy; labelled as not a climate event.
8. **Real-data plausibility (JRC).** Flood events are checked against the JRC / Copernicus CEMS 100-year river-flood map, sampled within 5 km of each entity's approximate coordinate (see *Real hazard data used*). An event is "consistent" if any directly hit entity has modelled river flooding nearby. Mode `flag` (default) marks the others; `drop` removes them. On the default data, 18 of the top 20 flood events are consistent and 8 of 293 are not, **but 92 of 100 entities have some modelled flooding within 5 km**, so the filter is lenient and passing it carries little information. It removes only clear misfits. It is a proxy plausibility check, not validation, and covers river flooding only.

Every finder event can be promoted to an ordinary scenario; its Results page reproduces the finder's portfolio impact (integration- and E2E-tested).

## 7b. Resilience optimiser (`models/optimiser.py`, `services/optimise.py`)
- **Decision variables:** x_j ∈ {0,1}, one per candidate intervention (type, target, magnitude). Candidates are generated from where the tail events bite: protect the 4 upstream nodes behind the most portfolio loss; inventory, diversification and substitution at the 4 holdings that lose most. Users can also supply their own.
- **Constraint:** Σ c_j x_j ≤ B, with c_j the annualised placeholder cost from the mitigation cost model. Alternative-sourcing capacity is enforced inside the simulation, shared across chosen interventions.
- **Objective:** minimise the mean portfolio impact of the worst N (default 10) of the top 50 distinct events after the plan. This is a CVaR-like tail over an unweighted event set, because the library has no probabilities.
- **Method:** the objective is evaluated by simulation and is neither linear nor provably submodular. So: greedy by reduction per unit cost, then 1-swap local search. On a pool of at most 10 candidates, exhaustive enumeration reports the optimality gap. Also reported: plan stability at costs ×0.5 and ×2 (Jaccard), a paired comparison across uncertainty draws, and the greedy frontier.
- **Result in the company view (default, 10 October 2026):** at $3M per year the plan costs $2.55M and cuts the mean tail impact from 3.228% to 3.072% of annual value added (4.83% lower), with a gap of 0 against brute force over 82 affordable plans in its 10-candidate pool and a positive reduction in 50 of 50 draws; at $2M it is 4.48% lower (38 plans, gap 0).
- **Result in the business-unit view (v0.3 numbers, 9 October 2026):** at $2M per year the plan cuts tail impact by 4.7%, with a gap of 0 against brute force over 84 feasible plans, and the reduction is positive in 50 of 50 draws. An independent enumeration of all 184 affordable plans over all 14 candidates confirms the same optimum; the figure is a 4.66% relative reduction in the mean tail impact (3.254% to 3.102% of annual value added). Some diversification candidates *increase* loss when the alternatives are themselves exposed, and the optimiser skips them. All costs are placeholders, so this is the best plan under stated assumptions, not a recommendation.

## 7c. Holdings as companies (multi-segment holdings) (`domain/holdings.py`)
A listed holding is a company, and many companies own several businesses (a judge's example: an Indian group with packaged foods next to much larger non-food businesses). Treating one held business unit as the whole holding overstates the company-level hit; treating the whole company as one node, which is what company-to-company supplier data such as Sectivia implies, overstates it further, because a shortfall of any one input then stops every business.

```
d_h        = Σ_s a_hs d_s          a_hs = share of company h's value added in business unit s (synthetic value added); Σ_s a_hs = 1 − o_h
upper_h    = d_h / (1 − o_h)       o_h  = share of h's value added OUTSIDE Food & Beverage: not modelled (no nodes, links or hazard), adds no loss to d_h
one node_h = 1 − Π_s (1 − d_s)     any unit's shortfall stops the whole company (noisy-OR): the opposite extreme
P(e)       = Σ_h W_h d_h(e) T(e)/365 = (d(e) · Aᵀ W) T(e)/365
```
- Each business unit is an ordinary entity and propagation is unchanged. Spreading company weights over their units (`w = AᵀW`) makes finder scoring, stability draws, the pair bound and the optimiser objective company-aware with no new engine code.
- **Same money.** A company's position weight is the sum of its held units' weights in `portfolio.json`. Units it owns that the portfolio did not hold (an own flour mill or milk plant) join the company and dilute it; nothing is added to the portfolio.
- **Own sites.** Location-only for a company aggregates direct disruption the same way, so a hazard at any unit the company owns is direct, not hidden. Who-can-hurt-whom, single points of failure and the pair bound exclude every unit a held company owns. Hidden exposure, ranks and the ≥20% single-point threshold apply at company level.
- **Business-unit view** (`holding_view=business_unit`): every held unit is its own holding (one segment, share 1), which is the v0.3 portfolio exactly. A field-by-field comparison with the v0.3 code for the finder (top 100 events, 200 draws), all six built-in scenarios and the optimiser found 0 differences.
- **Structures** (`companies.json`, generated, synthetic): Five Rivers Consumer Group (biscuits, an own flour mill, cooking oil; 55% of value added outside F&B), Lone Star Snacks and Beverages (snacks, soft drinks, juices in three US regions), Great Plains Foods (cereal plus an own flour mill), Lowlands Dairy Group (cheese and yogurt plus an own milk plant). Patterns are stylised; names and numbers are invented.

Result on the default data (10 October 2026, seed 42, 200 draws), the same library scored four ways:

| Holdings counted as | Holdings | Hidden-only events | Top hidden-only event | Mean of the 10 worst events |
|---|---|---|---|---|
| Business units (v0.3) | 18 | 165 | Drought at Dutch Regional Grid Operator, 1.13% | 3.25% |
| Companies (default) | 16 | 152 | same event, 1.06% | 3.23% |
| Companies, non-F&B businesses hit like the rest | 16 | 152 | same event, 1.06% | 3.23% |
| Each company as one node | 16 | 153 | same event, 1.46% | 4.04% |

- **Holding level: large.** Flood, 350 km around Bharat Fresh Retail: Five Rivers' biscuit unit is 71.5% disrupted and its flour mill 73.5%, its cooking-oil unit in Mumbai 0%; the company is 19.4% disrupted, up to 43.0% if its non-F&B businesses were hit as hard, and 92.5% as one node.
- **Rankings move.** Drought at Punjab Power Grid Utility falls from 3rd to 10th among hidden-only events (0.61% → 0.36%) because the biscuit maker is now part of a larger group. Drought at Friesland Dairy Farms rises from 6th to 3rd (0.48% → 0.70%) because Lowlands Dairy owns two links of the same milk chain: diversification can also concentrate risk. 13 events that are hidden-only in the business-unit view hit a unit the company owns, for example drought at Ludhiana Flour Mills.
- **Portfolio level: small.** The same money still sits in the same businesses, so diversification inside a company is close to owning its parts separately. What moves the portfolio is the non-F&B share, vertical integration, and one-node modelling (+25% on the mean of the 10 worst events).
- **Not immunity.** Shocks also travel between a firm's own units: regional shocks propagate through firms' establishment networks, more so in financially constrained firms (Giroud & Mueller 2019, *AER*); for each manufacturing job lost in a hurricane-hit US county, a further 0.19–0.25 are lost in the same firms' undisrupted regions, in resource-constrained firms only (Seetharam 2018, job-market paper). Units are treated as separate businesses here; the one-node view bounds this from above. An internal-spillover parameter is a possible extension, not implemented.
- **Not modelled:** stock prices, growth in other businesses, margins or earnings (shares are value added, not profit), and anything about the non-F&B businesses beyond their share.

## Real hazard data used
JRC / Copernicus CEMS global river flood hazard maps v2.1.2 (Baugh et al. 2024; © European Union, CC BY 4.0), 100-year return period, classified depth. `backend/data/fetch_jrc_flood.py` samples the share of ~90 m cells flooded (and deeper than 1 m) within 5 km of each located entity, and writes `data/hazard_layers/jrc_flood_rp100.json`. It is used as context on the entity page and as the finder's flood-plausibility filter, never as a loss input. The denominator is every ~90 m cell in the window (the raster codes sea, permanent water and dry land alike as 255), so coastal shares are diluted. Windows are truncated at tile edges, not stitched from neighbouring tiles; `window_coverage` records the fraction of the circle sampled (4 of 100 entities are below 0.9, the lowest 0.57). An independent exact-haversine re-sampling agrees with the stored shares to within 0.007.

## 8. Back-testing
`POST /analysis/backtest` compares simulated disruption with user-supplied observations (MAE, RMSE, bias, Spearman, precision/recall at 5%). No historical dataset is bundled and **no validation has been performed**. The `use_synthetic_demo` option perturbs the model's own output and is labelled circular.

## 9. Mitigation prioritisation (Mitigation laboratory)
Benefit = baseline loss − mitigated loss. Annualised cost = capex/10 y + opex (inventory: carrying cost 12%/yr; diversification: onboarding + 3% price premium on shifted flow; protection ∝ value added; relocation ∝ revenue). Annual expected benefit = benefit × analyst-set event probability (default 10%, shown with ×0.5/×2 sensitivity as BCR range). Priority score = 100·Σ w·{benefit .35, BCR .25, feasibility .15, speed .10, estimate confidence .15}, all normalised and shown. **Costs, times and feasibility are synthetic placeholders.** This ranks a fixed candidate list; it is not a constrained optimiser. The optimiser is §7b.

## Evidence strength (from the FIN-04 evidence review)
| Claim | Support |
|---|---|
| Supplier shock reaches direct customers | High for direction, moderate for size (5 independent firm-level studies) |
| Second order | Low–moderate (two studies; one non-climate natural experiment) |
| Third order | Low; simulation models only |
| Network vs location portfolio exposure | Low; each part supported, end-to-end untested |
| Hazard → financial loss | Uncertainty large; models and scores disagree |

Safeguards implemented: direct/indirect/deeper-hop separated everywhere; per-order evidence labels; no universal multiplier (the indirect/direct ratio is an output of each scenario and varies widely); ranges beside point values; observed/inferred/synthetic status on every record; coverage and missing-data reporting; limitations beside headline numbers.

## Known limitations
- Static edges within a run (the evidence says customers re-wire after shocks); only the mitigation lab and optimiser add links.
- No demand or price effects; one disruption window per event for every entity, so downstream entities behind inventory are charged the full window (no time-to-impact).
- Synthetic entities, links, coordinates, vulnerabilities, portfolio weights and costs. The only real data is the JRC river-flood layer, used as context and as a plausibility filter at synthetic coordinates.
- The finder's events carry no probabilities: rankings are by consequence. Stability under parameter draws is internal consistency, not validation.
- Financial channel not propagated; footprints are circular.
- Company structures are synthetic; units inside a company are treated as separate businesses (no internal spillover), and the share outside Food & Beverage is a single unmodelled number.
- Value-added loss over a single window, not an annual expected loss.
- Monte Carlo excludes structural model error.
