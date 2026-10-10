"""Weighted supply-chain graph compilation and multi-hop shock propagation.

Edge direction: supplier -> customer. A shock flows along edge direction only.

Per-edge transmission (all factors in [0,1], documented in docs/METHODOLOGY.md):
    tau_e(d) = dep_e * spec_e * (1 - sub_e) * inv_e * damp_e * (1 - a_mkt_e) * (1 - a_graph_e(d))
      dep_e    share of customer v's input *of that product* provided by supplier u
      spec_e   input specificity / criticality (Barrot & Sauvagnat: only specific inputs transmit)
      sub_e    input substitutability (a different input could replace it)
      inv_e    inventory adjustment = clip((T - (I_v + L_e)) / T, 0, 1) for storable goods, else 1
      damp_e   feedback damping for links inside a cycle (strongly connected component), else 1
      a_mkt_e  relief from suppliers OUTSIDE the modelled graph: entity assumption alt_v applied to the
               unmodelled share of that input (1 - sum of modelled dependency shares)
      a_graph_e(d)  relief from modelled same-product producers, from their spare capacity, reduced by their own
               disruption: min(0.95, sum_w spare_w (1 - d_w) / (n_w * flow_e)); n_w = number of links producer w could
               serve (its spare capacity is shared, not counted once per customer). Non-storable goods/services
               only from the customer's own country.
Update rule (bounded state d in [0,1], no double counting):
    g_{v,p}   = min(1, sum_{e into v with product p} d_u * tau_e(d))         (additive within one input)
    d_in_v    = 1 - prod_p (1 - g_{v,p})                                      (noisy-OR across different inputs)
    d_v(t+1)  = 1 - (1 - d0_v)(1 - d_in_v(d(t)))
tau_e(d) rises as alternatives are disrupted, so the map stays monotone and bounded; iteration from d0 converges to
the least fixed point or stops at the depth cap. Iteration t reproduces propagation through t hops.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from ..schemas.domain import Entity, Relation

CAP = 0.95        # an individual relief mechanism can remove at most 95% of a shock
EPS = 1e-9


@dataclass
class Network:
    node_ids: list[str]
    idx: dict[str, int]
    edge_ids: list[str]
    src: np.ndarray
    tgt: np.ndarray
    n_groups: int
    meg: np.ndarray          # (E,G)
    mgn: np.ndarray          # (G,N)
    dep: np.ndarray
    spec: np.ndarray
    sub: np.ndarray
    lead: np.ndarray
    storable: np.ndarray
    inv: np.ndarray          # (N,)
    alt: np.ndarray          # (N,) entity assumption about suppliers outside the graph
    va: np.ndarray           # (N,)
    relations: list[Relation]
    group_dep: np.ndarray    # (E,) modelled share of the edge's (customer, product) input
    alt_matrix: np.ndarray   # (E,N) spare capacity of eligible alternative producer w, per unit of edge flow
    cycle_edge: np.ndarray   # (E,) bool: link sits inside a feedback loop

    @property
    def n(self) -> int:
        return len(self.node_ids)

    @property
    def m(self) -> int:
        return len(self.edge_ids)


def _alternatives(entities: list[Entity], rels: list[Relation], idx: dict[str, int]) -> np.ndarray:
    by = {e.id: e for e in entities}
    elig: list[list[int]] = []
    for r in rels:
        tgt = by[r.target]
        ws = [i for i, w in enumerate(entities)
              if w.output_product == r.product and w.id not in (r.source, r.target) and w.entity_type != "financial"
              and w.spare_capacity_fraction > 0 and (r.storable or w.country == tgt.country)]
        elig.append(ws)
    n_links = np.zeros(len(entities))
    for ws in elig:
        for w in ws:
            n_links[w] += 1
    A = np.zeros((len(rels), len(entities)))
    for k, (r, ws) in enumerate(zip(rels, elig)):
        flow = max(r.annual_flow_musd, EPS)
        for w in ws:
            e = entities[w]
            A[k, w] = e.revenue_musd * e.spare_capacity_fraction / max(n_links[w], 1) / flow
    return A


def compile_network(entities: list[Entity], relations: list[Relation]) -> Network:
    ids = [e.id for e in entities]
    idx = {i: k for k, i in enumerate(ids)}
    rels = [r for r in relations if r.channel == "supply"]
    src = np.array([idx[r.source] for r in rels], dtype=int)
    tgt = np.array([idx[r.target] for r in rels], dtype=int)
    gmap: dict[tuple[int, str], int] = {}
    gofe = []
    for r, t in zip(rels, tgt):
        gofe.append(gmap.setdefault((int(t), r.product), len(gmap)))
    G = len(gmap)
    meg = np.zeros((len(rels), G))
    for k, g in enumerate(gofe):
        meg[k, g] = 1.0
    mgn = np.zeros((G, len(ids)))
    for (t, _), g in gmap.items():
        mgn[g, t] = 1.0
    arr = lambda f: np.array([f(r) for r in rels], dtype=float)  # noqa: E731
    dep = arr(lambda r: r.dependency)
    group_dep = (dep @ meg) @ meg.T if len(rels) else dep
    g = nx.DiGraph()
    g.add_nodes_from(ids)
    g.add_edges_from((r.source, r.target) for r in rels)
    comp = {}
    for c_i, c in enumerate(nx.strongly_connected_components(g)):
        for node in c:
            comp[node] = (c_i, len(c))
    cyc = np.array([comp[r.source][0] == comp[r.target][0] and comp[r.source][1] > 1 for r in rels], dtype=bool)
    return Network(
        node_ids=ids, idx=idx, edge_ids=[r.id for r in rels], src=src, tgt=tgt, n_groups=G, meg=meg, mgn=mgn,
        dep=dep, spec=arr(lambda r: r.input_specificity), sub=arr(lambda r: r.substitutability),
        lead=arr(lambda r: r.lead_time_days), storable=np.array([r.storable for r in rels], dtype=bool),
        inv=np.array([e.inventory_days for e in entities], dtype=float),
        alt=np.array([e.alternative_supplier_availability for e in entities], dtype=float),
        va=np.array([e.value_added_musd for e in entities], dtype=float), relations=rels,
        group_dep=np.clip(group_dep, 0, 1), alt_matrix=_alternatives(entities, rels, idx) if rels else np.zeros((0, len(ids))),
        cycle_edge=cyc)


def transmission(net: Network, T, dep: np.ndarray | None = None, sub: np.ndarray | None = None,
                 alt: np.ndarray | None = None, inv: np.ndarray | None = None, spec: np.ndarray | None = None,
                 inventory_scale: float = 1.0, substitution_scale: float = 1.0, dependency_scale: float = 1.0,
                 use_graph_alternatives: bool = True, cycle_damping: float = 1.0) -> np.ndarray:
    """State-independent part of tau_e, shape (S,E). T may be a scalar or one duration per simulation row (S,).
    With use_graph_alternatives=False the entity assumption alt_v applies to the whole input (pre-v0.2 behaviour)."""
    dep = np.atleast_2d(net.dep if dep is None else dep)
    sub = np.atleast_2d(net.sub if sub is None else sub)
    spec = np.atleast_2d(net.spec if spec is None else spec)
    alt = np.atleast_2d(net.alt if alt is None else alt)
    inv = np.atleast_2d(net.inv if inv is None else inv)
    T = np.atleast_1d(np.asarray(T, dtype=float)).reshape(-1, 1)
    rows = max(dep.shape[0], sub.shape[0], alt.shape[0], inv.shape[0], T.shape[0])
    if net.m == 0:
        return np.zeros((rows, 0))
    dep = np.clip(dep * dependency_scale, 0, 1)
    sub_e = np.clip(sub * substitution_scale, 0, CAP)
    unmodelled = (1 - net.group_dep)[None, :] if use_graph_alternatives else 1.0
    alt_e = np.clip(alt[:, net.tgt] * substitution_scale * unmodelled, 0, CAP)
    buf = inv[:, net.tgt] * inventory_scale + net.lead[None, :]
    inv_adj = np.where(net.storable[None, :], np.clip((T - buf) / np.maximum(T, EPS), 0, 1), 1.0)
    damp = np.where(net.cycle_edge, cycle_damping, 1.0)[None, :]
    return np.broadcast_to(dep * spec * (1 - alt_e) * (1 - sub_e) * inv_adj * damp, (rows, net.m)).copy()


def graph_relief(net: Network, d: np.ndarray, scale) -> np.ndarray:
    """(S,E) relief from modelled alternative producers given current disruption state d (S,N)."""
    return np.clip(((1 - d) @ net.alt_matrix.T) * np.asarray(scale).reshape(-1, 1), 0, CAP)


def propagate(net: Network, d0: np.ndarray, trans: np.ndarray, max_depth: int = 6, tol: float = 1e-6,
              graph_alt_scale=None):
    """Returns (history, converged, effective_transmission). history[t] has shape (S,N); history[0] = d0.
    graph_alt_scale=None disables state-dependent relief from modelled alternatives."""
    d0 = np.atleast_2d(d0)
    hist = [d0]
    d = d0
    converged = net.m == 0
    use_graph = graph_alt_scale is not None and net.m > 0 and net.alt_matrix.any()
    eff = trans * (1 - graph_relief(net, d, graph_alt_scale)) if use_graph else trans
    for _ in range(max_depth):
        if net.m == 0:
            break
        eff = trans * (1 - graph_relief(net, d, graph_alt_scale)) if use_graph else trans
        p = d[:, net.src] * eff
        g = np.minimum(p @ net.meg, 1 - EPS)
        d_in = 1 - np.exp(np.log1p(-g) @ net.mgn)
        d_new = 1 - (1 - d0) * (1 - d_in)
        delta = float(np.max(np.abs(d_new - d))) if d_new.size else 0.0
        hist.append(d_new)
        d = d_new
        if delta < tol:
            converged = True
            break
    if use_graph:
        eff = trans * (1 - graph_relief(net, d, graph_alt_scale))
    return hist, converged, eff


def simulate(net: Network, d0: np.ndarray, T, *, inventory_scale: float = 1.0, substitution_scale: float = 1.0,
             dependency_scale: float = 1.0, use_graph_alternatives: bool = True, cycle_damping: float = 1.0,
             max_depth: int = 6, tol: float = 1e-6, dep=None, sub=None, alt=None, inv=None, graph_scale=1.0):
    """One call used by the deterministic run, Monte Carlo and the reverse stress test (rows = runs)."""
    trans = transmission(net, T, dep=dep, sub=sub, alt=alt, inv=inv, inventory_scale=inventory_scale,
                         substitution_scale=substitution_scale, dependency_scale=dependency_scale,
                         use_graph_alternatives=use_graph_alternatives, cycle_damping=cycle_damping)
    gscale = (np.asarray(graph_scale, dtype=float) * substitution_scale) if use_graph_alternatives else None
    return propagate(net, d0, trans, max_depth=max_depth, tol=tol, graph_alt_scale=gscale)
