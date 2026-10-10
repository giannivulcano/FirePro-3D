"""ET1 G1 -- block editors preview Fixed ends and Drafting linetypes at the
project drawing scale; schematic editors / render scenes keep real size;
a project scale change reaches open editors (MainWindow half:
``test_et1_mainwindow_scale.py``)."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden
from tests.lt5_support import arrow, set_ends
from tests.test_et1_raw import _head_width, _render as _render_bare
from tests.test_lts_canvas import _inner, _row


def _editor_scene(kind="block"):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 50.0
    w = BlockEditorWidget(proj, kind=kind)
    return proj, w, w.editor_scene


def test_g1_block_editor_follows_project_drawing_scale(qapp):
    _, _, sc = _editor_scene()
    sc.scale_manager.drawing_scale = 50.0            # what main's units sync copies (MainWindow test)
    lid = hidden(sc)
    ln = LineItem(QPointF(0, 0), QPointF(2000, 0))
    ln.style["linetype"] = lid
    sc.addItem(ln)
    row = _row(_render_bare(sc, QRectF(0, -20, 1000, 40), 1000, 40), 20)  # 1 px/mm
    dashes, gaps = _inner(row, True), _inner(row, False)
    assert dashes and all(abs(n - 300) <= 3 for n in dashes), dashes   # 6 mm x 50
    assert gaps and all(abs(n - 150) <= 3 for n in gaps), gaps         # 3 mm x 50
    a = arrow(length=3.0, half=1.0)
    sc.register_block_definition(a)
    ln2 = LineItem(QPointF(0, 300), QPointF(2000, 300))
    set_ends(ln2, finish=a.id)
    sc.addItem(ln2)
    sc._draw_lines.append(ln2)
    # 0.2 px/mm crop around ln2 only (the Hidden line at y = 0 stays out);
    # the finish attach point sits on the right edge.
    img = _render_bare(sc, QRectF(0, 200, 2000, 200), 400, 40)
    assert abs(_head_width(img) - 30) <= 3, _head_width(img)    # 3 mm x 50 = 150 mm = 30 px


def test_g1_schematic_editor_keeps_real_size(qapp):
    _, _, sc = _editor_scene(kind="schematic")
    assert sc.scale_manager.drawing_scale == 1.0
    lid = hidden(sc)
    ln = LineItem(QPointF(0, 0), QPointF(36, 0))
    ln.style["linetype"] = lid
    sc.addItem(ln)
    row = _row(_render_bare(sc, QRectF(0, -2, 40, 4)), 20)             # 10 px/mm
    # Hidden 6 / 3 at 1:1 -> lit 0-60 px, dark 60-90, lit 90-150 ...
    assert all(row[5:55]) and not any(row[65:85]) and all(row[95:145])


def test_g1_schematic_render_scene_keeps_real_size(qapp):
    from firepro3d.schematic_scene import SchematicSceneManager
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 50.0
    # commit_block_definition returns None on empty primitives -> one line.
    prim = LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()
    d = proj.commit_block_definition(block_id=None, name="S", library="L", series="",
                                     primitives=[prim], origin=(0.0, 0.0),
                                     place_instance=False, kind="schematic")
    assert d is not None
    sc = SchematicSceneManager(proj).scene_for(d.id)
    assert sc is not None and sc.scale_manager.drawing_scale == 1.0
