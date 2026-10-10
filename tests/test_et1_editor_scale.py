"""ET1 G1 -- block and schematic editors preview Fixed ends and Drafting
linetypes at the project drawing scale; schematic render scenes keep real size;
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


def test_g1_schematic_editor_follows_project_drawing_scale_like_a_block_editor(qapp):
    """Smoke ruling 2026-10-10 (retires Q2's schematic real size): schematic
    content is built from model-size blocks, so its editor previews ends and
    Drafting linetypes at the project drawing scale exactly like a block
    editor -- the same line looks the same in both."""
    heads = {}
    for kind in ("block", "schematic"):
        _, _, sc = _editor_scene(kind=kind)
        assert sc.scale_manager.drawing_scale == 100.0     # not pinned to 1:1
        sc.scale_manager.drawing_scale = 50.0              # what the units sync copies
        a = arrow(length=3.0, half=1.0)
        sc.register_block_definition(a)
        ln = LineItem(QPointF(0, 300), QPointF(2000, 300))
        set_ends(ln, finish=a.id)
        sc.addItem(ln)
        sc._draw_lines.append(ln)
        heads[kind] = _head_width(_render_bare(sc, QRectF(0, 200, 2000, 200), 400, 40))
    assert abs(heads["schematic"] - 30) <= 3, heads      # 3 mm x 50 = 150 mm = 30 px
    assert abs(heads["schematic"] - heads["block"]) <= 1, heads


def test_g1_schematic_render_scene_keeps_real_size(qapp):
    """The sheet-render scene stays 1:1: it only reaches paper, where ends
    print true mm through the paper scale, and its extent fits the NTS box."""
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
