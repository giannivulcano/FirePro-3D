"""ModifyToolsController.can_start -- the Edit-button predicate (editor-build design §1, B2).

can_start(tool, items) must agree with start(tool) on every refusal start() makes
before entering a mode, and must post no status / enter no mode itself.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.modify_tools_controller import ModifyToolsController
from tests._snap_polish_helpers import close_view, make_view

TOOLS = ("copy", "cut", "paste", "duplicate", "move", "rotate", "scale",
         "flip", "mirror", "offset", "array")


@pytest.fixture
def plan(qapp):
    view, scene = make_view(role="plan")
    yield scene
    close_view(view, scene)


def _wall(scene):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    scene.addItem(w)
    return w


def _line(scene):
    from firepro3d.geometry_2d import LineItem
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(ln)
    return ln


def test_wall_selection_disables_scale_flip_mirror_offset(plan):
    """2026-10-26 ruling: Array stays live on walls (it copies them through paste)."""
    w = _wall(plan)
    w.setSelected(True)
    ctl = plan._modify_ctl
    sel = plan.selectedItems()
    live = {t for t in TOOLS if t != "paste" and ctl.can_start(t, sel)}
    assert live == {"copy", "cut", "duplicate", "move", "rotate", "array"}, live


def test_empty_selection_leaves_only_offset_live(plan):
    ctl = plan._modify_ctl
    live = {t for t in TOOLS if t != "paste" and ctl.can_start(t, [])}
    assert live == {"offset"}, live


def test_no_view_turns_every_tool_off(plan):
    w = _wall(plan)
    w.setSelected(True)
    plan.view_available = False
    try:
        assert not any(plan._modify_ctl.can_start(t, plan.selectedItems())
                       for t in TOOLS)
    finally:
        plan.view_available = True


def test_paste_follows_the_clipboard_payload(plan, monkeypatch):
    ctl = plan._modify_ctl
    monkeypatch.setattr(type(plan), "clipboard_payload", lambda self: None)
    assert not ctl.can_start("paste", [])
    monkeypatch.setattr(type(plan), "clipboard_payload",
                        lambda self: {"items": []})
    assert not ctl.can_start("paste", [])
    monkeypatch.setattr(type(plan), "clipboard_payload",
                        lambda self: {"items": [{"type": "line"}]})
    assert ctl.can_start("paste", [])


def test_can_start_posts_no_status_and_enters_no_mode(plan):
    msgs = []
    plan._show_status = lambda m, *a: msgs.append(m)
    w = _wall(plan)
    w.setSelected(True)
    for t in TOOLS:
        plan._modify_ctl.can_start(t, plan.selectedItems())
    assert msgs == []
    assert plan.mode in (None, "select")


@pytest.mark.parametrize("make", ["wall", "line", "wall+line", "none"])
@pytest.mark.parametrize("tool", [t for t in TOOLS if t != "paste"])
def test_can_start_agrees_with_start(plan, make, tool):
    """Parity: start(tool) enters a mode exactly when can_start says it may."""
    items = []
    if "wall" in make:
        items.append(_wall(plan))
    if "line" in make:
        items.append(_line(plan))
    for it in items:
        it.setSelected(True)
    ctl = plan._modify_ctl
    expected = ctl.can_start(tool, plan.selectedItems())
    plan._show_status = lambda *a: None
    try:
        entered = ctl.start(tool)
        if tool == "offset" and make != "none":
            # start("offset") always enters pick mode (D3 exemption); the
            # button predicate is stricter on a non-empty selection (B2).
            assert entered
        else:
            assert entered == expected, (tool, make, entered, expected)
    finally:
        plan.set_mode("select")
