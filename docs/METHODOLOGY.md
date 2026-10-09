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
Per-edge transmission:
```
τ_e = dep_e · spec_e · (1 − alt_v)(1 − sub_e) · inv_e
inv_e = clip((T − (I_v + L_e)) / T, 0, 1)   if the good is storable, else 1
```
`T` = event + recovery days; `I_v` = v's input inventory days; `L_e` = lead time (pipeline stock keeps arriving). `alt_v` (market alternatives) and `sub_e` (input substitution) are different mechanisms so they multiply; each capped at 0.95. Scenario scales multiply inventory, alt/sub, and dependency.

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
Seeded (`numpy.random.default_rng`). Samples: hazard intensity × Triangular(0.7,1,1.3); vulnerability × LogNormal(0,.25) global × LogNormal(0,.15) per entity; dependency × LogNormal(0,.2) per edge (groups rescaled if > 1); substitutability + N(0,.1); inventory × LogNormal(0,.3); alternative-supplier availability + N(0,.1). Returns mean, median, p05/p25/p75/p95, histogram, Spearman sensitivities, per-entity quantiles. The p05–p95 range is a *scenario-uncertainty range under analyst-defined input ranges*, not a confidence interval; structural model error is excluded.

## 7. Network-aware vs location-only
Location-only = Σ direct losses. Network-aware = Σ direct + modelled indirect. Reported for the whole network and for an 18-holding equal-weight synthetic portfolio, with absolute and relative difference (relative is null when the denominator is zero), and rank changes by disruption fraction. Ties share the average rank, and holdings untouched in both views report no rank change (a tie is not a ranking). *Hidden exposure* = holding with direct disruption < 1% but propagated ≥ 5%. This is a model comparison; the evidence review found **no** study comparing the two on the same portfolio.

## 8. Back-testing
`POST /analysis/backtest` compares simulated disruption with user-supplied observations (MAE, RMSE, bias, Spearman, precision/recall at 5%). No historical dataset is bundled and **no validation has been performed**. The `use_synthetic_demo` option perturbs the model's own output and is labelled circular.

## 9. Mitigation prioritisation
Benefit = baseline loss − mitigated loss. Annualised cost = capex/10 y + opex (inventory: carrying cost 12%/yr; diversification: onboarding + 3% price premium on shifted flow; protection ∝ value added; relocation ∝ revenue). Annual expected benefit = benefit × analyst-set event probability (default 10%, shown with ×0.5/×2 sensitivity as BCR range). Priority score = 100·Σ w·{benefit .35, BCR .25, feasibility .15, speed .10, estimate confidence .15}, all normalised and shown. **Costs, times and feasibility are synthetic placeholders.** This ranks a fixed candidate list; it is not a constrained optimiser.

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
Static edges within a run (the evidence says customers re-wire after shocks); no demand/price effects; synthetic everything; no real hazard data; financial channel not propagated; footprint circular/synthetic; value-added loss over a single window, not an annual expected loss; Monte Carlo excludes structural error.
