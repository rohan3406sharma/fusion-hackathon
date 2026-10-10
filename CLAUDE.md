# FIN-04 Climate Exposure Graph (Food & Beverage only)

Network-aware climate stress testing on a SYNTHETIC F&B supply chain. FastAPI + NetworkX/NumPy backend, React/Vite/Tailwind/Cytoscape frontend.

## Rules that must not regress
- Food & Beverage only. Do not add other industries. Never relabel Sectivia (non-food) companies as food companies.
- Holdings are companies (`companies.json`, generated): a company owns F&B business units (entities) and may carry ONE `other_businesses_share` for businesses outside F&B. That share is never modelled (no nodes, links, hazard or named industry); it only dilutes. Keep the `business_unit` view reproducing v0.3 exactly (`tests/test_holdings.py`). No real company names or figures in the data.
- All entities/edges/scenarios are synthetic and labelled so (`synthetic`, `status`, `provenance`). Never present synthetic data as observed.
- No universal indirect-loss multiplier; third-order+ results are model-based/low confidence; no claim of validation.
- Keep distinct: hazard intensity, exposure, vulnerability, direct loss, propagated loss. Keep dependency/specificity/substitutability/confidence as separate edge attributes.
- Dataset is generated: edit `backend/data/generate_dataset.py`, then rerun it. Do not hand-edit the JSON.
- The JRC flood layer is the only real data: context and a plausibility filter at synthetic coordinates, never a loss input. Regenerate with `data/fetch_jrc_flood.py` (requirements-data.txt), keep its citation and licence.
- Copilot: the language model may only choose and phrase cited facts. Every value/name/path is rendered by the server from the fact sheet; a reply that fails `copilot/grounding.py` is replaced by templates. Never let it compute, give advice, or state probabilities/savings; `empirically_validated` provenance must never be emitted. Anthropic is optional and off by default; keys stay server-side.
- Finder rankings are by consequence (no event probabilities); stability under draws is internal consistency, not validation. Do not call sorted lists an optimiser.

## Commands
- Backend: `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000`; tests: `../.venv/bin/python -m pytest -q`
- Frontend: `cd frontend && npm run dev`; tests: `npm test`; build/typecheck: `npm run build`
- E2E (needs both servers + Chrome + puppeteer-core): `cd scripts && npm i && npm run e2e`

## Layout
`backend/app/{models (pure algorithms), services (orchestration/cache), api/routes.py, schemas, domain (dataset, holdings = company view)}`, `docs/` has METHODOLOGY (formulas), ARCHITECTURE, DATA_*.
