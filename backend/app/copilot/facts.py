"""Fact sheets: the only source of numbers, names, paths and rankings the copilot may state.

Every Fact carries a provenance label and the API field it came from. Nothing here is computed by a language model, and no
number is derived beyond formatting; ranks, shares and impacts are copied from the deterministic engine's own outputs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.dataset import FnbDataset
from ..schemas.copilot import FinderEventFocus, MitigationFocus, ScenarioFocus
from ..schemas.scenario import HazardComponent, ScenarioSpec

PCT, PCT0, USD, COUNT, TEXT, DAYS, INDEX, YESNO, NUM = "pct", "pct0", "usd_m", "count", "text", "days", "index", "yesno", "number"
UNITS = {PCT: "% of annual value added", PCT0: "%", USD: "USD million", COUNT: "count", TEXT: "text", DAYS: "days", INDEX: "index 0-1",
         YESNO: "yes/no", NUM: "number"}
# facts the language model may use to justify the words "robust"/"stable" (ranking stability), never a loss magnitude
STABILITY_KINDS = {"p_top5", "median_rank", "kendall_tau", "stability_draws"}
MAGNITUDE_IDS_PREFIX = ("impact_", "loss_", "tail_", "reduction_", "cost_", "residual_", "holding_net_", "holding_dir_", "mit_")


def render(kind: str, v: Any) -> str:
    if v is None:
        return "not available"
    if kind == PCT:
        return f"{float(v) * 100:.2f}%"
    if kind == PCT0:
        return f"{float(v) * 100:.0f}%"
    if kind == USD:
        return f"${float(v):,.1f}M"
    if kind == COUNT:
        return f"{int(v)}"
    if kind == DAYS:
        return f"{float(v):.0f} days"
    if kind == INDEX:
        return f"{float(v):.2f}"
    if kind == YESNO:
        return "yes" if v else "no"
    if kind == NUM:
        return f"{float(v):.2f}"
    return str(v)


@dataclass
class Fact:
    id: str
    label: str
    kind: str
    value: Any
    provenance: str
    source: str
    rendered: str = ""

    def __post_init__(self):
        self.rendered = render(self.kind, self.value)

    @property
    def is_magnitude(self) -> bool:
        """A numeric loss/impact/cost figure from the model (never a ranking-stability statistic)."""
        return self.kind != TEXT and self.provenance in ("unvalidated_model_output", "model_assumption") and self.id.startswith(MAGNITUDE_IDS_PREFIX)

    @property
    def is_stability(self) -> bool:
        return self.provenance == "model_robustness"


@dataclass
class FactSheet:
    title: str
    focus_kind: str
    facts: dict[str, Fact] = field(default_factory=dict)
    names: set[str] = field(default_factory=set)       # every entity name in the fact sheet (for leak checks)
    all_entity_vocab: set[str] = field(default_factory=set)

    def add(self, id_: str, label: str, kind: str, value: Any, prov: str, source: str) -> Fact:
        assert id_ not in self.facts, id_
        f = Fact(id_, label, kind, value, prov, source)
        self.facts[id_] = f
        if kind == TEXT and id_.endswith("_name"):
            self.names.add(str(value))
        return f

    def has(self, id_: str) -> bool:
        return id_ in self.facts


NOTICES = {
    "notice_synthetic": ("Data status", "All entities, supply links, coordinates, portfolio weights and intervention costs are synthetic demonstration data; only the "
                         "river-flood hazard layer is real, and it is used as context, not as a loss input.", "synthetic_input", "docs/DATA_SOURCES.md"),
    "notice_unvalidated": ("Validation status", "Loss magnitudes come from an uncalibrated damage proxy and have not been validated against any observed event; "
                           "no empirical validation exists.", "model_assumption", "METHODOLOGY.md"),
    "notice_no_probability": ("Probability status", "Events carry no probabilities, so rankings are by consequence, not likelihood, and nothing here is a forecast.",
                              "model_assumption", "METHODOLOGY.md §7a"),
}


def _standing(fs: FactSheet) -> None:
    for k, (label, text, prov, src) in NOTICES.items():
        fs.add(k, label, TEXT, text, prov, src)


def _vocab(ds: FnbDataset) -> set[str]:
    out = set()
    for e in ds.entities:
        for field_ in (e.name, e.country or "", e.region or ""):
            for tok in field_.replace("-", " ").replace(",", " ").replace(".", " ").split():
                if len(tok) > 2:
                    out.add(tok)
    return out


def _event_core(fs: FactSheet, ev, res, ds: FnbDataset, list_name: str = "all events", rank_all: int | None = None) -> None:
    h = ev.hazard_component
    fs.add("event_label", "Event", TEXT, ev.label, "synthetic_input", "events[].label")
    fs.add("event_hazard", "Hazard", TEXT, ev.hazard, "synthetic_input", "events[].hazard")
    fs.add("event_intensity", "Reference intensity index", INDEX, h.intensity, "model_assumption", "events[].hazard_component.intensity")
    fs.add("event_duration", "Event duration", DAYS, h.duration_days, "model_assumption", "events[].hazard_component.duration_days")
    fs.add("impact_network", "Portfolio impact, network-aware", PCT, ev.portfolio_network_impact, "unvalidated_model_output", "events[].portfolio_network_impact")
    fs.add("impact_location", "Portfolio impact, location-only (zero means no holding is hit directly)", PCT, ev.portfolio_location_impact, "unvalidated_model_output", "events[].portfolio_location_impact")
    fs.add("hidden_share", "Hidden share (part a location-only screen misses)", PCT0, ev.hidden_share, "unvalidated_model_output", "events[].hidden_share")
    fs.add("hidden_only", "No holding is hit directly", YESNO, ev.hidden_only, "unvalidated_model_output", "events[].hidden_only")
    fs.add("holdings_affected", "Holdings affected (>1% disruption)", COUNT, ev.holdings_affected, "unvalidated_model_output", "events[].holdings_affected")
    fs.add("entities_hit_directly", "Entities of any kind (not only holdings) hit directly", COUNT, ev.entities_hit_directly, "unvalidated_model_output", "events[].entities_hit_directly")
    fs.add("ranking_list", "The ranked list this event's rank and stability refer to", TEXT, list_name, "model_robustness", "events[] list")
    fs.add("event_rank", f"Rank among {list_name} (by portfolio impact)", COUNT, ev.rank, "unvalidated_model_output", "events[].rank")
    if rank_all is not None:
        fs.add("event_rank_all", "Rank among all events", COUNT, rank_all, "unvalidated_model_output", "events[].rank (all events list)")
    if ev.p_top5 is not None:
        fs.add("p_top5", f"Share of uncertainty draws in which the event stays in the top 5 of {list_name}", PCT0, ev.p_top5, "model_robustness", "events[].p_top5")
        fs.add("median_rank", f"Median rank among {list_name} across draws", NUM, ev.median_rank, "model_robustness", "events[].median_rank")
        fs.add("fragile", "Flagged fragile (top 5 deterministically, below 50% under draws)", YESNO, bool(ev.fragile), "model_robustness", "events[].fragile")
        st = res.stability or {}
        fs.add("stability_draws", "Uncertainty draws used", COUNT, st.get("n_draws"), "model_robustness", "stability.n_draws")
        if st.get("kendall_tau_top20") is not None:
            fs.add("kendall_tau", "Kendall tau of the top 20 across draws", NUM, st["kendall_tau_top20"], "model_robustness", "stability.kendall_tau_top20")
    if ev.jrc_flood_check:
        fs.add("jrc_check", "JRC 100-year river-flood map near the directly hit entities", TEXT, ev.jrc_flood_check, "real_hazard_context", "events[].jrc_flood_check")
        hl = res.hazard_layer or {}
        if hl.get("entities_total"):
            fs.add("jrc_base_rate", "Entities with some modelled flooding within 5 km (base rate: the check is lenient)", TEXT,
                   f"{hl['entities_with_any_flooding']} of {hl['entities_total']}", "real_hazard_context", "hazard_layer.entities_with_any_flooding")
    for i, hd in enumerate(ev.top_holdings[:5], 1):
        fs.add(f"holding_{i}_name", f"Holding {i}", TEXT, hd.name, "synthetic_input", f"events[].top_holdings[{i-1}].name")
        fs.add(f"holding_dir_{i}", f"Holding {i} direct disruption", PCT0, hd.direct_disruption, "unvalidated_model_output", f"events[].top_holdings[{i-1}].direct_disruption")
        fs.add(f"holding_net_{i}", f"Holding {i} network disruption", PCT0, hd.network_disruption, "unvalidated_model_output", f"events[].top_holdings[{i-1}].network_disruption")
        fs.add(f"holding_{i}_weight", f"Holding {i} synthetic portfolio weight", PCT, hd.weight, "synthetic_input", f"events[].top_holdings[{i-1}].weight")
        _structure(fs, i, hd.kind, hd.other_businesses_share, hd.network_disruption_if_other_hit, f"events[].top_holdings[{i-1}]")


def _structure(fs: FactSheet, i: int, kind: str | None, other: float | None, upper: float | None, src: str) -> None:
    """Company structure of holding i (company view): only for companies that own several business units or businesses
    outside Food & Beverage. The share outside F&B is a synthetic input and is never modelled."""
    if kind != "multi_segment":
        return
    text = ("a company with several business units, part of its value added outside food and beverage, which is not modelled"
            if other else "a company with several business units")
    fs.add(f"holding_{i}_structure", f"Holding {i} company structure", TEXT, text, "synthetic_input", f"{src}.segments")
    if other:
        fs.add(f"holding_{i}_other_share", f"Holding {i} share of value added outside food and beverage (not modelled)", PCT0, other,
               "synthetic_input", f"{src}.other_businesses_share")
        if upper is not None:
            fs.add(f"holding_net_{i}_if_other_hit", f"Holding {i} network disruption if its businesses outside food and beverage were hit as hard (upper end)",
                   PCT0, upper, "unvalidated_model_output", f"{src}.network_disruption_if_other_hit")


def _paths(fs: FactSheet, run, owned: set, ds: FnbDataset, n: int = 3) -> None:
    held = [p for p in run.critical_paths if p.terminal_id in owned]       # paths ending at any business unit a held company owns
    held.sort(key=lambda p: -p.terminal_total_loss_musd)
    for i, p in enumerate(held[:n], 1):
        fs.add(f"path_{i}", f"Dominant propagation path {i}", TEXT, " → ".join(p.names), "unvalidated_model_output", f"critical_paths[{i-1}].names")
        fs.add(f"path_{i}_transmission", f"Path {i} cumulative transmission (a diagnostic, not a loss share)", PCT, p.cumulative_transmission, "unvalidated_model_output",
               f"critical_paths[{i-1}].cumulative_transmission")
        fs.add(f"path_{i}_hops", f"Path {i} hops", COUNT, len(p.hops), "unvalidated_model_output", f"critical_paths[{i-1}].hops")
        for j, hp in enumerate(p.hops[:4], 1):
            fs.add(f"path_{i}_hop_{j}", f"Path {i} step {j}", TEXT, f"{ds.by_id[hp.source].name} supplies {hp.product.replace('_', ' ')} to {ds.by_id[hp.target].name}",
                   "synthetic_input", f"critical_paths[{i-1}].hops[{j-1}]")
    if not held:
        fs.add("no_path", "Graph path evidence", TEXT, "no multi-hop path to a holding was identified among the dominant paths", "unvalidated_model_output", "critical_paths")


def _orders(fs: FactSheet, run) -> None:
    for o in run.orders[:4]:
        key = {"direct": "direct", "1": "order1", "2": "order2", "3": "order3"}[o.order]
        fs.add(f"loss_{key}", f"{o.label} loss", USD, o.loss_musd, "unvalidated_model_output", f"orders[{o.order}].loss_musd")
        fs.add(f"orderN_{key}", f"{o.label} entities", COUNT, o.entities, "unvalidated_model_output", f"orders[{o.order}].entities")
    fs.add("evidence_order1", "Evidence for first-order propagation", TEXT, run.orders[1].evidence, "model_assumption", "orders[1].evidence")
    fs.add("evidence_order3", "Evidence for third-order propagation", TEXT, run.orders[3].evidence, "model_assumption", "orders[3].evidence")


def _mitigation_for_run(fs: FactSheet, ds: FnbDataset, spec: ScenarioSpec, run, depth: int | None) -> None:
    from ..models.mitigation import candidate_interventions, evaluate_interventions
    cands = candidate_interventions(ds.entities, [r.model_dump() for r in run.entities])
    if not cands:
        fs.add("mit_none", "Mitigation evidence", TEXT, "no affected entity to mitigate", "unvalidated_model_output", "mitigation")
        return
    out = evaluate_interventions(ds.entities, ds.relations, spec, cands[:24], 0.10, 10, depth)
    for i, o in enumerate(out["options"][:3], 1):
        fs.add(f"mit_{i}_label", f"Candidate intervention {i}", TEXT, o["label"], "model_assumption", f"mitigation.options[{i-1}].label")
        fs.add(f"mit_{i}_reduction", f"Intervention {i}: modelled reduction in scenario value-added loss", USD, o["effect"]["loss_reduction_musd"],
               "unvalidated_model_output", f"mitigation.options[{i-1}].effect.loss_reduction_musd")
        fs.add(f"mit_{i}_cost", f"Intervention {i}: annualised cost (synthetic placeholder)", USD, o["cost"]["annualised_cost_musd"], "model_assumption",
               f"mitigation.options[{i-1}].cost.annualised_cost_musd")
    fs.add("residual_loss", "Scenario value-added loss with no intervention", USD, out["baseline"]["total_loss_musd"], "unvalidated_model_output", "mitigation.baseline.total_loss_musd")


def finder_event_sheet(ds: FnbDataset, focus: FinderEventFocus, res, owned: set, run, spec: ScenarioSpec, event, list_name: str = "all events",
                       rank_all: int | None = None) -> FactSheet:
    fs = FactSheet(title=f"Hidden exposure: {event.label}", focus_kind="finder_event")
    fs.all_entity_vocab = _vocab(ds)
    _event_core(fs, event, res, ds, list_name, rank_all)
    fs.add("scenario_effective_window", "Disruption window (event + recovery)", DAYS, run.summary.effective_duration_days, "model_assumption", "summary.effective_duration_days")
    fs.add("loss_total", "Scenario value-added loss, whole network", USD, run.summary.total_loss_musd, "unvalidated_model_output", "summary.total_loss_musd")
    fs.add("loss_direct_total", "Scenario value-added loss, direct", USD, run.summary.direct_loss_musd, "unvalidated_model_output", "summary.direct_loss_musd")
    _orders(fs, run)
    _paths(fs, run, owned, ds)
    _mitigation_for_run(fs, ds, spec, run, focus.finder.max_depth)
    _standing(fs)
    return fs


def scenario_sheet(ds: FnbDataset, focus: ScenarioFocus, run, mc, owned: set) -> FactSheet:
    fs = FactSheet(title=f"Scenario: {run.scenario.name}", focus_kind="scenario")
    fs.all_entity_vocab = _vocab(ds)
    s, c = run.summary, run.comparison
    fs.add("scenario_name", "Scenario", TEXT, run.scenario.name, "synthetic_input", "scenario.name")
    fs.add("scenario_hazards", "Hazards", TEXT, " + ".join(h.hazard_type for h in run.scenario.hazards), "synthetic_input", "scenario.hazards")
    fs.add("scenario_effective_window", "Disruption window (event + recovery)", DAYS, s.effective_duration_days, "model_assumption", "summary.effective_duration_days")
    fs.add("loss_direct_total", "Direct value-added loss", USD, s.direct_loss_musd, "unvalidated_model_output", "summary.direct_loss_musd")
    fs.add("loss_total", "Network-aware value-added loss", USD, s.total_loss_musd, "unvalidated_model_output", "summary.total_loss_musd")
    fs.add("loss_indirect_total", "Indirect value-added loss", USD, s.indirect_loss_musd, "unvalidated_model_output", "summary.indirect_loss_musd")
    fs.add("entities_exposed", "Directly exposed entities", COUNT, s.n_exposed_facilities, "unvalidated_model_output", "summary.n_exposed_facilities")
    fs.add("entities_downstream", "Entities affected only through supply links", COUNT, s.n_affected_downstream, "unvalidated_model_output", "summary.n_affected_downstream")
    fs.add("impact_location", "Portfolio impact, location-only", PCT, c.portfolio_location_impact, "unvalidated_model_output", "comparison.portfolio_location_impact")
    fs.add("impact_network", "Portfolio impact, network-aware", PCT, c.portfolio_network_impact, "unvalidated_model_output", "comparison.portfolio_network_impact")
    if c.portfolio_hidden_share is not None:
        fs.add("hidden_share", "Portfolio hidden share", PCT0, c.portfolio_hidden_share, "unvalidated_model_output", "comparison.portfolio_hidden_share")
    hid = [r for r in c.portfolio_rows if r.hidden_exposure]
    fs.add("holdings_hidden_count", "Holdings with hidden exposure (<1% direct, >=5% propagated)", COUNT, len(hid), "unvalidated_model_output", "comparison.hidden_exposure_count")
    for i, r in enumerate(sorted(c.portfolio_rows, key=lambda r: -r.network_disruption)[:5], 1):
        fs.add(f"holding_{i}_name", f"Holding {i}", TEXT, r.name, "synthetic_input", f"comparison.portfolio_rows[{i-1}].name")
        fs.add(f"holding_dir_{i}", f"Holding {i} direct disruption", PCT0, r.location_disruption, "unvalidated_model_output", f"comparison.portfolio_rows[{i-1}].location_disruption")
        fs.add(f"holding_net_{i}", f"Holding {i} network disruption", PCT0, r.network_disruption, "unvalidated_model_output", f"comparison.portfolio_rows[{i-1}].network_disruption")
        _structure(fs, i, r.kind, r.other_businesses_share, r.network_disruption_if_other_hit, f"comparison.portfolio_rows[{i-1}]")
    _orders(fs, run)
    _paths(fs, run, owned, ds)
    if mc is not None:
        fs.add("mc_runs", "Monte Carlo draws", COUNT, mc.n_simulations, "model_robustness", "monte_carlo.n_simulations")
        fs.add("loss_mc_p05", "5th percentile, scenario value-added loss", USD, mc.total_loss.p05, "unvalidated_model_output", "monte_carlo.total_loss.p05")
        fs.add("loss_mc_median", "Median, scenario value-added loss", USD, mc.total_loss.median, "unvalidated_model_output", "monte_carlo.total_loss.median")
        fs.add("loss_mc_p95", "95th percentile, scenario value-added loss", USD, mc.total_loss.p95, "unvalidated_model_output", "monte_carlo.total_loss.p95")
    spec = ScenarioSpec(**run.scenario.model_dump())
    _mitigation_for_run(fs, ds, spec, run, focus.max_depth)
    _standing(fs)
    return fs


def mitigation_sheet(ds: FnbDataset, focus: MitigationFocus, opt: dict) -> FactSheet:
    fs = FactSheet(title=f"Mitigation plan, budget ${opt['budget_musd']:g}M a year", focus_kind="mitigation_plan")
    fs.all_entity_vocab = _vocab(ds)
    fs.add("budget", "Budget (annualised, synthetic placeholder costs)", USD, opt["budget_musd"], "model_assumption", "budget_musd")
    fs.add("tail_events_n", "Worst events averaged", COUNT, opt["tail_events"], "model_assumption", "tail_events")
    fs.add("events_considered", "Distinct events considered", COUNT, opt["n_events"], "model_assumption", "n_events")
    fs.add("tail_before", "Mean portfolio impact of the worst events, before the plan", PCT, opt["baseline_objective"], "unvalidated_model_output", "baseline_objective")
    fs.add("tail_after", "Mean portfolio impact of the worst events, after the plan", PCT, opt["plan_objective"], "unvalidated_model_output", "plan_objective")
    if opt["reduction_fraction"] is not None:
        fs.add("reduction_fraction", "Relative reduction in that tail impact", PCT, opt["reduction_fraction"], "unvalidated_model_output", "reduction_fraction")
    fs.add("cost_plan", "Plan annualised cost (synthetic placeholder)", USD, opt["plan_cost_musd"], "model_assumption", "plan_cost_musd")
    fs.add("plan_size", "Interventions in the plan", COUNT, len(opt["plan"]), "model_assumption", "plan")
    for i, p in enumerate(opt["plan"][:6], 1):
        fs.add(f"mit_{i}_label", f"Plan intervention {i}", TEXT, p["label"], "model_assumption", f"plan[{i-1}].label")
        fs.add(f"mit_{i}_cost", f"Plan intervention {i} annualised cost (synthetic placeholder)", USD, p["annualised_cost_musd"], "model_assumption", f"plan[{i-1}].annualised_cost_musd")
    ex = opt.get("exhaustive")
    if ex:
        fs.add("exhaustive_plans", "Affordable plans checked by brute force (within the stated pool)", COUNT, ex["n_feasible_plans"], "model_robustness", "exhaustive.n_feasible_plans")
        if ex["optimality_gap"] is not None:
            fs.add("optimality_gap", "Optimality gap against brute force within that pool", PCT0, ex["optimality_gap"], "model_robustness", "exhaustive.optimality_gap")
    for i, c in enumerate(opt["cost_sensitivity"], 1):
        fs.add(f"cost_sens_{i}_factor", f"Cost sensitivity {i}: cost multiplier", NUM, c["cost_factor"], "model_assumption", f"cost_sensitivity[{i-1}].cost_factor")
        fs.add(f"cost_sens_{i}_overlap", f"Cost sensitivity {i}: share of the plan unchanged", PCT0, c["jaccard_with_base"], "model_robustness", f"cost_sensitivity[{i-1}].jaccard_with_base")
    rb = opt.get("robustness")
    if rb:
        fs.add("robust_draws", "Uncertainty draws for the plan", COUNT, rb["n_draws"], "model_robustness", "robustness.n_draws")
        fs.add("robust_positive", "Share of draws in which the plan reduces the tail impact", PCT0, rb["share_positive"], "model_robustness", "robustness.share_positive")
    for i, r in enumerate(opt.get("residual_events", [])[:5], 1):
        fs.add(f"residual_{i}_label", f"Residual event {i}", TEXT, r["label"], "synthetic_input", f"residual_events[{i-1}].label")
        fs.add(f"residual_{i}_after", f"Residual event {i}: portfolio impact after the plan", PCT, r["after_impact"], "unvalidated_model_output", f"residual_events[{i-1}].after_impact")
        fs.add(f"residual_{i}_before", f"Residual event {i}: portfolio impact before the plan", PCT, r["baseline_impact"], "unvalidated_model_output", f"residual_events[{i-1}].baseline_impact")
    _standing(fs)
    return fs
