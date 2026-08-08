"""Tests for gridline-bubble true-scale paper rendering (paper-space spec §9.9.1)."""
import pytest
from PyQt6.QtGui import QFont, QFontMetricsF

from firepro3d.constants import TEXT_METRIC_REF_PX, GRIDLINE_BUBBLE_LABEL_EM_FRAC
from firepro3d.gridline import bubble_paper_geometry


class TestBubblePaperGeometry:
    def test_radius_exceeds_em_exceeds_cap(self, qapp):
        radius_mm, em_mm = bubble_paper_geometry(3.0)
        assert radius_mm > em_mm > 3.0  # cap < em (cap_ratio < 1) < radius (em = 0.9r)

    def test_default_cap_gives_plausible_head(self, qapp):
        radius_mm, _ = bubble_paper_geometry(3.0)
        # 3mm cap → head diameter in the 8–12mm drafting band
        assert 4.0 <= radius_mm <= 6.0

    def test_linear_in_cap_height(self, qapp):
        r1, e1 = bubble_paper_geometry(3.0)
        r2, e2 = bubble_paper_geometry(6.0)
        assert r2 == pytest.approx(2 * r1)
        assert e2 == pytest.approx(2 * e1)

    def test_matches_metrics_derivation(self, qapp):
        f = QFont("Consolas")
        f.setBold(True)
        f.setPixelSize(TEXT_METRIC_REF_PX)
        cap_ratio = QFontMetricsF(f).capHeight() / TEXT_METRIC_REF_PX
        radius_mm, em_mm = bubble_paper_geometry(3.0)
        assert em_mm == pytest.approx(3.0 / cap_ratio)
        assert radius_mm == pytest.approx(em_mm / GRIDLINE_BUBBLE_LABEL_EM_FRAC)
