from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsScene
from firepro3d.gridline import GridlineItem


def test_screen_dash_is_model_absolute():
    from firepro3d.gridline import _dash_pattern_model, _DASH_MODEL_MM, GRID_WIDTH
    import math
    # On-screen dash px = entry * pen_width_px; pen_width_px = GRID_WIDTH (constant).
    # scene dash mm = entry * pen_w_scene = entry * (GRID_WIDTH/sx) must equal _DASH_MODEL_MM for any sx.
    for sx in (0.01, 0.1, 0.5, 2.0):
        entry = _dash_pattern_model(sx)[0]
        scene_dash_mm = entry * (GRID_WIDTH / sx)
        assert math.isclose(scene_dash_mm, _DASH_MODEL_MM, rel_tol=1e-9)


def test_paint_uses_dash_pattern_not_solid(qapp):
    scene = QGraphicsScene()
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    scene.addItem(gl)
    pen = gl._build_line_pen(sx=1.0)
    assert pen.style().name != "SolidLine"
    assert len(pen.dashPattern()) >= 2


def test_grip_uses_house_selection_style(qapp):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor
    from firepro3d.gridline import GridlineItem
    from firepro3d.constants import SELECTION_OUTLINE_COLOR
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="A")
    grip = gl._grip1
    # white fill
    assert grip.brush().color() == QColor(Qt.GlobalColor.white)
    # SELECTION_OUTLINE_COLOR outline (a real pen, not NoPen)
    assert grip.pen().style() != Qt.PenStyle.NoPen
    assert grip.pen().color().name().lower() == QColor(SELECTION_OUTLINE_COLOR).name().lower()


def test_duplicate_warning_keeps_border_width(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d.gridline import GridlineItem
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="A")
    w_before = gl.bubble1.pen().widthF()
    gl.update_duplicate_warning(True)
    assert gl.bubble1.pen().widthF() == w_before   # only color changes
    assert gl.bubble1.pen().color().name() == "#ff8800"


def test_paper_dash_pattern_normalizes_to_onpaper_mm():
    from firepro3d.gridline import _dash_pattern_mm, _DASH_MM, _GAP_MM, _DOT_MM
    import math
    lw_mm = 0.35
    pat = _dash_pattern_mm(lw_mm)
    # entries are mm/lw_mm; on-paper dash = entry * (lw_mm/S) * S = _DASH_MM for any S
    for S in (0.01, 0.02, 0.5, 1.0):
        pen_w_scene = lw_mm / S
        onpaper_dash = pat[0] * pen_w_scene * S
        assert math.isclose(onpaper_dash, _DASH_MM, rel_tol=1e-9)
        onpaper_gap = pat[1] * pen_w_scene * S
        assert math.isclose(onpaper_gap, _GAP_MM, rel_tol=1e-9)


def test_screen_dash_model_constants_positive():
    from firepro3d.gridline import _DASH_MODEL_MM, _GAP_MODEL_MM, _DOT_MODEL_MM
    assert _DASH_MODEL_MM > 0
    assert _GAP_MODEL_MM > 0
    assert _DOT_MODEL_MM > 0
    # Dot is the short mark of a dash-dot; keep it shorter than the dash.
    assert _DOT_MODEL_MM < _DASH_MODEL_MM
