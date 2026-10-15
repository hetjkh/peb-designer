"""Core StructuralModel behaviour."""

from __future__ import annotations

import pytest

from app.core.models import Member, Node, StructuralModel, Support, SupportType


def test_add_node_and_member():
    model = StructuralModel()
    model.add_node(Node(1, 0, 0, 0))
    model.add_node(Node(2, 0, 5, 0))
    model.add_member(Member(1, 1, 2, member_type="column", section="ISMB 300", material="E350"))
    assert len(model.nodes) == 2
    assert len(model.members) == 1
    assert model.summary().startswith("Nodes: 2")


def test_duplicate_node_rejected():
    model = StructuralModel()
    model.add_node(Node(1, 0, 0, 0))
    with pytest.raises(ValueError, match="Duplicate node"):
        model.add_node(Node(1, 1, 1, 1))


def test_member_requires_existing_nodes():
    model = StructuralModel()
    model.add_node(Node(1, 0, 0, 0))
    with pytest.raises(ValueError, match="Unknown"):
        model.add_member(Member(1, 1, 99))


def test_support_and_replace_member():
    model = StructuralModel()
    model.add_node(Node(1, 0, 0, 0))
    model.add_node(Node(2, 0, 5, 0))
    model.add_member(Member(1, 1, 2, section="ISMB 200", material="E250"))
    model.set_support(Support(1, SupportType.FIXED, rz=True))
    assert model.supports[1].support_type == SupportType.FIXED
    model.replace_member(Member(1, 1, 2, section="ISMB 400", material="E350", member_type="column"))
    assert model.members[1].section == "ISMB 400"


def test_clear_resets_all():
    model = StructuralModel()
    model.add_node(Node(1, 0, 0, 0))
    model.metadata["x"] = 1
    model.clear()
    assert not model.nodes
    assert not model.metadata
