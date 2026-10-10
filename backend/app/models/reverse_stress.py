"""Portfolio reverse stress test: evaluate an event library through the unchanged propagation engine in one batch.

For event e with effective window T(e) and portfolio weights w_h:
    P_net(e) = sum_h w_h d*_h(e) T(e)/365        P_loc(e) = sum_h w_h d0_h(e) T(e)/365        H(e) = 1 - P_loc/P_net
P is the position-weighted share of the holdings' annual value added lost. H is the share a location-only screen
(direct damage at the holdings' own sites) would not see. Rankings, not magnitudes, are the defensible output.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from scipy.stats import kendalltau

from ..schemas.domain import Entity
from .climate import HAZARD_PARAMS
from .events import VULN_ATTR, Event
from .montecarlo import sample
from .propagation import Network, simulate

TOP = 5
OUTAGE_T = 60.0          # standard window for structural single-node / pair outages (days)
SPOF_THRESHOLD = 0.2     # a node is a single point of failure for a holding if its outage alone disrupts it >= 20%


@dataclass
class Params:
    max_depth: int = 6
    inventory_scale: float = 1.0
    substitution_scale: float = 1.0
    dependency_scale: float = 1.0
    use_graph_alternatives: bool = True
    cycle_damping: float = 0.5


def direct_matrix(entities: list[Entity], events: list[Event], intensity_mult: float = 1.0, k_mult: float = 1.0,
                  vuln_mult: np.ndarray | None = None) -> np.ndarray:
    """(S,N) direct disruption for single-hazard events; same proxy function as models/climate.py."""
    expo = np.array([1.0 if e.exposed_asset_share is None else e.exposed_asset_share for e in entities])
    vm = np.ones(len(entities)) if vuln_mult is None else np.asarray(vuln_mult).reshape(-1)
    out = np.zeros((len(events), len(entities)))
    for h in {ev.hazard for ev in events}:
        rows = [i for i, ev in enumerate(events) if ev.hazard == h]
        V = np.clip(np.array([getattr(e, VULN_ATTR[h]) for e in entities]) * vm, 0, 1)
        W = np.vstack([events[i].weights for i in rows])
        I = np.clip(np.array([events[i].intensity for i in rows]) * intensity_mult, 0, 1)[:, None]
        dur = np.array([events[i].duration_days for i in rows])[:, None]
        p = HAZARD_PARAMS[h]
        D = 1 - np.exp(-dur / p["tau"])
        out[rows] = D * (1 - np.exp(-p["k"] * k_mult * np.clip(I * W, 0, 1) * expo[None, :] * V[None, :]))
    return np.clip(out, 0, 1)


def event_T(events: list[Event], recovery_mult: float = 1.0) -> np.ndarray:
    return np.array([ev.duration_days + HAZARD_PARAMS[ev.hazard]["recovery"] * recovery_mult for ev in events])


def weight_vector(net: Network, weights: dict[str, float]) -> np.ndarray:
    w = np.zeros(net.n)
    for k, v in weights.items():
        if k in net.idx:
            w[net.idx[k]] = v
    return w


def run_events(net: Network, d0: np.ndarray, T: np.ndarray, p: Params, chunk: int = 600, **draw) -> np.ndarray:
    """Final disruption (S,N) for many events, processed in chunks to bound memory."""
    out = np.zeros_like(d0)
    for a in range(0, len(d0), chunk):
        hist, _, _ = simulate(net, d0[a:a + chunk], T[a:a + chunk], inventory_scale=p.inventory_scale,
                              substitution_scale=p.substitution_scale, dependency_scale=p.dependency_scale,
                              use_graph_alternatives=p.use_graph_alternatives, cycle_damping=p.cycle_damping,
                              max_depth=p.max_depth, **draw)
        out[a:a + chunk] = hist[-1]
    return out


def score(d0: np.ndarray, final: np.ndarray, T: np.ndarray, w: np.ndarray):
    pf = np.minimum(1.0, T / 365.0)
    p_loc, p_net = (d0 @ w) * pf, (final @ w) * pf
    hidden = np.where(p_net > 1e-12, 1 - p_loc / np.maximum(p_net, 1e-12), 0.0)
    return p_loc, p_net, np.clip(hidden, 0, 1)


def collapse(order: np.ndarray, events: list[Event], d0: np.ndarray, jaccard: float = 0.6) -> tuple[list[int], dict[int, list[int]]]:
    """Group near-duplicate events: same hazard and directly-hit entity sets with Jaccard >= threshold. Walks events in
    rank order; the first of each group is its representative. Returns (representatives in order, rep -> variants)."""
    reps: list[int] = []
    sets: list[set] = []
    variants: dict[int, list[int]] = {}
    for r in order:
        s = set(np.flatnonzero(d0[r] > 0.01).tolist())
        for k, rep in enumerate(reps):
            if events[rep].hazard == events[r].hazard and s and sets[k]:
                if len(s & sets[k]) / len(s | sets[k]) >= jaccard:
                    variants[rep].append(int(r))
                    break
        else:
            reps.append(int(r))
            sets.append(s)
            variants[int(r)] = []
    return reps, variants


def rank_stats(pnet_draws: np.ndarray) -> dict:
    """pnet_draws (n,K): per-draw impacts of K events. Ranks within the K, P(top 5), median rank, IQR."""
    n, K = pnet_draws.shape
    ranks = np.zeros((n, K), dtype=int)
    for j in range(n):
        order = np.argsort(-pnet_draws[j], kind="stable")
        ranks[j, order] = np.arange(1, K + 1)
    med = np.median(ranks, axis=0)
    top20 = np.arange(min(20, K))
    tau = kendalltau(top20, med[top20]).statistic if len(top20) > 2 else float("nan")
    return dict(p_top=(ranks <= TOP).mean(axis=0), median_rank=med, q25=np.percentile(ranks, 25, axis=0),
                q75=np.percentile(ranks, 75, axis=0), kendall_tau_top20=None if np.isnan(tau) else float(tau))


def stability_draws(net: Network, entities: list[Entity], events: list[Event], w: np.ndarray, p: Params, n: int,
                    seed: int) -> np.ndarray:
    """(n,K) portfolio impact of each listed event under n joint parameter draws (shared + local factors, as Monte Carlo)."""
    dr = sample(net, 1, n, seed)
    out = np.zeros((n, len(events)))
    for j in range(n):
        d0 = direct_matrix(entities, events, dr.intensity_mult[j, 0], dr.k_mult[j], dr.vuln_mult[j])
        T = event_T(events, dr.recovery_mult[j])
        fin = run_events(net, d0, T, p, dep=dr.dep[j][None], sub=dr.sub[j][None], alt=dr.alt[j][None],
                         inv=dr.inv[j][None], graph_scale=dr.spare[j])
        out[j] = score(d0, fin, T, w)[1]
    return out


def outage_matrix(net: Network, nodes: list[int], p: Params) -> np.ndarray:
    """(len(nodes),N): final disruption when each listed node alone suffers a full outage for OUTAGE_T days."""
    d0 = np.zeros((len(nodes), net.n))
    d0[np.arange(len(nodes)), nodes] = 1.0
    return run_events(net, d0, np.full(len(nodes), OUTAGE_T), p)


def worst_pairs(net: Network, nodes: list[int], w: np.ndarray, p: Params, single: np.ndarray, top: int = 5) -> dict:
    """Structural bound: exhaustive search over all node pairs (full outage of both), compared with greedy
    (best single node, then its best partner). Not a climate event; shows what the structure can do at worst."""
    pairs = list(itertools.combinations(range(len(nodes)), 2))
    d0 = np.zeros((len(pairs), net.n))
    for r, (a, b) in enumerate(pairs):
        d0[r, nodes[a]] = 1.0
        d0[r, nodes[b]] = 1.0
    fin = run_events(net, d0, np.full(len(pairs), OUTAGE_T), p, chunk=1000)
    val = (fin @ w) * (OUTAGE_T / 365)
    order = np.argsort(-val)
    best_single = int(np.argmax((single @ w)))
    partner = [r for r, (a, b) in enumerate(pairs) if best_single in (a, b)]
    g = max(partner, key=lambda r: val[r]) if partner else int(order[0])
    return dict(n_pairs=len(pairs), exhaustive=[(pairs[r], float(val[r])) for r in order[:top]],
                greedy=(pairs[g], float(val[g])), greedy_matches=bool(abs(val[g] - val[order[0]]) < 1e-12))
