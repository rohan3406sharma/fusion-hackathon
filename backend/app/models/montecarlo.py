"""Monte Carlo uncertainty analysis over analyst-defined input ranges.

Every uncertain input group gets a SHARED (global) factor per draw and, where it varies by item, a LOCAL factor per
entity or link. The shared factors carry the systematic uncertainty ("are all dependencies weaker than we assumed?");
sensitivity is measured on them. Independent per-link noise alone averages out over hundreds of links and would make
influential assumptions look irrelevant (the flaw fixed in v0.2).

The output is a scenario distribution under stated input ranges, not a statistical confidence interval, and it does not
make the underlying assumptions empirically accurate. Structural model error is not represented.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..schemas.domain import Entity, Relation
from ..schemas.scenario import ScenarioSpec
from .climate import DirectExposureInputs, build_direct_inputs, direct_disruption
from .propagation import CAP, Network, compile_network, simulate

SAMPLING = {
    "hazard_intensity": "Shared: intensity x Triangular(0.7, 1.0, 1.3), clipped to [0,1]",
    "damage_steepness": "Shared: damage-function steepness k x LogNormal(0, 0.20)",
    "recovery_time": "Shared: recovery days x Uniform(0.5, 1.5)",
    "vulnerability": "Shared LogNormal(0, 0.25) x per-entity LogNormal(0, 0.15), clipped to [0,1]",
    "dependency": "Shared LogNormal(0, 0.15) x per-link LogNormal(0, 0.15); input groups rescaled if shares exceed 1",
    "substitutability": "Shared shift Normal(0, 0.08) + per-link Normal(0, 0.08), clipped to [0, 0.95]",
    "market_alternatives": "Shared shift Normal(0, 0.08) + per-entity Normal(0, 0.08) on unmodelled-market alternatives",
    "spare_capacity": "Shared: relief from modelled alternative producers x LogNormal(0, 0.30)",
    "inventory": "Shared LogNormal(0, 0.20) x per-entity LogNormal(0, 0.20) on inventory days",
}


@dataclass
class Draws:
    n: int
    shared: dict[str, np.ndarray]     # factor name -> (n,) shared factor values (what sensitivity is measured on)
    intensity_mult: np.ndarray        # (n,C)
    k_mult: np.ndarray                # (n,)
    recovery_mult: np.ndarray         # (n,)
    vuln_mult: np.ndarray             # (n,1,N)
    dep: np.ndarray                   # (n,E)
    sub: np.ndarray                   # (n,E)
    alt: np.ndarray                   # (n,N)
    inv: np.ndarray                   # (n,N)
    spare: np.ndarray                 # (n,)


def sample(net: Network, n_components: int, n: int, seed: int) -> Draws:
    rng = np.random.default_rng(seed)
    N, E = net.n, net.m
    g_int = rng.triangular(0.7, 1.0, 1.3, size=n)
    g_k = rng.lognormal(0, 0.20, size=n)
    g_rec = rng.uniform(0.5, 1.5, size=n)
    g_vul = rng.lognormal(0, 0.25, size=n)
    g_dep = rng.lognormal(0, 0.15, size=n)
    g_sub = rng.normal(0, 0.08, size=n)
    g_alt = rng.normal(0, 0.08, size=n)
    g_spare = rng.lognormal(0, 0.30, size=n)
    g_inv = rng.lognormal(0, 0.20, size=n)
    vuln_mult = g_vul[:, None, None] * rng.lognormal(0, 0.15, size=(n, 1, N))
    dep = net.dep[None, :] * g_dep[:, None] * rng.lognormal(0, 0.15, size=(n, E))
    if E:
        gs = dep @ net.meg
        dep = dep * (np.where(gs > 1, 1 / np.maximum(gs, 1e-12), 1.0) @ net.meg.T)
    sub = np.clip(net.sub[None, :] + g_sub[:, None] + rng.normal(0, 0.08, size=(n, E)), 0, CAP)
    alt = np.clip(net.alt[None, :] + g_alt[:, None] + rng.normal(0, 0.08, size=(n, N)), 0, 1)
    inv = net.inv[None, :] * g_inv[:, None] * rng.lognormal(0, 0.20, size=(n, N))
    shared = {"hazard_intensity": g_int, "damage_steepness": g_k, "recovery_time": g_rec, "vulnerability": g_vul,
              "dependency": g_dep, "substitutability": g_sub, "market_alternatives": g_alt, "spare_capacity": g_spare,
              "inventory": g_inv}
    return Draws(n, shared, np.repeat(g_int[:, None], n_components, axis=1), g_k, g_rec, vuln_mult, dep, sub, alt, inv, g_spare)


def evaluate_draws(net: Network, inp: DirectExposureInputs, spec: ScenarioSpec, dr: Draws, max_depth: int | None = None,
                   weights=None):
    """Runs every draw through direct exposure + propagation. Returns d0 (n,N), final (n,N), T (n,)."""
    intensity = np.clip(inp.intensity[None, :] * dr.intensity_mult, 0, 1)
    vuln = np.clip(inp.vuln[None] * dr.vuln_mult, 0, 1)
    d0 = direct_disruption(inp, intensity=intensity, vuln=vuln, k=inp.k[None, :] * dr.k_mult[:, None])
    T = inp.effective_T(dr.recovery_mult)
    hist, _, _ = simulate(net, d0, T, inventory_scale=spec.inventory_scale, substitution_scale=spec.substitution_scale,
                          dependency_scale=spec.dependency_scale, use_graph_alternatives=spec.use_graph_alternatives,
                          cycle_damping=spec.cycle_damping, max_depth=max_depth or spec.propagation_max_depth,
                          dep=dr.dep, sub=dr.sub, alt=dr.alt, inv=dr.inv, graph_scale=dr.spare)
    return d0, hist[-1], T


def _q(x: np.ndarray) -> dict:
    return dict(mean=float(np.mean(x)), median=float(np.median(x)), p05=float(np.percentile(x, 5)), p25=float(np.percentile(x, 25)),
                p75=float(np.percentile(x, 75)), p95=float(np.percentile(x, 95)), min=float(x.min()), max=float(x.max()))


def sensitivity(shared: dict[str, np.ndarray], y: np.ndarray) -> list[dict]:
    """Spearman rank correlation of each SHARED factor with the output, and an approximate share of explained rank
    variance (rho^2 normalised). Association under these ranges, not causation."""
    yr = pd.Series(y).rank()
    out = []
    for k, v in shared.items():
        s = pd.Series(v).rank().corr(yr)
        out.append(dict(parameter=k, spearman_with_total_loss=float(0.0 if np.isnan(s) else s), description=SAMPLING[k]))
    tot = sum(o["spearman_with_total_loss"] ** 2 for o in out) or 1.0
    for o in out:
        o["approx_variance_share"] = round(o["spearman_with_total_loss"] ** 2 / tot, 4)
    out.sort(key=lambda x: -abs(x["spearman_with_total_loss"]))
    return out


def run_monte_carlo(entities: list[Entity], relations: list[Relation], spec: ScenarioSpec, n: int, seed: int,
                    deterministic_total: float, max_depth: int | None = None, top_k: int = 12) -> dict:
    net = compile_network(entities, relations)
    inp = build_direct_inputs(entities, spec)
    dr = sample(net, len(spec.hazards), n, seed)
    d0, final, T = evaluate_draws(net, inp, spec, dr, max_depth)
    pf = np.minimum(1.0, T / 365.0)[:, None]
    va = net.va[None, :] * pf
    dloss, tloss = va * d0, va * final
    tot, dtot = tloss.sum(1), dloss.sum(1)
    itot = tot - dtot
    counts, edges = np.histogram(tot, bins=20)
    hist_rows = [dict(lo=float(edges[i]), hi=float(edges[i + 1]), count=int(counts[i])) for i in range(len(counts))]
    order = np.argsort(-np.median(tloss, axis=0))[:top_k]
    top = [dict(entity_id=net.node_ids[i], name=entities[i].name, median_loss_musd=float(np.median(tloss[:, i])),
                p05_loss_musd=float(np.percentile(tloss[:, i], 5)), p95_loss_musd=float(np.percentile(tloss[:, i], 95)),
                probability_affected=float((final[:, i] > 0.01).mean())) for i in order
           if np.median(tloss[:, i]) > 0 or np.percentile(tloss[:, i], 95) > 0]
    return dict(
        n_simulations=n, seed=seed, total_loss=_q(tot), direct_loss=_q(dtot), indirect_loss=_q(itot),
        network_minus_location=_q(tot - dtot), histogram=hist_rows, sensitivity=sensitivity(dr.shared, tot),
        indirect_sensitivity=sensitivity(dr.shared, itot), top_entities=top,
        assumptions=[f"{k}: {v}" for k, v in SAMPLING.items()],
        interpretation=("Spread of modelled value-added loss when the listed inputs vary within analyst-defined ranges. The 5th-95th percentile "
                        "range is a scenario-uncertainty range, NOT a formal confidence interval, and structural/model error is not included. "
                        "Sensitivity is measured on the shared factor of each input group."),
        deterministic_total_loss_musd=round(deterministic_total, 3))
