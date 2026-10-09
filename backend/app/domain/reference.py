"""Loader for the supplied Sectivia reference files. Used ONLY to exercise generic graph tooling and to audit coverage;
Sectivia contains no Food & Beverage companies and its companies are never relabelled as food businesses."""
from __future__ import annotations

import csv
from pathlib import Path

import networkx as nx


def load_sectivia_graph(directory: Path) -> nx.DiGraph:
    g = nx.DiGraph(attribution="Supply-chain data: Sectivia (https://sectivia.com), CC BY 4.0")
    with (directory / "sectivia-companies.csv").open() as f:
        for row in csv.DictReader(f):
            g.add_node(row["id"], name=row["name"], sector=row["sector"], segment=row["segment"], country=row["country"])
    with (directory / "sectivia-relations.csv").open() as f:
        for row in csv.DictReader(f):
            g.add_edge(row["supplier_id"], row["customer_id"], weight=None, status="reference")
    return g
