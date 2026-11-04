"""SB4d guard 4 (paper): a placed-section head and the detail callout head
print at authored mm through paper_display._apply_block -- radius HEAD_R / S
scene mm (= HEAD_R mm on paper) at paper scale S -- and the canvas size
comes back after the pass."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.paper_display import apply_paper_overrides, restore_model_display
from tests._sb4d_helpers import HEAD_R, dispose, head_def, plan_scene


@pytest.mark.parametrize("S", [0.01, 0.02])
def test_guard4_paper_heads_print_at_authored_mm(qapp, S):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Section")
        head_def(ms, "Detail")
        s = sec.place_section(QPointF(0.0, 0.0), QPointF(6000.0, 0.0))
        d = det.create_detail("Detail 1", QRectF(0.0, 1000.0, 3000.0, 2000.0))
        k = ms.scale_manager.drawing_scale
        rect = QRectF(-5000.0, -5000.0, 20000.0, 20000.0)
        saved = apply_paper_overrides(ms, rect, S)
        try:
            for h in (s.head_a, s.head_b, d.bubble):
                assert h.enclosing_radius() == pytest.approx(HEAD_R / S, rel=1e-3)
        finally:
            restore_model_display(saved)
        for h in (s.head_a, s.head_b, d.bubble):
            assert h.enclosing_radius() == pytest.approx(HEAD_R * k, rel=1e-3)
    finally:
        dispose(ms, sec, tabs)
