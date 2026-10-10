"""Dotted world map + the project's synthetic network, in one projected coordinate space.

Inputs : assets/data/vendor/land-110m.json (Natural Earth via world-atlas@2.0.2, public domain / ISC)
         ../backend/data/fnb_entities.json, fnb_relations.json, portfolio.json (the app's SYNTHETIC dataset)
Outputs: assets/data/geo.js  -> window.GEO = {w, h, dotPath, landPath, nodes, edges, holdings}
Projection: Equal Earth, fitted to a 1920x1080 frame (Antarctica cropped).
Run: .venv-tts/bin/python scripts/build_geo.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT.parent / "backend" / "data"
W, H = 1920, 1080
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = np.sqrt(3) / 2


def equal_earth(lon, lat):
    lam, phi = np.radians(lon), np.radians(lat)
    th = np.arcsin(M * np.sin(phi))
    th2 = th * th
    th6 = th2 ** 3
    x = lam * np.cos(th) / (M * (A1 + 3 * A2 * th2 + th6 * (7 * A3 + 9 * A4 * th2)))
    y = th * (A1 + A2 * th2 + th6 * (A3 + A4 * th2))
    return x, y


def decode_topojson(topo: dict) -> list[list[np.ndarray]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        a = np.cumsum(np.array(arc, dtype=float), axis=0)
        arcs.append(np.column_stack([a[:, 0] * sx + tx, a[:, 1] * sy + ty]))

    def ring(idx: list[int]) -> np.ndarray:
        pts = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.append(a if not pts else a[1:])
        return np.vstack(pts)

    polys = []
    for geom in topo["objects"]["land"]["geometries"]:
        groups = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
        for poly in groups:
            polys.append([ring(r) for r in poly])
    return polys


def main() -> None:
    topo = json.loads((ROOT / "assets" / "data" / "vendor" / "land-110m.json").read_text())
    polys = decode_topojson(topo)

    # fit: x range of the full globe, y from 84N down to 56S
    gx, _ = equal_earth(np.array([-180.0, 180.0]), np.array([0.0, 0.0]))
    _, gy = equal_earth(np.array([0.0, 0.0]), np.array([84.0, -56.0]))
    scale = min((W - 80) / (gx[1] - gx[0]), (H - 70) / (gy[0] - gy[1]))
    ox, oy = W / 2, H / 2 + scale * (gy[0] + gy[1]) / 2

    def proj(lon, lat):
        x, y = equal_earth(np.asarray(lon, float), np.asarray(lat, float))
        return ox + scale * x, oy - scale * y

    rings = []
    for poly in polys:
        for r in poly:
            if r[:, 1].max() < -58:
                continue  # Antarctica
            x, y = proj(r[:, 0], r[:, 1])
            rings.append(np.column_stack([x, y]))

    # dot grid (offset rows for a hex feel), keep points inside land (even-odd rule)
    step = 9.0
    pts = []
    for row, y in enumerate(np.arange(16, H - 10, step * 0.866)):
        off = step / 2 if row % 2 else 0.0
        for x in np.arange(10 + off, W - 10, step):
            pts.append((x, y))
    pts = np.array(pts)
    inside = np.zeros(len(pts), dtype=bool)
    px, py = pts[:, 0], pts[:, 1]
    for r in rings:
        xs, ys = r[:, 0], r[:, 1]
        x1, y1 = xs[:-1], ys[:-1]
        x2, y2 = xs[1:], ys[1:]
        # crossing test vectorised over points (rows) x edges (cols)
        cond = (y1[None, :] > py[:, None]) != (y2[None, :] > py[:, None])
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = x1[None, :] + (py[:, None] - y1[None, :]) * (x2 - x1)[None, :] / (y2 - y1)[None, :]
        inside ^= (np.sum(cond & (px[:, None] < xint), axis=1) % 2).astype(bool)
    dots = pts[inside]
    r = 2.1
    dot_path = "".join(f"M{x - r:.1f} {y:.1f}a{r} {r} 0 1 0 {2 * r} 0a{r} {r} 0 1 0 {-2 * r} 0" for x, y in dots)
    land_path = "".join("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in ring_) + "Z" for ring_ in rings)

    ents = json.loads((DATA / "fnb_entities.json").read_text())
    ents = ents["entities"] if isinstance(ents, dict) else ents
    rels = json.loads((DATA / "fnb_relations.json").read_text())
    rels = rels["relations"] if isinstance(rels, dict) else rels
    port = json.loads((DATA / "portfolio.json").read_text())
    holdings = [h["entity_id"] for h in port["holdings"]]
    nodes = {}
    for e in ents:
        if e.get("latitude") is None or e.get("longitude") is None:
            continue
        x, y = proj(e["longitude"], e["latitude"])
        nodes[e["id"]] = {"x": round(float(x), 1), "y": round(float(y), 1), "name": e["name"], "type": e["entity_type"],
                          "country": e.get("country"), "holding": e["id"] in holdings}
    edges = [[r_["source"], r_["target"], round(r_.get("dependency", 0), 3)] for r_ in rels
             if r_.get("channel") == "supply" and r_["source"] in nodes and r_["target"] in nodes]
    geo = {"w": W, "h": H, "dotPath": dot_path, "landPath": land_path, "nodes": nodes, "edges": edges, "holdings": holdings,
           "credit": "Land: Natural Earth (public domain) via world-atlas 2.0.2. Nodes: the app's SYNTHETIC entities at synthetic coordinates."}
    (ROOT / "assets" / "data" / "geo.js").write_text("// Generated by scripts/build_geo.py\nwindow.GEO = " + json.dumps(geo) + ";\n")
    print(f"dots {len(dots)}  rings {len(rings)}  nodes {len(nodes)}  edges {len(edges)}  holdings {len(holdings)}  "
          f"geo.js {len(json.dumps(geo)) / 1e6:.2f} MB")
    for k in ["grid_nl", "dairy_pack_nl", "retail_eu", "readymeal_uk", "port_rtm"]:
        print(" ", k, nodes.get(k))


if __name__ == "__main__":
    main()
