"""Paper text on the unified TextItem — rotation + axis-isolated box resize (C5.7).

Paper text is repointed onto ``firepro3d.text_item.TextItem`` (the retired
``TextAnnotationItem`` is gone).  These guards prove the two behaviours the
repoint had to preserve/enable on paper:

  * rotate is surfaced (paper text used to be translate+scale only), and
    ``manip_rotate`` writes ``data.angle``; and
  * a mid-edge horizontal box-resize changes ONLY the dragged axis
    (wrap width) and leaves ``box_height_mm`` untouched — the axis-isolated
    behaviour ported from the legacy paper ``_resize_box_on_paper`` (review I2).
"""
from PyQt6.QtCore import QPointF

from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
from firepro3d.text_item import TextItem, TextAnnotationData


def _stub_resolver():
    """A ViewResolver with all-None managers (safe for sheets with no views)."""
    return ViewResolver(None, None, None, None)


def _paper_scene():
    return PaperScene(Sheet.create_default(), _stub_resolver())


def test_paper_text_rotates(qapp):
    p = _paper_scene()
    t = TextItem(TextAnnotationData(text="R", x=0, y=0, height_mm=2.5))
    p.addItem(t)
    assert "rotate" in t.manip_capabilities()
    t.manip_rotate(45.0, t.boundingRect().center())
    assert abs(t.data.angle - 45.0) < 1e-6


def test_paper_text_midedge_resize_axis_isolated(qapp):
    p = _paper_scene()
    d = TextAnnotationData(text="Hello world", x=0, y=0, height_mm=2.5)
    t = TextItem(d)
    p.addItem(t)
    before_h = d.box_height_mm
    # Drag a horizontal mid-edge grip (index 3 = right-middle): wrap width
    # changes, box height must not (0/auto stays 0).
    pts = t.grip_points()
    t.apply_grip(3, pts[3] + QPointF(20, 0))
    assert d.box_height_mm == before_h
