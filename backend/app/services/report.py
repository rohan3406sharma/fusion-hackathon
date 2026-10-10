"""Plain-text exports of a scenario run (Markdown + CSV)."""
from __future__ import annotations

import csv
import io

from ..schemas.results import RunResult


def to_markdown(r: RunResult, mc=None) -> str:
    s, c = r.summary, r.comparison
    L = [f"# Scenario report: {r.scenario.name}", "",
         "> Food & Beverage demonstration. All entities, links and hazard footprints are SYNTHETIC; results are model estimates, not forecasts.", "",
         "## Summary", "",
         f"- Entities analysed: {s.n_entities}", f"- Directly exposed facilities: {s.n_exposed_facilities}",
         f"- Affected downstream entities: {s.n_affected_downstream}",
         f"- Direct loss (location-only): USD {s.direct_loss_musd:,.1f} M", f"- Indirect (modelled): USD {s.indirect_loss_musd:,.1f} M",
         f"- Network-aware total: USD {s.total_loss_musd:,.1f} M",
         f"- Propagation iterations: {s.iterations} (converged: {s.converged})", "", "## Loss by propagation order", "",
         "| Order | Entities | Loss (USD M) | Evidence |", "|---|---|---|---|"]
    L += [f"| {o.label} | {o.entities} | {o.loss_musd:,.1f} | {o.evidence} |" for o in r.orders]
    L += ["", "## Location-only vs network-aware", "",
          f"- Whole network: {c.location_only_loss_musd:,.1f} -> {c.network_aware_loss_musd:,.1f} (diff {c.absolute_difference_musd:,.1f}; relative {c.relative_difference})",
          f"- Demo portfolio (unweighted USD M sum): {c.portfolio_location_loss_musd:,.1f} -> {c.portfolio_network_loss_musd:,.1f}; hidden exposures: {c.hidden_exposure_count}",
          f"- Demo portfolio, position-weighted share of annual value added lost: {c.portfolio_location_impact:.4%} location-only vs {c.portfolio_network_impact:.4%} network-aware",
          "- Hidden-exposure count by cut-off: " + ", ".join(f"{x['threshold']:.0%}: {x['count']}" for x in c.hidden_exposure_curve),
          f"- {c.scope_note}", "", "## Top affected entities", "", "| Entity | Status | Hop | Direct | Final | Total loss (USD M) |", "|---|---|---|---|---|---|"]
    for e in sorted(r.entities, key=lambda e: -e.total_loss_musd)[:15]:
        L.append(f"| {e.name} (SYN) | {e.status} | {e.hop_order} | {e.direct_disruption:.2f} | {e.final_disruption:.2f} | {e.total_loss_musd:,.1f} |")
    L += ["", "## Critical propagation paths", ""]
    for p in r.critical_paths:
        L.append(f"- {' -> '.join(p.names)} (cumulative transmission {p.cumulative_transmission:.3f})")
    if mc is not None:
        q = mc.total_loss
        L += ["", "## Uncertainty analysis (Monte Carlo)", "",
              f"- {mc.n_simulations} simulations, seed {mc.seed}; deterministic total {mc.deterministic_total_loss_musd:,.1f}",
              f"- Total loss: median {q.median:,.1f}; 5th-95th percentile {q.p05:,.1f} - {q.p95:,.1f} (USD M)",
              f"- {mc.interpretation}", "- Sampled assumptions:"] + [f"  - {a}" for a in mc.assumptions]
        L += ["- Sensitivity (Spearman rank correlation with total loss):"] + [f"  - {s.parameter}: {s.spearman_with_total_loss:+.2f}" for s in mc.sensitivity]
    L += ["", "## Assumptions", ""] + [f"- {a}" for a in r.assumptions] + ["", "## Limitations", ""] + [f"- {x}" for x in r.limitations]
    return "\n".join(L) + "\n"


def to_csv(r: RunResult) -> str:
    buf = io.StringIO()
    meta = ["scenario_id", "scenario_name", "data_status"]
    cols = ["entity_id", "name", "entity_type", "food_category", "country", "region", "status", "hop_order", "hazard_intensity",
            "direct_disruption", "final_disruption", "value_added_musd", "direct_loss_musd", "indirect_loss_musd", "total_loss_musd"]
    w = csv.writer(buf)
    w.writerow(meta + cols)
    for e in r.entities:
        d = e.model_dump()
        w.writerow([r.scenario_id or "", r.scenario.name, "synthetic" if d["synthetic"] else "observed"] + [d[c] for c in cols])
    return buf.getvalue()
