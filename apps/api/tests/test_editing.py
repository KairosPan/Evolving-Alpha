import pytest
from apps.api.editing import (validate_path, first_dirty_node, apply_patch,
                              EDITABLE_PREFIXES, NodeNotEditable)


def test_whitelist_accepts_pattern_hits():
    validate_path("pattern_hits")


def test_whitelist_rejects_random_field():
    with pytest.raises(NodeNotEditable):
        validate_path("raw_quotes")


def test_whitelist_accepts_themes_phase():
    validate_path("themes.AI算力.phase")


def test_first_dirty_node_for_themes_phase_is_theme_analyst():
    assert first_dirty_node("themes.AI算力.phase") == "theme_analyst"


def test_first_dirty_node_for_pattern_hits_is_pattern_matcher():
    assert first_dirty_node("pattern_hits") == "pattern_matcher"


def test_first_dirty_node_for_risk_flags_is_risk_guard():
    assert first_dirty_node("risk_flags") == "risk_guard"


def test_first_dirty_node_for_leader_stack_is_leader_tracker():
    assert first_dirty_node("leader_stack") == "leader_tracker"


def test_apply_patch_sets_nested_value():
    state = {"themes": {"AI算力": {"phase": "horizontal"}}}
    out = apply_patch(state, "themes.AI算力.phase", "vertical")
    assert out["themes"]["AI算力"]["phase"] == "vertical"
