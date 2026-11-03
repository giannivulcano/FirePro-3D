"""SB4c half A -- elevation / section gridline bubbles drawn by the plan
gridline's annotation block (design
docs/superpowers/specs/2026-11-03-sb4c-elev-bubble-datum-design.md D1 D2 D6)."""
import pytest
from PyQt6.QtCore import QLineF, QPointF, QRectF

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.gridline import GridlineItem
from tests.test_sb4b_gridline_bubble import CIRCLE_R, _bubble_def, _gridline, _scene


def _k(ms):
    """Scene units per authored mm: the project drawing scale (plan and section
    canvas alike, annotative._drawing_scale); ScaleManager() defaults to 100."""
    return ms.scale_manager.drawing_scale


def _plan_gridline(ms, x=2500.0, label="1"):
    """A plan gridline vertical in plan at world x (start = bubble 1 at y=-3000);
    a North elevation shows it at h = -x."""
    gl = GridlineItem(QPointF(x, -3000.0), QPointF(x, 3000.0), label)
    ms.addItem(gl)
    ms._gridlines.append(gl)
    return gl


def _offset_box_def(ms, name="OffsetBox"):
    """A NON-circular, NON-symmetric Gridline bubble: a 12 x 6 mm box from
    y = -2 to y = +4 mm about the origin (Qt y-down block frame; drafter probe:
    its stroke op bounds are QRectF(-6, -2, 12, 6)), so a ray (0, +1) leaves at
    4 mm and (0, -1) at 2 mm -- a trim-sign probe. Mapped as the project default."""
    geom = {"type": "draw_rectangle", "x": -6.0, "y": -2.0, "w": 12.0, "h": 6.0,
            "color": "token:auto", "lineweight": 1.0}
    text = {"type": "text", "text": "@[Mark]", "x": -5.0, "y": -1.0, "height_mm": 3.0,
            "wrap_width_mm": 10.0, "box_height_mm": 4.0, "align": "C", "valign": "M"}
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[geom, text])
    d.scale_mode = "annotative"
    d.host_category = "Gridline"
    d.attributes = [normalise_attr({"key": "Mark", "source": "host", "host_key": "Mark",
                                    "placeholder": ""})]
    ms.register_block_definition(d)
    ms.annotation_defaults["Gridline"] = d.id
    return d


# -- D1 seam: data host vs graphics parent ----------------------------------

def test_d1_bound_label_parent_is_the_graphics_parent_and_host_stays_the_data_source(qapp):
    from PyQt6.QtWidgets import QGraphicsRectItem
    from firepro3d.bound_label import BoundLabelItem
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms, label="Q")
    holder = QGraphicsRectItem()
    ms.addItem(holder)
    lab = BoundLabelItem(gl, parent=holder)
    assert lab.parentItem() is holder
    assert lab.host is gl and lab.category == "Gridline"
    assert lab.host_values({"Mark"})["Mark"].raw == "Q"
    assert BoundLabelItem(gl).parentItem() is gl                    # default unchanged
    assert BoundLabelItem(gl, child=False).parentItem() is None     # SB4a D1 unchanged


def test_d1_outlined_label_base_has_no_overlays_and_gridline_bubble_extends_it(qapp):
    from PyQt6.QtWidgets import QGraphicsRectItem
    from firepro3d.bound_label import OutlinedLabel
    from firepro3d.gridline import GridlineBubble
    ms = _scene()
    k = _k(ms)
    _bubble_def(ms)
    gl = _gridline(ms)
    assert isinstance(gl.bubble1, GridlineBubble) and isinstance(gl.bubble1, OutlinedLabel)
    lab = OutlinedLabel(gl, child=False)
    ms.addItem(lab)
    assert lab.trim_distance(0.0, 1.0) == pytest.approx(CIRCLE_R * k, abs=0.05 * k)
    assert not lab.outline_path().isEmpty()
    gl.setSelected(True)
    assert lab.overlay_pens() == []                   # the base never rings
    # A GridlineBubble under another graphics parent still reads the plan gridline.
    holder = QGraphicsRectItem()
    ms.addItem(holder)
    b = GridlineBubble(gl, parent=holder)
    assert b.parentItem() is holder and b.host is gl and b.category == "Gridline"


def _static_width(label):
    """Width of the union of *label*'s painted non-text ops at its own k
    (the ops ``BoundLabelItem.paint`` hands ``paint_ops``)."""
    st = label._state()
    r = QRectF()
    for op in label._ops(label._k(None, st[0]), st):
        if op.kind != "text":
            r = r.united(op.path.boundingRect())
    return r.width()


def test_d1_section_scene_forwards_the_annotation_resolver(qapp, section_scene_for):
    """A label hosted on a plan gridline but living in a SectionScene draws the
    project's mapped block at the section canvas k (= the drawing scale)."""
    from firepro3d.bound_label import BoundLabelItem
    ms, sec = section_scene_for("north")
    k = _k(ms)
    d = _bubble_def(ms)
    gl = _plan_gridline(ms)
    assert sec.annotation_block("Gridline") is d
    lab = BoundLabelItem(gl, child=False)
    sec.addItem(lab)
    assert lab.definition() is d
    assert _static_width(lab) == pytest.approx(2 * CIRCLE_R * k, abs=0.1 * k)


def test_d1_cross_scene_host_deleted_first_reads_as_dead_not_a_raise(qapp, section_scene_for):
    """The data host now lives in ANOTHER scene than the label: when the plan
    gridline's C++ object is gone first (teardown order, undo restore), the
    label's host read must return None (placeholders, E9) -- a RuntimeError
    raised inside a Qt virtual (boundingRect / shape) is a native abort."""
    from PyQt6 import sip
    from firepro3d.bound_label import BoundLabelItem
    ms, sec = section_scene_for("north")
    _bubble_def(ms)
    gl = _plan_gridline(ms)
    lab = BoundLabelItem(gl, child=False)
    sec.addItem(lab)
    ms._gridlines.remove(gl)
    ms.removeItem(gl)
    sip.delete(gl)
    assert lab.host_values() is None
    lab.refresh()
    lab.boundingRect()                    # must not raise
