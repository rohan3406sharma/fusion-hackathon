"""Monte Carlo uncertainty analysis over analyst-defined input ranges.

The output is a *scenario distribution under stated input ranges*, not a statistical confidence interval, and it does not
make the underlying assumptions empirically accurate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..schemas.domain import Entity, Relation
from ..schemas.scenario import ScenarioSpec
from .climate import build_direct_inputs, direct_disruption
from .propagation import CAP, compile_network, propagate, transmission

SAMPLING = {
    "hazard_intensity": "Per hazard component: intensity x Triangular(0.7, 1.0, 1.3), clipped to [0,1]",
    "vulnerability": "Global factor LogNormal(0, 0.25) x per-entity LogNormal(0, 0.15), clipped to [0,1]",
    "dependency": "Per edge LogNormal(0, 0.20); each (customer,input) group rescaled if its shares exceed 1",
    "substitutability": "Per edge additive Normal(0, 0.10), clipped to [0, 0.95]",
    "alternatives": "Per entity alternative-supplier availability + Normal(0, 0.10), clipped to [0, 1]",
    "inventory": "Per entity inventory days x LogNormal(0, 0.30)",
}


def _q(x: np.ndarray) -> dict:
    return dict(mean=float(np.mean(x)), median=float(np.median(x)), p05=float(np.percentile(x, 5)), p25=float(np.percentile(x, 25)),
                p75=float(np.percentile(x, 75)), p95=float(np.percentile(x, 95)), min=float(x.min()), max=float(x.max()))


def run_monte_carlo(entities: list[Entity], relations: list[Relation], spec: ScenarioSpec, n: int, seed: int,
                    deterministic_total: float, max_depth: int | None = None, top_k: int = 12) -> dict:
    rng = np.random.default_rng(seed)
    net = compile_network(entities, relations)
    inp = build_direct_inputs(entities, spec)
    C, N, E = len(spec.hazards), net.n, net.m
    # --- sampled inputs
    mult_h = rng.triangular(0.7, 1.0, 1.3, size=(n, C))
    intensity = np.clip(inp.intensity[None, :] * mult_h, 0, 1)
    vg = rng.lognormal(0, 0.25, size=(n, 1, 1))
    vi = rng.lognormal(0, 0.15, size=(n, 1, N))
    vuln = np.clip(inp.vuln[None] * vg * vi, 0, 1)
    dep_mult = rng.lognormal(0, 0.20, size=(n, E))
    dep = net.dep[None, :] * dep_mult
    if E:
        gs = dep @ net.meg                                    # (n,G) group sums
        scale = np.where(gs > 1, 1 / np.maximum(gs, 1e-12), 1.0)
        dep = dep * (scale @ net.meg.T)
    sub_shift = rng.normal(0, 0.10, size=(n, E))
    sub = np.clip(net.sub[None, :] + sub_shift, 0, CAP)
    alt_shift = rng.normal(0, 0.10, size=(n, N))
    alt = np.clip(net.alt[None, :] + alt_shift, 0, 1)
    inv_mult = rng.lognormal(0, 0.30, size=(n, N))
    inv = net.inv[None, :] * inv_mult
    # --- evaluate
    d0 = direct_disruption(inp, intensity=intensity, vuln=vuln)                                     # (n,N)
    trans = transmission(net, inp.effective_duration_days, dep=dep, sub=sub, inv=inv, alt=alt, inventory_scale=spec.inventory_scale,
                         substitution_scale=spec.substitution_scale, dependency_scale=spec.dependency_scale)
    hist, _ = propagate(net, d0, trans, max_depth=max_depth or spec.propagation_max_depth)
    final = hist[-1]
    pf = min(1.0, inp.effective_duration_days / 365.0)
    va = net.va[None, :] * pf
    dloss, tloss = (va * d0), (va * final)
    tot, dtot = tloss.sum(1), dloss.sum(1)
    itot = tot - dtot
    # --- histogram + sensitivity
    counts, edges = np.histogram(tot, bins=20)
    hist_rows = [dict(lo=float(edges[i]), hi=float(edges[i + 1]), count=int(counts[i])) for i in range(len(counts))]
    drivers = {
        "hazard_intensity": mult_h.mean(1), "vulnerability": vg[:, 0, 0] * vi[:, 0, :].mean(1), "dependency": dep_mult.mean(1) if E else np.ones(n),
        "substitutability": sub_shift.mean(1) if E else np.zeros(n), "alternatives": alt_shift.mean(1), "inventory": inv_mult.mean(1),
    }
    sens = []
    for k, v in drivers.items():
        s = pd.Series(v).rank().corr(pd.Series(tot).rank())
        sens.append(dict(parameter=k, spearman_with_total_loss=float(0.0 if np.isnan(s) else s), description=SAMPLING[k]))
    sens.sort(key=lambda x: -abs(x["spearman_with_total_loss"]))
    order = np.argsort(-np.median(tloss, axis=0))[:top_k]
    top = [dict(entity_id=net.node_ids[i], name=entities[i].name, median_loss_musd=float(np.median(tloss[:, i])),
                p05_loss_musd=float(np.percentile(tloss[:, i], 5)), p95_loss_musd=float(np.percentile(tloss[:, i], 95)),
                probability_affected=float((final[:, i] > 0.01).mean())) for i in order if np.median(tloss[:, i]) > 0 or np.percentile(tloss[:, i], 95) > 0]
    return dict(
        n_simulations=n, seed=seed, total_loss=_q(tot), direct_loss=_q(dtot), indirect_loss=_q(itot),
        network_minus_location=_q(tot - dtot), histogram=hist_rows, sensitivity=sens, top_entities=top,
        assumptions=[f"{k}: {v}" for k, v in SAMPLING.items()],
        interpretation=("Spread of modelled value-added loss when the listed inputs vary within analyst-defined ranges. The 5th-95th percentile "
                        "range is a scenario-uncertainty range, NOT a formal confidence interval, and structural/model error is not included."),
        deterministic_total_loss_musd=round(deterministic_total, 3))
