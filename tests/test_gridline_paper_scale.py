"""Tests for gridline-bubble true-scale paper rendering (paper-space spec §9.9.1)."""
import pytest

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

    def test_absolute_values_in_expected_band(self, qapp):
        # Independently-derived expectation: Consolas-bold cap/em ratio is
        # ~0.63-0.72 on Windows, so 3.0mm cap -> em 4.1-4.8mm, radius = em/0.9.
        radius_mm, em_mm = bubble_paper_geometry(3.0)
        assert 4.1 <= em_mm <= 4.8
        assert radius_mm == pytest.approx(em_mm / 0.9)
