"""Climate scenario engine: hazard provider interface + direct (facility-level) exposure assessment.

Three things are kept distinct (see docs/METHODOLOGY.md):
  * hazard intensity  H_i,c  - what the scenario/provider says happens at the location (index 0-1, NOT a physical unit)
  * exposure          E_i    - share of the entity's productive base located in the footprint
  * vulnerability     V_i,h  - sensitivity of that entity type to the hazard (synthetic proxy, 0-1)
Direct operational disruption fraction (0-1):
      s_c  = 1 - exp(-k_h * H_i,c * E_i * V_i,h)         (saturating severity; k_h is a configurable proxy constant)
      D_c  = 1 - exp(-duration_c / tau_h)                 (event has to last long enough to bite)
      f_c  = s_c * D_c
      f_i  = 1 - prod_c (1 - f_c)  (x (1+amp) if >=2 hazards overlap, capped at 1)
This is a *configurable proxy*, not a validated damage function.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..schemas.domain import Entity
from ..schemas.scenario import HazardComponent, ScenarioSpec

HAZARDS = ("flood", "heat", "drought")
# k: severity steepness; tau: duration scale (days); recovery: days before facility/crop is back after the event.
HAZARD_PARAMS = {
    "flood": dict(k=3.0, tau=10.0, recovery=21.0),
    "heat": dict(k=2.5, tau=7.0, recovery=7.0),
    "drought": dict(k=2.5, tau=90.0, recovery=90.0),
}


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    r = 6371.0
    p1, p2 = math.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


class HazardProvider(Protocol):
    """Interface for hazard data sources. Real providers (e.g. gridded rainfall/discharge/temperature) implement the same
    method and return a footprint weight in [0,1] per entity; the engine never needs to change."""

    name: str
    is_synthetic: bool

    def footprint_weights(self, entities: list[Entity], comp: HazardComponent) -> np.ndarray: ...

    def describe(self) -> dict: ...


class SyntheticFootprintProvider:
    """Deterministic, labelled-synthetic footprint: full weight inside the radius, Gaussian fall-off over 0.5R beyond it."""

    name = "synthetic_footprint"
    is_synthetic = True

    def footprint_weights(self, entities: list[Entity], comp: HazardComponent) -> np.ndarray:
        n = len(entities)
        w = np.zeros(n)
        if comp.radius_km is not None:
            lat = np.array([e.latitude if e.latitude is not None else np.nan for e in entities], dtype=float)
            lon = np.array([e.longitude if e.longitude is not None else np.nan for e in entities], dtype=float)
            with np.errstate(invalid="ignore"):
                d = haversine_km(comp.center_lat, comp.center_lon, lat, lon)
                z = np.where(d <= comp.radius_km, 1.0, np.exp(-(((d - comp.radius_km) / (0.5 * comp.radius_km)) ** 2)))
            w = np.where(np.isnan(d), 0.0, z)
        if comp.regions:
            regs = {r.strip().lower() for r in comp.regions}
            for i, e in enumerate(entities):
                if (e.region or "").lower() in regs or (e.country or "").lower() in regs:
                    w[i] = 1.0
        if comp.affected_entity_ids:
            ids = set(comp.affected_entity_ids)
            for i, e in enumerate(entities):
                if e.id in ids:
                    w[i] = 1.0
        return np.clip(w, 0.0, 1.0)

    def describe(self) -> dict:
        return {
            "name": self.name, "synthetic": True, "license": "n/a (generated)",
            "description": "Deterministic synthetic hazard footprint. Intensity is a dimensionless index, not a physical measurement.",
            "limitations": "No real hazard map, return period or probability is represented.",
        }


PROVIDERS: dict[str, HazardProvider] = {"synthetic_footprint": SyntheticFootprintProvider()}


@dataclass
class DirectExposureInputs:
    weights: np.ndarray       # (C,N) footprint weights
    intensity: np.ndarray     # (C,) base intensities
    k: np.ndarray             # (C,)
    dur_factor: np.ndarray    # (C,)
    vuln: np.ndarray          # (C,N) base vulnerability per component hazard
    exposure: np.ndarray      # (N,)
    amplification: float
    effective_duration_days: float


def build_direct_inputs(entities: list[Entity], spec: ScenarioSpec) -> DirectExposureInputs:
    provider = PROVIDERS[spec.data_source]
    comps = spec.hazards
    weights = np.vstack([provider.footprint_weights(entities, c) for c in comps])
    intensity = np.array([c.intensity for c in comps])
    k = np.array([HAZARD_PARAMS[c.hazard_type]["k"] for c in comps])
    dur = np.array([1 - math.exp(-c.duration_days / HAZARD_PARAMS[c.hazard_type]["tau"]) for c in comps])
    attr = {"flood": "flood_vulnerability", "heat": "heat_vulnerability", "drought": "drought_vulnerability"}
    vuln = np.vstack([[getattr(e, attr[c.hazard_type]) for e in entities] for c in comps])
    exposure = np.array([1.0 if e.exposed_asset_share is None else e.exposed_asset_share for e in entities])
    eff = max(c.duration_days + HAZARD_PARAMS[c.hazard_type]["recovery"] for c in comps)
    return DirectExposureInputs(weights, intensity, k, dur, vuln, exposure, spec.compound_amplification, eff)


def direct_disruption(inp: DirectExposureInputs, intensity: np.ndarray | None = None, vuln: np.ndarray | None = None,
                      exposure: np.ndarray | None = None) -> np.ndarray:
    """Vectorised over simulations. intensity: (S,C) or (C,), vuln: (S,C,N) or (C,N). Returns (S,N) disruption fractions."""
    I = inp.intensity if intensity is None else intensity
    V = inp.vuln if vuln is None else vuln
    E = inp.exposure if exposure is None else exposure
    I = np.atleast_2d(I)                        # (S,C)
    V = V if V.ndim == 3 else V[None]           # (S|1,C,N)
    H = np.clip(I[:, :, None] * inp.weights[None], 0, 1)    # (S,C,N)
    raw = H * np.atleast_2d(E)[:, None, :] * V
    sev = 1 - np.exp(-inp.k[None, :, None] * raw)
    f_c = sev * inp.dur_factor[None, :, None]
    f = 1 - np.prod(1 - f_c, axis=1)            # (S,N)
    if inp.amplification > 0 and f_c.shape[1] > 1:
        overlap = (f_c > 0.01).sum(axis=1) >= 2
        f = np.where(overlap, np.minimum(1.0, f * (1 + inp.amplification)), f)
    return np.clip(f, 0.0, 1.0)


def hazard_intensity_at_entities(inp: DirectExposureInputs) -> np.ndarray:
    return np.clip((inp.intensity[:, None] * inp.weights).max(axis=0), 0, 1)
