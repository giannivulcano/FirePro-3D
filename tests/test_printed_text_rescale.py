"""Notes on schematics, Part 3: the Drawing scale row resizes the canvas text
about each anchor, one undo step, printed size unchanged (N14, N16, AC4)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.annotative import editor_text_scale
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.block_properties_info import BlockPropertiesInfo
from firepro3d.constraint_controller import CONFLICT_STATUS
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem
from firepro3d.text_leader import normalise
from tests.test_printed_text_pdf import _cap_mm, _export


def _setup(**data):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w = BlockEditorWidget(proj, kind="schematic")
    t = TextItem(TextAnnotationData(**{"text": "H", "font_family": "Arial",
                                       "height_mm": 60.0, **data}))
    w._add_primitive(t)
    w.editor_scene.push_undo_state()
    return proj, w, t


def _row(w, label):
    BlockPropertiesInfo(w.editor_scene, "X", editor=w).set_property("Drawing scale", label)


def _point(t, fx, fy):
    r = t._box_rect_local()
    return t.mapToScene(QPointF(r.left() + fx * r.width(), r.top() + fy * r.height()))


@pytest.mark.parametrize("align,fx", [("L", 0.0), ("C", 0.5), ("R", 1.0)])
@pytest.mark.parametrize("valign,fy", [("T", 0.0), ("M", 0.5), ("B", 1.0)])
def test_the_box_scales_about_its_alignment_point(qapp, align, fx, valign, fy):
    _p, w, t = _setup(x=100.0, y=100.0, wrap=True, wrap_width_mm=400.0, box_height_mm=200.0,
                      align=align, valign=valign)
    before = _point(t, fx, fy)
    _row(w, "1:40")
    assert editor_text_scale(w.editor_scene) == 40.0
    d = t.data
    assert (d.height_mm, d.wrap_width_mm, d.box_height_mm) == pytest.approx((120.0, 800.0, 400.0))
    after = _point(t, fx, fy)
    assert (after.x(), after.y()) == pytest.approx((before.x(), before.y()))
    b = t.manip_bounds()
    assert (b.width(), b.height()) == pytest.approx((800.0, 400.0))


def test_the_printed_size_stays(qapp):
    """height / N: 60 / 20 before, 120 / 40 after."""
    _p, w, t = _setup()
    _row(w, "1:40")
    assert t.data.height_mm / editor_text_scale(w.editor_scene) == pytest.approx(3.0)


def test_row_only_sets_the_editor_size_in_the_pdf(qapp, tmp_path):
    """AC4: after the change the saved schematic still prints 3 mm in a 1:10
    viewport and at NTS, measured from the PDF."""
    proj, w, t = _setup()
    _row(w, "1:40")
    defn = w.commit_block("Riser", "", "")
    assert defn.text_scale == 40.0
    for scale, name in ((0.1, "a.pdf"), (0.0, "b.pdf")):
        path, _m, data = _export(tmp_path, proj, defn, scale, name)
        assert _cap_mm(path, data) == pytest.approx(3.0, abs=0.03)


def test_padding_and_corner_scale_too(qapp):
    _p, w, t = _setup(cell_padding_mm=10.0, border_corner_radius_mm=4.0)
    _row(w, "1:10")
    assert t.data.cell_padding_mm == pytest.approx(5.0)
    assert t.data.border_corner_radius_mm == pytest.approx(2.0)


def test_an_auto_box_stays_auto(qapp):
    """A height-auto, Wrap-untouched box keeps its authored zeros and flags."""
    _p, w, t = _setup()
    _row(w, "1:40")
    d = t.data
    assert d.wrap_width_mm == 0.0 and d.box_height_mm == 0.0
    assert d.wrap is None and d.shrink is None


def test_a_leader_keeps_tip_and_elbow(qapp):
    rec = normalise({"edge": "R", "t": 0.5, "shoulder_mm": 120.0, "tip_x": 900.0,
                     "tip_y": 500.0, "end": "", "weight": ""})
    _p, w, t = _setup(x=100.0, y=100.0, wrap=True, wrap_width_mm=400.0, box_height_mm=200.0,
                      leader=rec)
    knee = t.grip_points()[t.LEADER_KNEE_GRIP]
    assert (knee.x(), knee.y()) == pytest.approx((620.0, 200.0))
    _row(w, "1:40")
    after = t.grip_points()
    assert (after[t.LEADER_KNEE_GRIP].x(), after[t.LEADER_KNEE_GRIP].y()) == pytest.approx((620.0, 200.0))
    assert (after[t.LEADER_TIP_GRIP].x(), after[t.LEADER_TIP_GRIP].y()) == pytest.approx((900.0, 500.0))
    assert t.data.leader["shoulder_mm"] == pytest.approx(240.0)
    assert t.data.leader["edge"] == "R" and t.data.leader["t"] == 0.5


def test_one_undo_step_restores_all(qapp):
    _p, w, t = _setup(x=100.0, y=100.0, wrap=True, wrap_width_mm=400.0, box_height_mm=200.0,
                      align="C", valign="M")
    sc = w.editor_scene
    depth = len(sc._undo_stack)
    _row(w, "1:40")
    assert len(sc._undo_stack) == depth + 1
    sc.undo()
    assert editor_text_scale(sc) == 20.0
    back = sc._texts[0]
    assert (back.data.height_mm, back.data.x, back.data.y) == (60.0, 100.0, 100.0)
    assert back.data.wrap_width_mm == 400.0


def test_a_tie_to_free_geometry_holds(qapp):
    """The tied line yields; the tie and the printed size both hold."""
    _p, w, t = _setup(x=100.0, y=100.0, wrap=True, wrap_width_mm=400.0, box_height_mm=200.0)
    sc = w.editor_scene
    ln = LineItem(QPointF(100.0, 300.0), QPointF(-200.0, 300.0))
    w._add_primitive(ln)
    ctl = sc.constraint_ctl
    assert ctl.add("coincident", [{"uid": t._uid, "h": "bl"}, {"uid": ln._uid, "h": "p1"}])
    _row(w, "1:40")
    assert editor_text_scale(sc) == 40.0
    assert t.data.height_mm == pytest.approx(120.0)
    bl = _point(t, 0.0, 1.0)
    p1 = ln.line().p1()
    assert (bl.x(), bl.y()) == pytest.approx((p1.x(), p1.y()), abs=1e-4)


def test_a_tie_that_refuses_reverts_the_row_with_a_status(qapp, monkeypatch):
    """N14: a corner held by two fixed points cannot grow. Nothing changes."""
    _p, w, t = _setup(x=100.0, y=100.0, wrap=True, wrap_width_mm=400.0, box_height_mm=200.0)
    sc = w.editor_scene
    a, b = LineItem(QPointF(100, 100), QPointF(0, 0)), LineItem(QPointF(500, 300), QPointF(600, 400))
    w._add_primitive(a)
    w._add_primitive(b)
    ctl = sc.constraint_ctl
    ctl.add("fix", [{"uid": a._uid, "h": "item"}])
    ctl.add("fix", [{"uid": b._uid, "h": "item"}])
    assert ctl.add("coincident", [{"uid": t._uid, "h": "tl"}, {"uid": a._uid, "h": "p1"}])
    assert ctl.add("coincident", [{"uid": t._uid, "h": "br"}, {"uid": b._uid, "h": "p1"}])
    said = []
    monkeypatch.setattr(sc, "_show_status", lambda msg, *a: said.append(msg))
    depth, before = len(sc._undo_stack), t.to_dict()
    w._mark_clean()
    _row(w, "1:40")
    assert CONFLICT_STATUS in said
    assert editor_text_scale(sc) == 20.0
    assert t.to_dict() == before
    assert len(sc._undo_stack) == depth
    assert not w.is_dirty()
    props = BlockPropertiesInfo(sc, "X", editor=w).get_properties()
    assert props["Drawing scale"]["value"] == "1:20"


def test_a_row_edit_ends_a_live_text_edit_first(qapp):
    _p, w, t = _setup()
    sc = w.editor_scene
    sc._text_edit_ctl.begin(t, is_new=False)
    _row(w, "1:40")
    assert not t._editing


def test_a_real_size_schematic_has_no_row_to_commit(qapp):
    _p, w, t = _setup()
    BlockPropertiesInfo(w.editor_scene, "X", editor=w).set_property("Text sizing", "Real size")
    _row(w, "1:40")
    assert t.data.height_mm == 60.0


def test_an_unreadable_label_is_ignored(qapp):
    _p, w, t = _setup()
    _row(w, "banana")
    assert editor_text_scale(w.editor_scene) == 20.0
    assert t.data.height_mm == 60.0


def test_a_dim_between_two_texts_keeps_its_value(qapp):
    """N16: each text scales about its own anchor, so neither anchor moves and a dim
    between them stays. Group B review: scaling it threw the texts 500 apart."""
    _p, w, a = _setup(x=0.0, y=0.0, align="C", valign="M", wrap=True, wrap_width_mm=200.0,
                      box_height_mm=100.0)
    b = TextItem(TextAnnotationData(text="H", font_family="Arial", height_mm=60.0, x=1000.0,
                                    y=0.0, align="C", valign="M", wrap=True,
                                    wrap_width_mm=200.0, box_height_mm=100.0))
    w._add_primitive(b)
    ctl = w.editor_scene.constraint_ctl
    assert ctl.add("dim_distance", [{"uid": a._uid, "h": "center"},
                                    {"uid": b._uid, "h": "center"}], value=1000.0)
    dim = ctl.constraints[-1]
    w.editor_scene.push_undo_state()
    before = (_point(a, 0.5, 0.5), _point(b, 0.5, 0.5))
    _row(w, "1:40")
    assert editor_text_scale(w.editor_scene) == 40.0
    assert a.data.height_mm == pytest.approx(120.0)
    assert dim.value == pytest.approx(1000.0)
    assert _point(a, 0.5, 0.5).x() == pytest.approx(before[0].x())
    assert _point(b, 0.5, 0.5).x() == pytest.approx(before[1].x())


def test_a_schematic_saved_as_a_block_drops_the_keys(qapp):
    """N9: the keys are schematics only."""
    defn = BlockDefinition(id="x", name="X", kind="block", version=1, library="", series="",
                           scale_mode="real_size", origin=(0.0, 0.0), attributes=[],
                           primitives=[])
    defn.text_sizing, defn.text_scale = "printed", 20.0
    Model_Space._apply_block_meta(defn, {})
    assert (defn.text_sizing, defn.text_scale) == (None, None)
