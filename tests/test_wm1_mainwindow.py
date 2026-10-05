"""WM1 G4/G5 -- real MainWindow + Block Editor: the template shows for every
draw tool, a template pick drives the drawn primitive, the panel stays on the
template after a commit, a selected-item edit doesn't move the current, the
current persists, and no "By Block" UI string remains (linetypes.md WM-10)."""
import pathlib
import re

from PyQt6.QtCore import QPointF

from firepro3d import stroke_style as ss
from firepro3d.geometry_2d import GeometryTemplate, LineItem
from tests.test_constraint_e2e import _click
from tests.test_constraint_pick_ribbon import (  # noqa: F401
    _editors, _plan_index, mw, win_with_editor)

DRAW_MODES = ("draw_line", "draw_rectangle", "draw_circle", "draw_arc",
              "polyline", "polygon", "draw_ellipse", "draw_spline")


def _target(w):
    return w.prop_manager._targets[0] if w.prop_manager._targets else None


def test_every_draw_tool_shows_the_template(win_with_editor, qapp):
    w = win_with_editor
    sc = w._test_editor.editor_scene
    for m in DRAW_MODES:
        sc.set_mode(m); qapp.processEvents()
        t = _target(w)
        assert isinstance(t, GeometryTemplate), m
        assert t._scene_ref is sc, m                   # the editor's, not the plan's
        sc.set_mode("select"); qapp.processEvents()


def test_template_pick_drives_drawn_line_and_panel_stays(win_with_editor, qapp):
    w = win_with_editor
    ed = w._test_editor
    sc, view = ed.editor_scene, ed.view
    sc.set_mode("draw_line"); qapp.processEvents()
    combo = w.prop_manager._prop_widgets["Weight"]
    combo.setCurrentText("Heavy"); qapp.processEvents()
    assert ss.current_style()["weight"] == "Heavy"
    n = len(sc._draw_lines)
    _click(view, view.mapFromScene(QPointF(-100, -150)))
    # Mid-placement (tool armed): the panel still shows the template.
    assert sc.mode == "draw_line"
    assert isinstance(_target(w), GeometryTemplate)
    _click(view, view.mapFromScene(QPointF(100, -150)))
    assert len(sc._draw_lines) == n + 1
    line = sc._draw_lines[-1]
    assert line.style["weight"] == "Heavy"
    assert line.to_dict()["style"]["weight"] == "Heavy"   # what is saved
    # draw_line is single-placement: the tool disarms and the panel shows the
    # placed line (existing behaviour), whose Weight row reads Heavy.
    assert sc.mode == "select" and _target(w) is line
    assert w.prop_manager._prop_widgets["Weight"].currentText() == "Heavy"


def test_selected_edit_does_not_move_current(win_with_editor, qapp):
    w = win_with_editor
    sc = w._test_editor.editor_scene
    ss.set_current(weight="Heavy")
    ln = LineItem(QPointF(0, -150), QPointF(100, -150))
    sc.addItem(ln); sc._draw_lines.append(ln); sc.push_undo_state()
    sc.set_mode("select"); sc.clearSelection(); ln.setSelected(True)
    qapp.processEvents()
    assert _target(w) is ln
    w.prop_manager._prop_widgets["Weight"].setCurrentText("Light")
    qapp.processEvents()
    assert ln.style["weight"] == "Light"
    assert ss.current_style()["weight"] == "Heavy"


def test_current_persists_through_save_settings(win_with_editor):
    w = win_with_editor
    ss.set_current(weight="Heavy")
    w.save_settings()
    ss.reset_current()
    ss.current_from_settings(w.settings)   # module-scoped mw: its own store
    assert ss.current_style()["weight"] == "Heavy"


def test_no_by_block_ui_strings():
    """G5: no user-facing "By Block" left in the app code (WM-1)."""
    root = pathlib.Path(__file__).resolve().parents[1]
    hits = []
    for p in [root / "main.py", *(root / "firepro3d").rglob("*.py")]:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if re.search(r"""["'][^"']*\bBy Block\b[^"']*["']""", s):
                hits.append(f"{p.name}:{i}: {s}")
    assert hits == [], hits
