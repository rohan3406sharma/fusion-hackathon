"""Scenario resolution + cached model execution used by the API layer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, model_validator

from ..config import get_settings
from ..db import ScenarioRow, session
from ..models.montecarlo import run_monte_carlo
from ..schemas.results import MonteCarloResult, RunResult
from ..schemas.scenario import ScenarioRecord, ScenarioSpec
from .runner import build_run_result, execute
from .state import get_state, spec_key

DEFAULT_SCENARIO_ID = "sc_punjab_flood"


class ScenarioRef(BaseModel):
    """Either a stored scenario id or an inline scenario specification."""
    scenario_id: Optional[str] = None
    scenario: Optional[ScenarioSpec] = None

    @model_validator(mode="after")
    def _one(self):
        if (self.scenario_id is None) == (self.scenario is None):
            raise ValueError("provide exactly one of scenario_id or scenario")
        return self


def record_from_row(row: ScenarioRow) -> ScenarioRecord:
    return ScenarioRecord(id=row.id, builtin=row.builtin, created_at=row.created_at, **json.loads(row.spec_json))


def load_record(scenario_id: str) -> ScenarioRecord:
    with session() as s:
        row = s.get(ScenarioRow, scenario_id)
    if row is None:
        raise HTTPException(404, f"scenario '{scenario_id}' not found")
    return record_from_row(row)


def validate_spec_against_dataset(spec: ScenarioSpec) -> None:
    ids = set(get_state().dataset.by_id)
    for h in spec.hazards:
        bad = [i for i in h.affected_entity_ids if i not in ids]
        if bad:
            raise HTTPException(422, f"unknown affected_entity_ids: {bad}")


def resolve(ref_id: Optional[str], inline: Optional[ScenarioSpec]) -> tuple[Optional[str], ScenarioSpec]:
    if (ref_id is None) == (inline is None):
        raise HTTPException(422, "provide exactly one of scenario_id or scenario")
    if ref_id is not None:
        rec = load_record(ref_id)
        return rec.id, ScenarioSpec(**rec.model_dump(exclude={"id", "builtin", "synthetic", "created_at"}))
    validate_spec_against_dataset(inline)
    return None, inline


def save_scenario(spec: ScenarioSpec, sid: str) -> ScenarioRecord:
    validate_spec_against_dataset(spec)
    with session() as s:
        s.add(ScenarioRow(id=sid, name=spec.name, spec_json=spec.model_dump_json(), builtin=False,
                          created_at=datetime.now(timezone.utc).isoformat()))
        s.commit()
    return load_record(sid)


def run(spec: ScenarioSpec, scenario_id: Optional[str], max_depth: Optional[int] = None, top_paths: int = 10) -> RunResult:
    st = get_state()

    def compute() -> RunResult:
        return build_run_result(st.dataset.entities, st.dataset.relations, spec, scenario_id, top_paths, max_depth)

    return st.cache.get_or_set("run:" + spec_key(spec, max_depth, top_paths, scenario_id), compute)


def monte_carlo(spec: ScenarioSpec, n: int, seed: int, max_depth: Optional[int] = None) -> MonteCarloResult:
    if n > get_settings().max_monte_carlo_runs:
        raise HTTPException(422, f"n_simulations exceeds limit {get_settings().max_monte_carlo_runs}")
    if n < 20:
        raise HTTPException(422, "n_simulations must be at least 20 for meaningful quantiles")
    st = get_state()

    def compute() -> MonteCarloResult:
        det = execute(st.dataset.entities, st.dataset.relations, spec, max_depth)
        total = float(det.losses()[1].sum())
        return MonteCarloResult.model_validate(run_monte_carlo(st.dataset.entities, st.dataset.relations, spec, n, seed, total, max_depth))

    return st.cache.get_or_set("mc:" + spec_key(spec, n, seed, max_depth), compute)
