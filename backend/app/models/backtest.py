"""Back-testing interface: compare simulated entity disruption with supplied observations.

No historical validation ships with this project. `synthetic_demo` generates pseudo-observations by perturbing the model's own
output; it demonstrates the interface only and is circular by construction (NOT validation).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def evaluate(simulated: dict[str, float], observed: dict[str, float]) -> dict:
    ids = sorted(set(simulated) & set(observed))
    if len(ids) < 3:
        return dict(n=len(ids), metrics=None, note="Need at least 3 overlapping entities to compute metrics.", missing=sorted(set(observed) - set(simulated)))
    s = np.array([simulated[i] for i in ids])
    o = np.array([observed[i] for i in ids])
    rho = pd.Series(s).rank().corr(pd.Series(o).rank()) if s.std() > 0 and o.std() > 0 else float("nan")
    thr = 0.05
    tp = int(((s > thr) & (o > thr)).sum())
    fp = int(((s > thr) & (o <= thr)).sum())
    fn = int(((s <= thr) & (o > thr)).sum())
    return dict(n=len(ids), missing=sorted(set(observed) - set(simulated)), metrics=dict(
        mae=float(np.mean(np.abs(s - o))), rmse=float(np.sqrt(np.mean((s - o) ** 2))), bias=float(np.mean(s - o)),
        spearman=None if np.isnan(rho) else float(rho),
        precision=tp / (tp + fp) if tp + fp else None, recall=tp / (tp + fn) if tp + fn else None,
        threshold=thr), note="Metrics on disruption fractions (0-1).")


def synthetic_demo(simulated: dict[str, float], seed: int = 7, noise: float = 0.08) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    return {k: float(np.clip(v * rng.lognormal(0, 0.3) + rng.normal(0, noise) * (v > 0.01), 0, 1)) for k, v in simulated.items()}
