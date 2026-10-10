"""Event library for the portfolio reverse stress test (Hidden Exposure Finder).

Events are generated, not hand-picked: every non-financial entity as a single-node shock, plus circular footprints centred
on every located entity and every region centroid, for each hazard and radius. Footprints that reach no sufficiently
vulnerable entity are dropped as implausible, and footprints that hit the same entities with the same weights are
de-duplicated. All events are SYNTHETIC: reference intensity and durations are analyst choices, not hazard statistics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..schemas.domain import Entity
from ..schemas.scenario import HazardComponent
from .climate import HAZARD_PARAMS, SyntheticFootprintProvider

REF_DURATION = {"flood": 21.0, "heat": 14.0, "drought": 120.0}
VULN_ATTR = {"flood": "flood_vulnerability", "heat": "heat_vulnerability", "drought": "drought_vulnerability"}


@dataclass
class Event:
    id: str
    kind: str                      # "node" | "footprint"
    hazard: str
    label: str
    origin_id: str | None
    country: str | None
    region: str | None
    center_lat: float | None
    center_lon: float | None
    radius_km: float | None
    intensity: float
    duration_days: float
    weights: np.ndarray = field(repr=False)   # (N,) footprint weight per entity

    @property
    def T(self) -> float:
        return self.duration_days + HAZARD_PARAMS[self.hazard]["recovery"]

    def hazard_component(self) -> dict:
        base = dict(hazard_type=self.hazard, intensity=self.intensity, duration_days=self.duration_days, label=self.label)
        if self.kind == "node":
            return {**base, "affected_entity_ids": [self.origin_id], "regions": []}
        return {**base, "center_lat": self.center_lat, "center_lon": self.center_lon, "radius_km": self.radius_km,
                "regions": [], "affected_entity_ids": []}


def build_library(entities: list[Entity], hazards=("flood", "heat", "drought"), intensity: float = 0.8,
                  radii=(150.0, 350.0), min_vulnerability: float = 0.3, include_regions: bool = True) -> list[Event]:
    prov = SyntheticFootprintProvider()
    n = len(entities)
    events: list[Event] = []
    seen: set = set()
    phys = [e for e in entities if e.entity_type != "financial"]
    for h in hazards:
        vul = np.array([getattr(e, VULN_ATTR[h]) for e in entities])
        for i, e in enumerate(entities):
            if e.entity_type == "financial" or vul[i] < min_vulnerability:
                continue
            w = np.zeros(n)
            w[i] = 1.0
            events.append(Event(f"node:{e.id}:{h}", "node", h, f"{h.title()} at {e.name}", e.id, e.country, e.region,
                                e.latitude, e.longitude, None, intensity, REF_DURATION[h], w))
        centres = [(f"ent:{e.id}", e.name, e.id, e.country, e.region, e.latitude, e.longitude) for e in phys if e.latitude is not None]
        if include_regions:
            groups: dict[tuple, list[Entity]] = {}
            for e in phys:
                if e.latitude is not None:
                    groups.setdefault((e.country, e.region), []).append(e)
            for (c, r), es in sorted(groups.items(), key=lambda kv: str(kv[0])):
                centres.append((f"reg:{c}:{r}", f"{r}, {c}", None, c, r, float(np.mean([x.latitude for x in es])),
                                float(np.mean([x.longitude for x in es]))))
        for key, name, origin, country, region, lat, lon in centres:
            for rad in radii:
                comp = HazardComponent(hazard_type=h, intensity=intensity, duration_days=REF_DURATION[h],
                                       center_lat=lat, center_lon=lon, radius_km=rad)
                w = prov.footprint_weights(entities, comp)
                if not np.any((w >= 0.5) & (vul >= min_vulnerability)):
                    continue                                   # reaches nothing vulnerable: implausible as a loss event
                sig = (h, tuple(np.round(w, 2)))
                if sig in seen:
                    continue
                seen.add(sig)
                events.append(Event(f"fp:{key}:{int(rad)}:{h}", "footprint", h,
                                    f"{h.title()}, {int(rad)} km around {name}", origin, country, region, lat, lon, rad,
                                    intensity, REF_DURATION[h], w))
    return events
