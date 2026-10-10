# Data sources

| Source | Role in this release | Licence | Status |
|---|---|---|---|
| Synthetic F&B entities, relations, scenarios | Everything the app computes on | Project-generated | In use; clearly labelled synthetic |
| Synthetic company structures (`backend/data/companies.json`) | Which business units a listed holding owns, and its share of value added outside Food & Beverage (company view of the portfolio) | Project-generated | In use; invented groupings, no real company's structure; the non-F&B share is never modelled |
| Sectivia U.S. supply-chain graph (`backend/data/reference/sectivia/`) | Reference graph format; generic-tooling test; audit shown in the UI | CC BY 4.0. *Supply-chain data: Sectivia (https://sectivia.com), CC BY 4.0* | **Not** used as food data (215 companies in AI, energy, defence, medicine, quantum, finance; 350 unweighted links; 98.6% USA; no coordinates; no per-link source in the files supplied) |
| JRC / Copernicus CEMS global river flood hazard maps v2.1.2 (`backend/data/hazard_layers/jrc_flood_rp100.json`) | Real hazard context: share of ~90 m cells flooded in the 100-year river flood within 5 km of each entity's synthetic coordinate. Shown on the entity page; flags or drops implausible flood events in the finder. Never a loss input | CC BY 4.0, © European Union 1995–2026. Cite: Baugh, C., Colonese, J., D'Angelo, C., Dottori, F., Neal, J., Prudhomme, C., Salamon, P. (2024). *Modelled flood inundation for different return period scenarios at the global scale.* European Commission, JRC | **Integrated offline** by `backend/data/fetch_jrc_flood.py` (23 tiles, 100 entities, retrieved 9 Oct 2026). River flooding only; real data at synthetic coordinates |
| World Bank CCKP | Planned hazard/climate provider | CC BY 4.0 (per evidence review) | **Not integrated** |
| Open-Meteo (ERA5, CMIP6 downscaled, GloFAS) | Planned provider | Free non-commercial ≤10 000 calls/day (per evidence review) | **Not integrated**; its flood API returns river discharge, not inundation depth |
| FIN-04 evidence review and problem breakdown (project documents) | Constraints on claims, evidence labels, design choices | n/a | Used as design input |

Licences and API limits for the two unintegrated sources are quoted from the evidence review and have **not** been re-verified; check them before integrating. To integrate a provider, implement `HazardProvider.footprint_weights` in `models/climate.py` and register it in `PROVIDERS`; keep hazard intensity, discharge, depth and damage as separate quantities.

The dataset manifest (`backend/data/manifest.json`) is served at `GET /api/v1/data/sources` and shown on the *Data & methodology* page.
