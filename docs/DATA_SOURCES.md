# Data sources

| Source | Role in this release | Licence | Status |
|---|---|---|---|
| Synthetic F&B entities, relations, scenarios | Everything the app computes on | Project-generated | In use; clearly labelled synthetic |
| Sectivia U.S. supply-chain graph (`backend/data/reference/sectivia/`) | Reference graph format; generic-tooling test; audit shown in the UI | CC BY 4.0. *Supply-chain data: Sectivia (https://sectivia.com), CC BY 4.0* | **Not** used as food data (215 companies in AI, energy, defence, medicine, quantum, finance; 350 unweighted links; 98.6% USA; no coordinates; no per-link source in the files supplied) |
| World Bank CCKP | Planned hazard/climate provider | CC BY 4.0 (per evidence review) | **Not integrated** |
| Open-Meteo (ERA5, CMIP6 downscaled, GloFAS) | Planned provider | Free non-commercial ≤10 000 calls/day (per evidence review) | **Not integrated**; its flood API returns river discharge, not inundation depth |
| FIN-04 evidence review and problem breakdown (project documents) | Constraints on claims, evidence labels, design choices | n/a | Used as design input |

Licences and API limits for the two unintegrated sources are quoted from the evidence review and have **not** been re-verified; check them before integrating. To integrate a provider, implement `HazardProvider.footprint_weights` in `models/climate.py` and register it in `PROVIDERS`; keep hazard intensity, discharge, depth and damage as separate quantities.

The dataset manifest (`backend/data/manifest.json`) is served at `GET /api/v1/data/sources` and shown on the *Data & methodology* page.
