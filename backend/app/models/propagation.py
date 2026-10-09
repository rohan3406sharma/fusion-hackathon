"""Weighted supply-chain graph compilation and multi-hop shock propagation.

Edge direction: supplier -> customer. A shock flows along edge direction only.

Per-edge transmission (all factors in [0,1], documented in docs/METHODOLOGY.md):
    tau_e = dep_e * spec_e * (1 - alt_v) * (1 - sub_e) * inv_e
      dep_e   share of customer v's input *of that product* provided by supplier u
      spec_e  input specificity / criticality of the input to v's product (Barrot & Sauvagnat: only specific inputs transmit)
      alt_v   alternative-supplier availability of v   |  sub_e  input substitutability (different mechanisms -> multiplied)
      inv_e   inventory adjustment = clip((T - (I_v + L_e)) / T, 0, 1)   for storable goods, else 1
              T = effective disruption duration (event + recovery), I_v = v's input inventory days, L_e = edge lead time (pipeline stock)
Update rule (bounded state d in [0,1], no double counting):
    g_{v,p}   = min(1, sum_{e into v with product p} d_u * tau_e)            (additive within one input)
    d_in_v    = 1 - prod_p (1 - g_{v,p})                                      (noisy-OR across different inputs)
    d_v(t+1)  = 1 - (1 - d0_v)(1 - d_in_v(d(t)))                              (direct + input shortfall combine, never > 1)
Iteration t reproduces propagation through t hops. The map is monotone and bounded, so cycles converge to a fixed point.
"""
from __future__ import annotations

from dataclasses import dataclass

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
    alt: np.ndarray          # (N,)
    va: np.ndarray           # (N,)
    relations: list[Relation]

    @property
    def n(self) -> int:
        return len(self.node_ids)

    @property
    def m(self) -> int:
        return len(self.edge_ids)


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
    return Network(
        node_ids=ids, idx=idx, edge_ids=[r.id for r in rels], src=src, tgt=tgt, n_groups=G, meg=meg, mgn=mgn,
        dep=arr(lambda r: r.dependency), spec=arr(lambda r: r.input_specificity), sub=arr(lambda r: r.substitutability),
        lead=arr(lambda r: r.lead_time_days), storable=np.array([r.storable for r in rels], dtype=bool),
        inv=np.array([e.inventory_days for e in entities]), alt=np.array([e.alternative_supplier_availability for e in entities]),
        va=np.array([e.value_added_musd for e in entities]), relations=rels)


def transmission(net: Network, T: float, dep: np.ndarray | None = None, sub: np.ndarray | None = None,
                 alt: np.ndarray | None = None, inv: np.ndarray | None = None, spec: np.ndarray | None = None,
                 inventory_scale: float = 1.0, substitution_scale: float = 1.0, dependency_scale: float = 1.0) -> np.ndarray:
    """Per-edge transmission factors tau_e, shape (S,E). Inputs may carry a leading simulation axis."""
    dep = np.atleast_2d(net.dep if dep is None else dep)
    sub = np.atleast_2d(net.sub if sub is None else sub)
    spec = np.atleast_2d(net.spec if spec is None else spec)
    alt = np.atleast_2d(net.alt if alt is None else alt)
    inv = np.atleast_2d(net.inv if inv is None else inv)
    if net.m == 0:
        return np.zeros((max(dep.shape[0], 1), 0))
    dep = np.clip(dep * dependency_scale, 0, 1)
    sub_e = np.clip(sub * substitution_scale, 0, CAP)
    alt_e = np.clip(alt[:, net.tgt] * substitution_scale, 0, CAP)
    buf = inv[:, net.tgt] * inventory_scale + net.lead[None, :]
    inv_adj = np.where(net.storable[None, :], np.clip((T - buf) / max(T, EPS), 0, 1), 1.0)
    return dep * spec * (1 - alt_e) * (1 - sub_e) * inv_adj


def propagate(net: Network, d0: np.ndarray, trans: np.ndarray, max_depth: int = 6, tol: float = 1e-6):
    """Returns (history, converged). history[t] has shape (S,N); history[0] = d0 (direct). Stops at tolerance or max_depth."""
    d0 = np.atleast_2d(d0)
    hist = [d0]
    d = d0
    converged = net.m == 0
    for _ in range(max_depth):
        if net.m == 0:
            break
        p = d[:, net.src] * trans
        g = np.minimum(p @ net.meg, 1 - EPS)
        d_in = 1 - np.exp(np.log1p(-g) @ net.mgn)
        d_new = 1 - (1 - d0) * (1 - d_in)
        delta = float(np.max(np.abs(d_new - d))) if d_new.size else 0.0
        hist.append(d_new)
        d = d_new
        if delta < tol:
            converged = True
            break
    return hist, converged
