from pathlib import Path

import pytest

from app.config import get_settings
from app.domain.dataset import FnbDataset, validate_graph_data
from app.domain.reference import load_sectivia_graph
from conftest import make_entity, make_rel


@pytest.fixture(scope="module")
def ds():
    return FnbDataset.load(get_settings().data_dir)


def test_dataset_loads_and_is_valid(ds):
    assert ds.validation.ok, ds.validation.errors
    assert 60 <= len(ds.entities) <= 120 and len(ds.relations) >= 100
    assert all(e.synthetic for e in ds.entities)
    assert all(r.status in ("synthetic", "modelled") for r in ds.relations)


def test_dataset_is_food_and_beverage_only(ds):
    assert not {"ai", "medicin", "forsvar", "finans"} & {e.food_category for e in ds.entities}


def test_multi_hop_paths_exist(ds):
    import networkx as nx
    g = ds.graph()
    depth = nx.single_source_shortest_path_length(g, "fert_br")
    assert max(depth.values()) >= 4 and "retail_br" in depth


def test_cycle_is_flagged_not_rejected(ds):
    assert ds.validation.cycles and not ds.validation.errors


def test_validation_catches_bad_data():
    a, b = make_entity("a"), make_entity("b")
    assert "unknown target" in " ".join(validate_graph_data([a, b], [make_rel("a", "zz")]).errors)
    assert "self-loop" in " ".join(validate_graph_data([a, b], [make_rel("a", "a")]).errors)
    dup = validate_graph_data([a, b], [make_rel("a", "b"), make_rel("a", "b")])
    assert any("duplicate edge" in e for e in dup.errors)
    over = validate_graph_data([a, b, make_entity("c")], [make_rel("a", "c", dep=0.7), make_rel("b", "c", dep=0.6)])
    assert any("impossible dependency" in e for e in over.errors)
    assert validate_graph_data([a, a], []).errors
    assert validate_graph_data([a, b], [make_rel("a", "b")]).ok


def test_isolated_nodes_warned():
    rep = validate_graph_data([make_entity("a"), make_entity("b"), make_entity("lonely")], [make_rel("a", "b")])
    assert rep.isolated_nodes == ["lonely"]


def test_sectivia_reference_loads_with_generic_tooling(ds):
    g = load_sectivia_graph(get_settings().data_dir / "reference" / "sectivia")
    assert g.number_of_nodes() == 215 and g.number_of_edges() == 350
    assert ds.reference_audit["food_and_beverage_segments_found"] == []
