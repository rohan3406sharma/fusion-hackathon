"""Budget-constrained resilience optimiser.

Decision variables  x_j in {0,1} for candidate interventions j (each a type, a target entity and a magnitude).
Constraint          sum_j c_j x_j <= B, with c_j the annualised cost (SYNTHETIC placeholders, models/mitigation.py).
                    Capacity limits on alternative sourcing are enforced inside apply_interventions (shared spare capacity).
Objective           minimise R(x) = mean portfolio impact of the `tail` worst events in the event set after the plan
                    (a CVaR-like tail over the finder's shortlisted events; events are equally weighted because the
                    library carries no probabilities).
Method              R(x) is evaluated by simulation and is not linear or provably submodular, so: greedy by marginal
                    reduction per unit cost, then 1-swap local search; on <= 10 candidates an exhaustive search reports the
                    optimality gap. Results hold only under the stated costs, events and model.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from ..schemas.domain import Entity, Relation
from ..schemas.mitigation import Intervention
from . import reverse_stress as rs
from .events import Event
from .mitigation import apply_interventions, cost_of
from .propagation import compile_network


@dataclass
class Problem:
    entities: list[Entity]
    relations: list[Relation]
    events: list[Event]
    weights: dict[str, float]
    params: rs.Params
    tail: int
    candidates: list[Intervention]
    costs: np.ndarray
    d0_ref: np.ndarray
    idx: dict[str, int]
    cache: dict = field(default_factory=dict)

    def evaluate(self, plan: tuple[int, ...]) -> float:
        key = tuple(sorted(plan))
        if key not in self.cache:
            self.cache[key] = self._tail(key)[0]
        return self.cache[key]

    def _tail(self, key: tuple[int, ...]):
        ivs = [self.candidates[i] for i in key]
        ents, rels, notes = apply_interventions(self.entities, self.relations, ivs, self.d0_ref, self.idx) if ivs else (self.entities, self.relations, [])
        net = compile_network(ents, rels)
        d0 = rs.direct_matrix(ents, self.events)
        T = rs.event_T(self.events)
        fin = rs.run_events(net, d0, T, self.params)
        p_net = rs.score(d0, fin, T, rs.weight_vector(net, self.weights))[1]
        return float(np.sort(p_net)[::-1][: self.tail].mean()), p_net, notes, ents, rels, net


def make_problem(entities, relations, events, weights, params, tail, candidates) -> Problem:
    idx = {e.id: i for i, e in enumerate(entities)}
    d0_ref = rs.direct_matrix(entities, events).max(axis=0)       # an entity hit in any listed event cannot lend capacity
    costs = []
    for iv in candidates:
        _, rels2, notes = apply_interventions(entities, relations, [iv], d0_ref, idx)
        costs.append(cost_of(iv, entities, rels2, notes)["annualised_cost_musd"])
    return Problem(entities, relations, events, weights, params, tail, candidates, np.array(costs, dtype=float), d0_ref, idx)


def greedy(pb: Problem, budget: float, costs: np.ndarray | None = None) -> tuple[list[int], list[dict]]:
    costs = pb.costs if costs is None else costs
    chosen: list[int] = []
    spent, cur = 0.0, pb.evaluate(())
    path = []
    while True:
        best = None
        for j in range(len(pb.candidates)):
            if j in chosen or spent + costs[j] > budget + 1e-12:
                continue
            val = pb.evaluate(tuple(chosen + [j]))
            gain = cur - val
            if gain <= 1e-12:
                continue
            ratio = gain / max(costs[j], 1e-6)
            if best is None or ratio > best[0]:
                best = (ratio, j, val, gain)
        if best is None:
            break
        _, j, val, gain = best
        chosen.append(j)
        spent += costs[j]
        cur = val
        path.append(dict(candidate=j, cumulative_cost=round(spent, 4), objective=val, marginal_gain=gain))
    return chosen, path


def local_search(pb: Problem, plan: list[int], budget: float, rounds: int = 3) -> list[int]:
    plan = list(plan)
    for _ in range(rounds):
        cur = pb.evaluate(tuple(plan))
        best = None
        others = [j for j in range(len(pb.candidates)) if j not in plan]
        moves = [(i, j) for i in plan for j in others] + [(None, j) for j in others]
        for i, j in moves:
            new = [x for x in plan if x != i] + [j]
            if pb.costs[new].sum() > budget + 1e-12:
                continue
            val = pb.evaluate(tuple(new))
            if val < cur - 1e-12 and (best is None or val < best[0]):
                best = (val, new)
        if best is None:
            break
        plan = best[1]
    return plan


def exhaustive(pb: Problem, budget: float, pool: list[int]) -> dict:
    best_val, best_set, n = pb.evaluate(()), (), 0
    for r in range(1, len(pool) + 1):
        for comb in itertools.combinations(pool, r):
            if pb.costs[list(comb)].sum() > budget + 1e-12:
                continue
            n += 1
            v = pb.evaluate(comb)
            if v < best_val - 1e-12:
                best_val, best_set = v, comb
    return dict(n_feasible_plans=n, best_objective=best_val, best_plan=list(best_set))
