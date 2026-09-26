"""New/Open mid-tool: _clear_scene ends the active tool first (seam I-2).

A tool left running across ``_clear_scene`` (the path under both New and
Open) keeps references to deleted items and aborts NATIVELY on the next mouse
event. A regression therefore kills the whole process — run each case in its
own process (``-k``) when bisecting.
"""
import pytest
from PyQt6.QtCore import QPointF

from tests._modify_tools_helpers import add_primitive
from tests._snap_polish_helpers import click, close_view, make_view, move

# tool -> the mode it must be in when New/Open lands (armed mid-gesture).
TOOLS = {"move": "move", "duplicate": "duplicate", "rotate": "rotate",
         "array": "array", "offset": "offset_side"}


@pytest.mark.parametrize("path", ["new", "open"])
@pytest.mark.parametrize("tool", list(TOOLS))
def test_new_or_open_mid_tool_ends_the_tool(qapp, tmp_path, tool, path):
    view, scene = make_view(scale=1.0)
    try:
        fpd = tmp_path / "blank.fpd"
        if path == "open":
            scene.save_to_file(str(fpd))       # a real project file to Open
        add_primitive(scene, "line")
        assert scene._modify_ctl.start(tool)
        if tool != "offset":
            click(view, QPointF(0, 0))         # arm: base / pivot picked
        move(view, QPointF(120, 40))           # ghost live on the old items
        assert scene.mode == TOOLS[tool]
        if path == "new":
            scene._clear_scene()
        else:
            scene.load_from_file(str(fpd))
        assert scene.mode is None
        # Pre-fix, either event aborts the process natively (dead item refs).
        move(view, QPointF(200, 50))
        click(view, QPointF(200, 50))
        move(view, QPointF(250, 80))
        click(view, QPointF(250, 80))
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)
