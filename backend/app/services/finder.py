"""Orchestrates the Hidden Exposure Finder: library -> batch scoring -> ranking -> stability -> structure."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..domain.dataset import FnbDataset
from ..domain.holdings import Holdings, build_holdings, holding_meta
from ..models import reverse_stress as rs
from ..models.events import build_library
from ..models.propagation import compile_network
from ..schemas.finder import FinderRequest, FinderResult

ASSUMPTIONS = [
    "Event library is SYNTHETIC: every non-financial entity as a single-node shock plus circular footprints around every located "
    "entity and region centroid, per hazard and radius; footprints reaching nothing with vulnerability >= the threshold are dropped.",
    "All events use the same reference intensity index and reference durations (flood 21 d, heat 14 d, drought 120 d); no return "
    "periods or probabilities are represented, so events are ranked by consequence, not likelihood.",
    "Near-duplicate events (same hazard, directly-hit entity sets with Jaccard >= 0.6) are collapsed into one row with variants.",
    "Portfolio impact = position-weighted share of the holdings' annual value added lost over the disruption window.",
    "Single points of failure and the pair bound come from a structural test: a full 60-day outage of nodes the portfolio does "
    "not own; not climate events.",
    "Stability re-ranks the shortlisted representatives under joint draws of the same shared and local factors as the Monte Carlo analysis.",
]
COMPANY_ASSUMPTION = ("Holdings are companies: a company's disruption is the value-added-weighted average of its business units (segments). "
                      "Its share of value added outside Food & Beverage is NOT modelled and adds no loss; an upper end treats it as hit like "
                      "the modelled part. Company structures and shares are SYNTHETIC.")
COMPANY_LIMITATION = ("Segments are treated as separate businesses. Shocks can also travel inside a firm through shared overheads, capital and "
                      "management attention (Giroud & Mueller 2019; Seetharam 2018, hurricanes), which this view leaves out; the one-node view "
                      "is the opposite extreme.")
LIMITATIONS = [
    "Synthetic network, synthetic facilities, synthetic portfolio weights: the output shows structure, not real exposure.",
    "Magnitudes rest on an uncalibrated damage proxy; read ranks and hidden shares before percentages.",
    "Robust ranking under stated ranges is internal consistency, not validation against observed losses.",
    "Events outside the shortlist are not re-ranked under uncertainty (screening); a test checks that a larger shortlist does not change the top.",
]


def _stability(net, ents, events, reps, w, p, req):
    short = reps[: min(req.shortlist, len(reps))]
    draws = rs.stability_draws(net, ents, [events[i] for i in short], w, p, req.stability_draws, req.seed)
    return short, draws


@dataclass
class Screen:
    net: object
    params: rs.Params
    events: list
    holdings: Holdings
    hm: object              # HoldingMatrix on this network
    weights: dict           # entity id -> weight (each holding spread over its segments); what the optimiser and draws take
    owned: set              # every segment of every held company
    w: np.ndarray
    d0: np.ndarray
    T: np.ndarray
    fin: np.ndarray
    p_loc: np.ndarray
    p_net: np.ndarray
    hid: np.ndarray
    hidden_only: np.ndarray
    reps: list
    variants: dict


FLOOD_MIN_SHARE = 0.0   # any modelled 100-year river flooding within the sampling radius counts as "consistent"


def jrc_check(ds: FnbDataset, events, d0) -> dict[int, bool]:
    """Flood events only: True if any directly hit entity has modelled 100-year river flooding within the sampled radius,
    False if none does; events without a flood hazard or without layer coverage are absent."""
    layer = ds.hazard_layers.get("jrc_flood_rp100")
    if not layer:
        return {}
    shares = layer["entities"]
    ids = [e.id for e in ds.entities]
    out = {}
    for r, ev in enumerate(events):
        if ev.hazard != "flood":
            continue
        hit = [ids[i] for i in np.flatnonzero(d0[r] > 0.01) if ids[i] in shares]
        if hit:
            out[r] = any(shares[i]["flooded_share"] > FLOOD_MIN_SHARE for i in hit)
    return out


def screen(ds: FnbDataset, req: FinderRequest) -> Screen:
    """Deterministic pass over the whole library: scores, ranking, collapsed representatives."""
    ents, rels = ds.entities, ds.relations
    holdings = build_holdings(ds, req.weights, req.holding_view)
    net = compile_network(ents, rels)
    hm = holdings.compile(net.idx, net.n)
    p = rs.Params(max_depth=req.max_depth)
    events = build_library(ents, tuple(req.hazards), req.intensity, tuple(req.radii_km), req.min_vulnerability)
    w = hm.w
    d0 = rs.direct_matrix(ents, events)
    T = rs.event_T(events)
    fin = rs.run_events(net, d0, T, p)
    p_loc, p_net, hid = rs.score(d0, fin, T, w)
    order = np.argsort(-p_net, kind="stable")
    order = order[p_net[order] > 1e-9]
    hidden_only = (p_loc <= 1e-12) & (p_net > 1e-9)
    reps, variants = rs.collapse(order, events, d0)
    flood = jrc_check(ds, events, d0)
    if req.flood_check == "drop":
        keep = lambda r: flood.get(r) != False  # noqa: E712,E731
        reps = [r for r in reps if keep(r)]
    return Screen(net, p, events, holdings, hm, holdings.entity_weights(), holdings.owned, w, d0, T, fin, p_loc, p_net, hid, hidden_only,
                  reps, variants)


def _ranked(events, d0, p_loc: np.ndarray, p_net: np.ndarray) -> tuple[list[int], list[int]]:
    """Distinct representatives and the hidden-only ones, for one way of scoring the library."""
    order = np.argsort(-p_net, kind="stable")
    order = order[p_net[order] > 1e-9]
    reps, _ = rs.collapse(order, events, d0)
    return reps, [r for r in reps if p_loc[r] <= 1e-12]


def structure_comparison(ds: FnbDataset, req: FinderRequest, sc: Screen) -> dict | None:
    """The same event library scored four ways: held units as separate holdings (v0.3), companies segment-weighted (this
    view), companies with their non-F&B businesses hit like the modelled part, and every company as one node."""
    if sc.holdings.view != "company":
        return None
    pf = np.minimum(1.0, sc.T / 365.0)
    hm, W = sc.hm, sc.hm.W
    views: list[tuple[str, str, int, np.ndarray, np.ndarray]] = []
    try:
        bu = build_holdings(ds, req.weights, "business_unit")
        pl, pn, _ = rs.score(sc.d0, sc.fin, sc.T, bu.compile(sc.net.idx, sc.net.n).w)
        views.append(("business_unit", "Each held business unit as its own holding (v0.3)", len(bu.holdings), pl, pn))
    except ValueError:              # weights given as company ids have no business-unit equivalent
        bu = None
    views.append(("company", "Companies, segment-weighted (this view)", len(sc.holdings.holdings), sc.p_loc, sc.p_net))
    views.append(("company_if_other_hit", "Companies, non-F&B businesses hit like the modelled part (upper end)", len(sc.holdings.holdings),
                  (hm.if_other_hit(sc.d0) @ W) * pf, (hm.if_other_hit(sc.fin) @ W) * pf))
    views.append(("company_one_node", "Each company as one node (what a company-level supply graph implies)", len(sc.holdings.holdings),
                  (hm.one_node(sc.d0) @ W) * pf, (hm.one_node(sc.fin) @ W) * pf))
    rows, ranked = [], {}
    for key, label, n_h, pl, pn in views:
        reps, ho = _ranked(sc.events, sc.d0, pl, pn)
        ranked[key] = (reps, ho, pl)
        top = ho[0] if ho else None
        rows.append(dict(view=key, label=label, n_holdings=n_h, n_distinct_events=len(reps), n_hidden_only=len(ho),
                         top_hidden_only=None if top is None else dict(id=sc.events[top].id, label=sc.events[top].label, impact=round(float(pn[top]), 7)),
                         mean_top10_impact=round(float(np.mean(pn[reps[:10]])), 7) if reps else 0.0))
    own_site = None
    if "business_unit" in ranked:
        own_site = int(sum(1 for r in ranked["business_unit"][1] if sc.p_loc[r] > 1e-12))
    multi = [h for h in sc.holdings.holdings if h.multi_segment]
    return dict(views=rows, n_multi_segment=len(multi), multi_segment_holdings=[h.name for h in multi],
                hidden_only_events_on_own_sites=own_site,
                note=("Same events, same engine; only the definition of a holding changes. 'Own sites' counts events that are hidden-only when "
                      "each held unit is its own holding but hit a business unit the company owns once the whole company is counted. "
                      "All structures are synthetic; none of these views is validated."))


def run_finder(ds: FnbDataset, req: FinderRequest) -> FinderResult:
    t0 = time.perf_counter()
    ents = ds.entities
    sc = screen(ds, req)
    net, p, events, w, hm = sc.net, sc.params, sc.events, sc.w, sc.hm
    d0, T, fin, p_loc, p_net, hid, hidden_only = sc.d0, sc.T, sc.fin, sc.p_loc, sc.p_net, sc.hid, sc.hidden_only
    hs_list, W, company = sc.holdings.holdings, hm.W, sc.holdings.view == "company"
    hd0, hfin = hm.segment_weighted(d0), hm.segment_weighted(fin)          # (S,H) company-level disruption
    pf = np.minimum(1.0, T / 365.0)
    up_net = (hm.if_other_hit(fin) @ W) * pf if company else None
    one_net = (hm.one_node(fin) @ W) * pf if company else None
    reps, variants = sc.reps, sc.variants
    hid_reps = [r for r in reps if hidden_only[r]]
    flood = jrc_check(ds, events, d0)
    layer = ds.hazard_layers.get("jrc_flood_rp100")
    top_flood = [r for r in reps if events[r].hazard == "flood"][:20]
    hazard_layer = None if not layer else dict(
        name=layer["layer"], citation=layer["citation"], licence=layer["licence"], source=layer["source"], retrieved=layer["retrieved"],
        mode=req.flood_check, flood_events_checked=len(flood), flood_events_without_modelled_flooding=int(sum(1 for v in flood.values() if not v)),
        top20_flood_events_consistent=int(sum(1 for r in top_flood if flood.get(r))), top20_flood_events=len(top_flood),
        entities_total=len(layer["entities"]), entities_with_any_flooding=int(sum(1 for v in layer["entities"].values() if v["flooded_share"] > FLOOD_MIN_SHARE)),
        entities_window_clipped=int(sum(1 for v in layer["entities"].values() if v.get("window_coverage", 1.0) < 0.9)),
        caveat="Lenient filter: most entities have some modelled river flooding within 5 km, so passing it says little. " +"Proxy plausibility check, not validation: river flooding only (no coastal or surface-water flooding), sampled around "
               "SYNTHETIC approximate coordinates; a zero is not evidence that a site is safe.")

    stab_all = stab_hid = None
    stability_meta = None
    if req.stability_draws > 0 and reps:
        short, draws = _stability(net, ents, events, reps, w, p, req)
        st = rs.rank_stats(draws)
        stab_all = {short[j]: (float(st["p_top"][j]), float(st["median_rank"][j]), [float(st["q25"][j]), float(st["q75"][j])])
                    for j in range(len(short))}
        cols = [j for j, r in enumerate(short) if hidden_only[r]]
        if cols:
            sh = rs.rank_stats(draws[:, cols])
            stab_hid = {short[c]: (float(sh["p_top"][k]), float(sh["median_rank"][k]), [float(sh["q25"][k]), float(sh["q75"][k])])
                        for k, c in enumerate(cols)}
        stability_meta = dict(n_draws=req.stability_draws, seed=req.seed, shortlist=len(short), kendall_tau_top20=st["kendall_tau_top20"],
                              kendall_tau_top20_hidden_only=sh["kendall_tau_top20"] if cols else None,
                              note="Ranks among the shortlisted representatives; hidden-only ranks among hidden-only representatives.")

    def holding_row(h: int, direct: float, network: float, dvec: np.ndarray, fvec: np.ndarray) -> dict:
        """One holding's impact; dvec/fvec are the per-entity direct and final disruption of the event (or outage)."""
        hd = hs_list[h]
        row = dict(entity_id=hd.id, name=hd.name, weight=round(float(W[h]), 6), direct_disruption=round(float(direct), 4),
                   network_disruption=round(float(network), 4), kind=hd.kind, primary_entity_id=hd.primary_entity_id)
        if hd.multi_segment:
            cols = hm.cols[h]
            row.update(other_businesses_share=hd.other_share,
                       network_disruption_if_other_hit=round(float(network / max(1.0 - hd.other_share, 1e-12)), 4),
                       network_disruption_one_node=round(float(1.0 - np.prod(1.0 - fvec[cols])), 4),
                       segments=[dict(entity_id=sg.entity_id, name=sg.name, segment=sg.label, share=round(sg.share, 4),
                                      direct_disruption=round(float(dvec[c]), 4), network_disruption=round(float(fvec[c]), 4))
                                 for sg, c in zip(hd.segments, cols)])
        return row

    def holding_rows(r: int, k: int = 5):
        order = sorted(range(len(hs_list)), key=lambda h: -hfin[r, h] * W[h])
        return [holding_row(h, hd0[r, h], hfin[r, h], d0[r], fin[r]) for h in order[:k] if hfin[r, h] > 1e-4]

    def event_row(rank: int, r: int, stab: dict | None):
        ev = events[r]
        pt = stab.get(r) if stab else None
        return dict(
            rank=rank, id=ev.id, kind=ev.kind, hazard=ev.hazard, label=ev.label, origin_id=ev.origin_id, country=ev.country,
            region=ev.region, portfolio_network_impact=round(float(p_net[r]), 7), portfolio_location_impact=round(float(p_loc[r]), 7),
            hidden_share=round(float(hid[r]), 4), hidden_only=bool(hidden_only[r]), variants=len(variants.get(r, [])),
            holdings_affected=int((hfin[r] > 0.01).sum()), entities_hit_directly=int((d0[r] > 0.01).sum()),
            top_holdings=holding_rows(r), p_top5=None if pt is None else round(pt[0], 4), median_rank=None if pt is None else pt[1],
            rank_iqr=None if pt is None else pt[2], fragile=None if pt is None else bool(rank <= rs.TOP and pt[0] < 0.5),
            hazard_component=ev.hazard_component(),
            jrc_flood_check=None if r not in flood else ("river flooding modelled nearby" if flood[r] else "no river flooding modelled nearby"),
            portfolio_network_impact_if_other_hit=round(float(up_net[r]), 7) if company else None,
            portfolio_network_impact_one_node=round(float(one_net[r]), 7) if company else None)

    # holding x upstream-node matrix: each node the portfolio's companies do NOT own, at its worst single-node climate event
    owned = sc.owned
    node_rows: dict[str, int] = {}
    for r, ev in enumerate(events):
        if ev.kind == "node" and ev.origin_id not in owned and (ev.origin_id not in node_rows or p_net[r] > p_net[node_rows[ev.origin_id]]):
            node_rows[ev.origin_id] = r
    mat = []
    for nid, r in node_rows.items():
        vals = {hs_list[h].id: float(hfin[r, h] * W[h] * min(1.0, T[r] / 365)) for h in range(len(hs_list))}
        tot_r = sum(vals.values())
        if tot_r <= 1e-9:
            continue
        mat.append(dict(entity_id=nid, name=ds.by_id[nid].name, entity_type=ds.by_id[nid].entity_type, worst_event_id=events[r].id,
                        total=round(tot_r, 7), holdings_reached=int((hfin[r] > 0.01).sum()),
                        values={k: round(v, 7) for k, v in vals.items()}))
    mat.sort(key=lambda x: -x["total"])

    # structural single points of failure: full outage of one node the portfolio does not own
    upstream = [i for i, e in enumerate(ents) if e.entity_type != "financial" and e.id not in owned]
    single = rs.outage_matrix(net, upstream, p)
    hsingle = hm.segment_weighted(single)
    no_direct = np.zeros(net.n)
    spofs = []
    for j, u in enumerate(upstream):
        hit = [h for h in range(len(hs_list)) if hsingle[j, h] >= rs.SPOF_THRESHOLD]
        if hit:
            spofs.append(dict(entity_id=net.node_ids[u], name=ents[u].name, entity_type=ents[u].entity_type, is_holding=False,
                              holdings=[holding_row(h, 0.0, hsingle[j, h], no_direct, single[j]) for h in sorted(hit, key=lambda h: -hsingle[j, h])]))
    spofs.sort(key=lambda s: (-len(s["holdings"]), -sum(h["network_disruption"] * h["weight"] for h in s["holdings"])))

    bound = None
    if req.include_pairs and len(upstream) >= 2:
        wp = rs.worst_pairs(net, upstream, w, p, single)
        nm = lambda pr: [ents[upstream[pr[0]]].name, ents[upstream[pr[1]]].name]  # noqa: E731
        bound = dict(n_pairs=wp["n_pairs"], method="exhaustive search over all pairs of nodes the portfolio does not own (full 60-day outage of both)",
                     top=[dict(entities=nm(pr), impact=round(v, 7)) for pr, v in wp["exhaustive"]],
                     greedy=dict(entities=nm(wp["greedy"][0]), impact=round(wp["greedy"][1], 7)), greedy_matches=wp["greedy_matches"],
                     note="Structural bound, not a climate event: what simultaneous failure of two upstream nodes could do to this portfolio.")

    curve = [dict(threshold=t, events=int(sum(1 for r in reps if hid[r] >= t))) for t in (0.25, 0.5, 0.75, 0.9, 0.99)]
    return FinderResult.model_validate(dict(
        n_events=len(events), n_node_events=sum(e.kind == "node" for e in events),
        n_footprint_events=sum(e.kind == "footprint" for e in events), n_distinct_events=len(reps), n_hidden_only=len(hid_reps),
        runtime_seconds=round(time.perf_counter() - t0, 3),
        events=[event_row(k, r, stab_all) for k, r in enumerate(reps[: req.top_k], 1)],
        hidden_only_events=[event_row(k, r, stab_hid) for k, r in enumerate(hid_reps[: req.top_k], 1)],
        hidden_share_curve=curve,
        holdings=[holding_meta(ds, h) for h in hs_list],
        matrix=mat[:15], single_points_of_failure=spofs[:15], structural_bound=bound, stability=stability_meta, hazard_layer=hazard_layer,
        holding_view=sc.holdings.view, structure_comparison=structure_comparison(ds, req, sc),
        parameters=req.model_dump(exclude={"weights"}) | {"portfolio": ds.portfolio.get("name"), "weighting": ds.portfolio.get("weighting")},
        units={"portfolio_impact": "position-weighted share of annual value added lost (0-1)", "hidden_share": "0-1",
               "p_top5": "share of uncertainty draws", "disruption": "fraction of normal output, 0-1",
               "holding_disruption": "company level: value-added-weighted average of its business units' disruption (0-1)"},
        assumptions=ASSUMPTIONS + ([COMPANY_ASSUMPTION] if company else []), limitations=LIMITATIONS + ([COMPANY_LIMITATION] if company else [])))
