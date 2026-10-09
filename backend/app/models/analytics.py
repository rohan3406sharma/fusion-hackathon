"""Graph analytics and the (non-monetary) systemic vulnerability score.

Centrality is NOT climate risk. The score below is a transparent ranking aid: normalised components, configurable weights,
component contributions exposed. It is never converted into money.
"""
from __future__ import annotations

import math
from collections import defaultdict

import networkx as nx
import numpy as np

from ..schemas.domain import Entity, Relation

DEFAULT_WEIGHTS = {
    "direct_exposure": 0.25, "downstream_reach": 0.20, "weighted_dependency": 0.15,
    "lack_of_alternatives": 0.15, "inventory_fragility": 0.10, "operational_criticality": 0.15,
}
COMPONENT_DESCRIPTIONS = {
    "direct_exposure": "Direct disruption fraction under the active scenario (0 when no scenario is supplied).",
    "downstream_reach": "Share of total network value-added located downstream (transitively) of the entity.",
    "weighted_dependency": "Sum over outgoing edges of dependency x input specificity.",
    "lack_of_alternatives": "Flow-weighted (1-alt availability)(1-substitutability) of its customers: how hard it is to replace this entity.",
    "inventory_fragility": "Flow-weighted exp(-buffer/14d) over customers (buffer = customer inventory + lead time; 1 for non-storable).",
    "operational_criticality": "Entity-level criticality attribute (synthetic).",
}


def supply_graph(entities: list[Entity], relations: list[Relation]) -> nx.DiGraph:
    g = nx.DiGraph()
    for e in entities:
        g.add_node(e.id)
    for r in relations:
        if r.channel == "supply":
            g.add_edge(r.source, r.target, dep=r.dependency, spec=r.input_specificity, product=r.product, rid=r.id)
    return g


def _minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()) if x.size else 0.0, float(x.max()) if x.size else 0.0
    return np.zeros_like(x) if hi - lo < 1e-12 else (x - lo) / (hi - lo)


def graph_structure(entities: list[Entity], relations: list[Relation]) -> dict:
    g = supply_graph(entities, relations)
    wcc = sorted((len(c) for c in nx.weakly_connected_components(g)), reverse=True)
    scc = [sorted(c) for c in nx.strongly_connected_components(g) if len(c) > 1]
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for r in relations:
        if r.channel == "supply":
            groups[(r.target, r.product)].append(r)
    single = [
        {"target": t, "product": p, "supplier": rs[0].source, "dependency": rs[0].dependency}
        for (t, p), rs in groups.items() if len(rs) == 1 and rs[0].dependency >= 0.6
    ]
    single.sort(key=lambda x: -x["dependency"])
    return {
        "n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges(), "weak_component_sizes": wcc,
        "largest_component_share": (wcc[0] / g.number_of_nodes()) if wcc else 0.0,
        "cycles": scc, "single_source_dependencies": single,
        "is_dag": nx.is_directed_acyclic_graph(g) if g.number_of_nodes() else True,
    }


def systemic_scores(entities: list[Entity], relations: list[Relation], d0: np.ndarray | None = None,
                    weights: dict[str, float] | None = None) -> list[dict]:
    g = supply_graph(entities, relations)
    ids = [e.id for e in entities]
    idx = {i: k for k, i in enumerate(ids)}
    by_id = {e.id: e for e in entities}
    n = len(ids)
    rel_by_src: dict[str, list[Relation]] = defaultdict(list)
    for r in relations:
        if r.channel == "supply":
            rel_by_src[r.source].append(r)
    total_va = sum(e.value_added_musd for e in entities) or 1.0
    reach_n = np.zeros(n)
    reach_v = np.zeros(n)
    for i, nid in enumerate(ids):
        desc = nx.descendants(g, nid) if nid in g else set()
        reach_n[i] = len(desc)
        reach_v[i] = sum(by_id[d].value_added_musd for d in desc) / total_va
    wdep = np.zeros(n)
    irrepl = np.zeros(n)
    fragile = np.zeros(n)
    for i, nid in enumerate(ids):
        outs = rel_by_src.get(nid, [])
        if not outs:
            continue
        flows = np.array([max(r.annual_flow_musd, 1e-9) for r in outs])
        wdep[i] = sum(r.dependency * r.input_specificity for r in outs)
        irrepl[i] = float(np.average([(1 - by_id[r.target].alternative_supplier_availability) * (1 - r.substitutability) for r in outs], weights=flows))
        fragile[i] = float(np.average([1.0 if not r.storable else math.exp(-(by_id[r.target].inventory_days + r.lead_time_days) / 14.0) for r in outs], weights=flows))
    crit = np.array([e.operational_criticality for e in entities])
    dist_g = nx.DiGraph()
    dist_g.add_nodes_from(ids)
    for u, v, a in g.edges(data=True):
        dist_g.add_edge(u, v, dist=-math.log(max(a["dep"] * a["spec"], 1e-6)), dep=a["dep"])
    btw = nx.betweenness_centrality(dist_g, weight="dist", normalized=True)
    pr = nx.pagerank(dist_g.reverse(copy=True), weight="dep") if dist_g.number_of_edges() else {i: 1 / max(n, 1) for i in ids}
    comps = {
        "direct_exposure": _minmax(np.zeros(n) if d0 is None else np.asarray(d0, float)),
        "downstream_reach": _minmax(reach_v), "weighted_dependency": _minmax(wdep),
        "lack_of_alternatives": _minmax(irrepl), "inventory_fragility": _minmax(fragile),
        "operational_criticality": _minmax(crit),
    }
    w = dict(DEFAULT_WEIGHTS if weights is None else weights)
    if d0 is None or float(np.max(d0)) <= 0:
        w["direct_exposure"] = 0.0
    wsum = sum(w.values()) or 1.0
    rows = []
    for i, nid in enumerate(ids):
        contrib = {k: 100.0 * w.get(k, 0.0) / wsum * float(comps[k][i]) for k in comps}
        rows.append({
            "entity_id": nid, "name": by_id[nid].name, "entity_type": by_id[nid].entity_type, "food_category": by_id[nid].food_category,
            "score": round(sum(contrib.values()), 2), "components": {k: round(float(v[i]), 4) for k, v in comps.items()},
            "contributions": {k: round(v, 2) for k, v in contrib.items()}, "in_degree": int(g.in_degree(nid)), "out_degree": int(g.out_degree(nid)),
            "weighted_out_dependency": round(float(wdep[i]), 3), "betweenness": round(float(btw[nid]), 4),
            "pagerank_dependedness": round(float(pr[nid]), 5), "downstream_reach": int(reach_n[i]),
        })
    rows.sort(key=lambda r: -r["score"])
    for k, r in enumerate(rows, 1):
        r["rank"] = k
    return rows


def dominant_paths(net, trans: np.ndarray, d0: np.ndarray, names: dict[str, str], losses: dict[str, float],
                   top: int = 10, thr: float = 0.01) -> list[dict]:
    """For each affected entity, the single path from a directly hit entity that carries the largest transmitted fraction
    (max-product path = Dijkstra on -log). A diagnostic of the dominant channel, not a decomposition of total loss."""
    if top <= 0 or net.m == 0:
        return []
    g = nx.DiGraph()
    g.add_node("__origin__")
    for k in range(net.m):
        if trans[k] > 1e-9:
            g.add_edge(net.node_ids[net.src[k]], net.node_ids[net.tgt[k]], w=-math.log(trans[k]), k=k)
    for i, nid in enumerate(net.node_ids):
        if d0[i] > thr:
            g.add_edge("__origin__", nid, w=-math.log(min(d0[i], 1 - 1e-12)), k=-1)
    dist, paths = nx.single_source_dijkstra(g, "__origin__", weight="w")
    cands = []
    for nid, p in paths.items():
        if nid == "__origin__" or len(p) < 3:  # needs origin + >=2 real nodes
            continue
        cands.append((losses.get(nid, 0.0), nid, p[1:], math.exp(-dist[nid])))
    cands.sort(key=lambda c: -c[0])
    out = []
    for loss, nid, p, cum in cands[:top]:
        hops = []
        for a, b in zip(p[:-1], p[1:]):
            k = g[a][b]["k"]
            hops.append({"source": a, "target": b, "product": net.relations[k].product, "transmission": round(float(trans[k]), 4)})
        out.append({"origin_id": p[0], "terminal_id": nid, "entity_ids": p, "names": [names[x] for x in p], "hops": hops,
                    "cumulative_transmission": round(cum, 5), "terminal_total_loss_musd": round(loss, 3)})
    return out


def neighbours(entities: list[Entity], relations: list[Relation], entity_id: str, depth: int = 3) -> dict:
    g = supply_graph(entities, relations)
    if entity_id not in g:
        raise KeyError(entity_id)
    up = nx.single_source_shortest_path_length(g.reverse(copy=False), entity_id, cutoff=depth)
    down = nx.single_source_shortest_path_length(g, entity_id, cutoff=depth)
    up.pop(entity_id, None)
    down.pop(entity_id, None)
    return {"upstream_hops": up, "downstream_hops": down}
