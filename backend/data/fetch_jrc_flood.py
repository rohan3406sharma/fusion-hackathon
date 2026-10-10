"""Offline step: sample the JRC / Copernicus CEMS global river flood hazard map (100-year return period) around each
entity's approximate coordinate and write data/hazard_layers/jrc_flood_rp100.json for the app to read.

What the layer means: the share of ~90 m cells within RADIUS_KM of the entity's SYNTHETIC approximate location that
the model floods in a 1-in-100-year river flood (and the share deeper than 1 m). It is hazard context at a coordinate,
not the exposure of a real facility. River flooding only: coastal and surface-water flooding are not represented, so
a zero is not evidence that a site is safe.

Source: Baugh, C., Colonese, J., D'Angelo, C., Dottori, F., Neal, J., Prudhomme, C., Salamon, P. (2024). Modelled flood
inundation for different return period scenarios at the global scale. European Commission, Joint Research Centre.
Dataset v2.1.2. (c) European Union, 1995-2026, CC BY 4.0. https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/
Changes made: windowed sampling and aggregation to shares per coordinate.

Run once (needs network and requirements-data.txt):  ../.venv/bin/python data/fetch_jrc_flood.py
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
OUT = HERE / "hazard_layers" / "jrc_flood_rp100.json"
CACHE = HERE / "hazard_layers" / "cache"
BASE = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/"
RP = 100
RADIUS_KM = 5.0


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print("downloading", url, file=sys.stderr)
        with urllib.request.urlopen(url, timeout=180) as r, open(dest, "wb") as f:
            f.write(r.read())
    return dest


def tile_for(lat: float, lon: float, tiles: list[dict]) -> dict | None:
    for t in tiles:
        xs = [p[0] for p in t["geometry"]["coordinates"][0]]
        ys = [p[1] for p in t["geometry"]["coordinates"][0]]
        if min(xs) <= lon < max(xs) and min(ys) <= lat < max(ys):
            return t
    return None


def read_tile(path: Path):
    import tifffile
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        scale = page.tags["ModelPixelScaleTag"].value          # (dx, dy, dz)
        tie = page.tags["ModelTiepointTag"].value              # (i, j, k, x, y, z)
        arr = page.asarray()
    return arr, float(tie[3]), float(tie[4]), float(scale[0]), float(scale[1])


def sample(arr, x0, y0, dx, dy, lat, lon):
    col, row = (lon - x0) / dx, (y0 - lat) / dy
    rl = RADIUS_KM / 111.32 / dy
    rc = RADIUS_KM / (111.32 * math.cos(math.radians(lat))) / dx
    r0, r1 = int(max(0, row - rl)), int(min(arr.shape[0], row + rl + 1))
    c0, c1 = int(max(0, col - rc)), int(min(arr.shape[1], col + rc + 1))
    win = arr[r0:r1, c0:c1]
    rr, cc = np.mgrid[r0:r1, c0:c1]
    mask = ((rr - row) / rl) ** 2 + ((cc - col) / rc) ** 2 <= 1.0
    vals = win[mask]                      # classes 1-4 = flooded depth bands; 255 = not flooded / no data (incl. sea)
    n = int(vals.size)
    full = math.pi * RADIUS_KM ** 2 / (dy * 111.32 * dx * 111.32 * math.cos(math.radians(lat)))   # cells in a complete circle
    flooded = (vals >= 1) & (vals <= 4)
    deep = (vals >= 2) & (vals <= 4)
    return dict(cells=n, window_coverage=round(min(1.0, n / full), 3), flooded_share=round(float(flooded.mean()) if n else 0.0, 4),
                deep_share=round(float(deep.mean()) if n else 0.0, 4))


def main() -> None:
    ents = json.loads((HERE / "fnb_entities.json").read_text())
    tiles = json.loads(fetch(BASE + "tile_extents.geojson", CACHE / "tile_extents.geojson").read_text())["features"]
    by_tile: dict[str, list[dict]] = {}
    for e in ents:
        if e["latitude"] is None:
            continue
        t = tile_for(e["latitude"], e["longitude"], tiles)
        if t is not None:
            by_tile.setdefault(f"ID{t['properties']['id']}_{t['properties']['name']}", []).append(e)
    out = {}
    for name, es in sorted(by_tile.items()):
        fn = f"{name}_RP{RP}_depth_reclass.tif"
        path = fetch(f"{BASE}RP{RP}/{fn}", CACHE / fn)
        arr, x0, y0, dx, dy = read_tile(path)
        for e in es:
            out[e["id"]] = {**sample(arr, x0, y0, dx, dy, e["latitude"], e["longitude"]), "tile": fn}
        del arr
    missing = [e["id"] for e in ents if e["latitude"] is not None and e["id"] not in out]
    OUT.write_text(json.dumps({
        "layer": f"JRC/CEMS global river flood hazard, {RP}-year return period, sampled within {RADIUS_KM:g} km",
        "source": BASE, "dataset_version": "2.1.2",
        "citation": "Baugh, C., Colonese, J., D'Angelo, C., Dottori, F., Neal, J., Prudhomme, C., Salamon, P. (2024). Modelled flood "
                    "inundation for different return period scenarios at the global scale. European Commission, Joint Research Centre.",
        "licence": "CC BY 4.0, (c) European Union 1995-2026; changes: windowed sampling and aggregation to shares per coordinate",
        "retrieved": date.today().isoformat(), "radius_km": RADIUS_KM, "return_period_years": RP,
        "meaning": "Share of the ~90 m cells within the radius that the model floods (class >= 1), and floods deeper than 1 m (class >= 2), in a "
                   "1-in-100-year river flood, around each entity's SYNTHETIC approximate coordinate. The denominator is ALL cells in the window, "
                   "including sea, permanent water and dry land (the raster marks them all 255), so coastal shares are diluted. River flooding only. "
                   "Windows at tile edges are truncated, not stitched from neighbouring tiles: see window_coverage.",
        "entities": out, "not_covered": missing}, indent=1))
    print(f"wrote {OUT} for {len(out)} entities from {len(by_tile)} tiles; not covered: {missing}")


if __name__ == "__main__":
    main()
