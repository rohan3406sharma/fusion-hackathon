# FIN-04 Climate Exposure Graph (Food & Beverage only)

Network-aware climate stress testing on a SYNTHETIC F&B supply chain. FastAPI + NetworkX/NumPy backend, React/Vite/Tailwind/Cytoscape frontend.

## Rules that must not regress
- Food & Beverage only. Do not add other industries. Never relabel Sectivia (non-food) companies as food companies.
- All entities/edges/scenarios are synthetic and labelled so (`synthetic`, `status`, `provenance`). Never present synthetic data as observed.
- No universal indirect-loss multiplier; third-order+ results are model-based/low confidence; no claim of validation.
- Keep distinct: hazard intensity, exposure, vulnerability, direct loss, propagated loss. Keep dependency/specificity/substitutability/confidence as separate edge attributes.
- Dataset is generated: edit `backend/data/generate_dataset.py`, then rerun it. Do not hand-edit the JSON.

## Commands
- Backend: `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000`; tests: `../.venv/bin/python -m pytest -q`
- Frontend: `cd frontend && npm run dev`; tests: `npm test`; build/typecheck: `npm run build`
- E2E (needs both servers + Chrome + puppeteer-core): `cd scripts && npm i && npm run e2e`

## Layout
`backend/app/{models (pure algorithms), services (orchestration/cache), api/routes.py, schemas, domain}`, `docs/` has METHODOLOGY (formulas), ARCHITECTURE, DATA_*.
