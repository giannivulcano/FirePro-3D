"""tests/test_reference_line_legacy.py -- reference lines after the retirement
of ``ReferenceLineItem`` (reference-geometry design RG1-RG3, RG11-RG13).

A reference line is now a ``LineItem`` with ``reference=True`` living in
``_draw_lines``; legacy ``reference_line`` records still load as one. Covers
serialization, delete routing, undo capture/restore, the paper / block
exclusion of the non-printed flag and the "Reference Geometry" Display
Manager category. Placement (Space toggle) is covered with Task 5's tests.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem


def _ref(p1, p2, printed=False, color="#ffffff"):
    ln = LineItem(p1, p2, color)
    ln.reference, ln.printed = True, bool(printed)
    return ln


def test_reference_line_is_a_flagged_lineitem():
    # Snap participation + base editing come for free: it IS a LineItem.
    rl = _ref(QPointF(0, 0), QPointF(10, 0))
    assert type(rl) is LineItem and rl.reference is True


def test_reference_line_defaults_not_printed():
    rl = _ref(QPointF(0, 0), QPointF(10, 0))
    assert rl.printed is False


def test_reference_line_serialization_roundtrip():
    rl = _ref(QPointF(1, 2), QPointF(30, 40), printed=True, color="#abcdef")
    d = rl.to_dict()
    assert d["type"] == "draw_line"                  # RG2: one schema
    assert d["reference"] is True and d["printed"] is True
    back = LineItem.from_dict(d)
    assert back.reference is True and back.printed is True
    assert (back._pt1.x(), back._pt1.y()) == (1, 2)
    assert (back._pt2.x(), back._pt2.y()) == (30, 40)
    assert back.style["colour"] == "#abcdef"
    # A legacy record without the flag loads not-printed (RG3).
    old = LineItem.from_dict({"type": "reference_line", "pt1": [0, 0], "pt2": [1, 1]})
    assert old.reference is True and old.printed is False


def test_delete_routes_to_draw_lines(shown_model_view):
    view, scene = shown_model_view
    rl = _ref(QPointF(0, 0), QPointF(10, 0))
    scene.addItem(rl); scene._draw_lines.append(rl)
    assert scene._remove_item_from_lists(rl) is True
    assert rl not in scene._draw_lines


def test_undo_restore_preserves_reference_line(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"           # containment C1: loose authoring
    rl = _ref(QPointF(0, 0), QPointF(600, 0), printed=True)
    scene.addItem(rl); scene._draw_lines.append(rl)
    state = scene._capture_network()
    assert "reference_lines" not in state        # one list (RG1)
    scene._restore_network(state)
    refs = [ln for ln in scene._draw_lines if ln.reference]
    assert len(refs) == 1 and refs[0] is not rl
    assert refs[0].printed is True and refs[0]._uid == rl._uid


def test_legacy_undo_snapshot_key_restores_flagged_lines(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    state = scene._capture_network()
    state["reference_lines"] = [{"type": "reference_line", "pt1": [0, 0],
                                 "pt2": [10, 0], "color": "#888888",
                                 "lineweight": 1.0, "printed": True}]
    scene._restore_network(state)
    refs = [ln for ln in scene._draw_lines if ln.reference]
    assert len(refs) == 1 and type(refs[0]) is LineItem and refs[0].printed is True


def test_paper_export_excludes_non_printed_includes_printed(shown_model_view):
    from PyQt6.QtCore import QRectF
    from firepro3d import paper_display
    view, scene = shown_model_view
    off = _ref(QPointF(0, 0), QPointF(100, 0), printed=False)
    on = _ref(QPointF(0, 50), QPointF(100, 50), printed=True)
    plain = LineItem(QPointF(0, 100), QPointF(100, 100))     # printed attr False
    for it in (off, on, plain):
        scene.addItem(it); scene._draw_lines.append(it)
    from firepro3d.text_item import TextAnnotationData, TextItem
    text = TextItem(TextAnnotationData(text="T", x=0.0, y=200.0, height_mm=20.0))
    assert text.printed is False                             # carries the attr too
    scene.addItem(text); scene._texts.append(text)
    saved = paper_display.apply_paper_overrides(scene, QRectF(-1000, -1000, 3000, 3000))
    assert off.isVisible() is False, "non-printing reference line must be excluded from plots"
    assert on.isVisible() is True, "printed reference line must plot"
    assert plain.isVisible() is True, "a normal line always plots"
    assert text.isVisible() is True, "text always plots (no reference form, AC10)"
    paper_display.restore_model_display(saved)
    assert off.isVisible() is True, "visibility must be restored after the render pass"


def test_block_definition_saves_all_renders_only_printed(qapp):
    # D23 (parametric-constraint-system.md) retired "non-printed is dropped from
    # the block": every reference line is saved as scaffolding; compile renders
    # only the printed one.
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.model_space import Model_Space
    from firepro3d.block_editor import BlockEditorManager
    tabs, proj = QTabWidget(), Model_Space()   # kept alive for commit_block
    w = BlockEditorManager(tabs, proj).open_new()
    s = w.editor_scene
    off = _ref(QPointF(0, 0), QPointF(100, 0), printed=False)
    on = _ref(QPointF(0, 50), QPointF(100, 50), printed=True)
    for it in (off, on):
        s.addItem(it); s._draw_lines.append(it)
    prims = w.gather_primitives()
    assert on in prims, "printed reference line must be in the block definition"
    assert off in prims, "non-printing reference line is saved as scaffolding (D23)"
    defn = w.commit_block("RL", "L", "S")
    assert len(defn.primitives) == 2
    assert len(defn.render_ops()) == 1, "only the printed reference line renders"


def test_reference_geometry_display_category(shown_model_view):
    from firepro3d import display_manager
    view, scene = shown_model_view
    assert "Reference Geometry" in display_manager._CATEGORY_MAP
    rl = _ref(QPointF(0, 0), QPointF(10, 0))
    scene.addItem(rl); scene._draw_lines.append(rl)
    members = display_manager._items_for_category_static(scene, "Reference Geometry")
    assert rl in members
    # It must NOT double up in the 2D Geometry category.
    assert rl not in display_manager._items_for_category_static(scene, "2D Geometry")


@pytest.mark.xfail(strict=True, reason="Printed panel row lands with plan Task 6 (RG10)")
def test_printed_property_uses_toggle_field():
    rl = _ref(QPointF(0, 0), QPointF(10, 0))
    props = rl.get_properties()
    assert props["Printed"]["type"] == "toggle"
    assert props["Printed"]["value"] is False
    rl.set_property("Printed", True)
    assert rl.printed is True
