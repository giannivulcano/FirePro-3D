"""P1 DD10 / M8: both right-click menus start Copy's base-point pick (D4) and
offer Cut beside it.

Real path: a shown Model_View over a real block_editor Model_Space; the menus
come from the production builders (Model_Space._build_entity_context_menu,
Model_View._build_plan_context_menu); actions are triggered, the base point is
a real click; observables are the scene mode, the clipboard payload's base
and the geometry.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests._modify_tools_helpers import add_primitive, ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view


_MENUS = []      # the entity QMenu is parentless: keep it alive past _actions


def _actions(which, view, scene, item):
    if which == "entity":
        menu = scene._build_entity_context_menu(item)
    else:
        menu = view._build_plan_context_menu(scene, [item], "select")
    _MENUS[:] = [menu]
    return {a.text(): a for a in menu.actions()}


@pytest.mark.parametrize("which", ["entity", "view"])
def test_context_menu_copy_starts_the_base_point_pick(qapp, which):
    view, scene = make_view(scale=1.0)
    ignore_os_mouse(view)
    try:
        item, attr = add_primitive(scene, "line")              # (0,0)-(100,0)
        QApplication.clipboard().setText("sentinel")
        _actions(which, view, scene, item)["Copy"].trigger()
        assert scene.mode == "copy_base"                        # [RED]
        assert scene.clipboard_payload() is None                # nothing copied yet
        click(view, QPointF(100, 0))                            # base on the endpoint
        data = scene.clipboard_payload()
        assert data is not None and len(data["items"]) == 1
        assert data["base"] == pytest.approx([100.0, 0.0], abs=1e-6)
        assert getattr(scene, attr) == [item]                   # Copy keeps it
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("which", ["entity", "view"])
def test_context_menu_cut_is_offered_and_cuts_after_the_base_pick(qapp, which):
    view, scene = make_view(scale=1.0)
    ignore_os_mouse(view)
    try:
        item, attr = add_primitive(scene, "line")
        p0 = scene._undo_pos
        acts = _actions(which, view, scene, item)
        assert "Cut" in acts                                    # [RED]
        assert list(acts).index("Cut") == list(acts).index("Copy") + 1
        acts["Cut"].trigger()
        assert scene.mode == "copy_base"
        assert getattr(scene, attr) == [item]                   # not yet removed
        click(view, QPointF(100, 0))
        assert getattr(scene, attr) == []
        assert scene.clipboard_payload()["base"] == pytest.approx([100.0, 0.0], abs=1e-6)
        assert scene._undo_pos == p0 + 1
        scene.undo()
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)
