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


from PyQt6.QtCore import QSettings

from firepro3d.paper_display import (
    FACTORY_PAPER_CATEGORIES, load_paper_categories, save_paper_categories,
    get_paper_display_for_save, apply_paper_display_from_project)


@pytest.fixture
def temp_settings(tmp_path):
    s = QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    yield s


@pytest.fixture
def clean_paper_settings():
    """Clear paper/* from the real QSettings before and after (mirrors TestProjectRoundTrip)."""
    s = QSettings("GV", "FirePro3D")
    s.remove("paper")
    s.sync()
    yield
    s.remove("paper")
    s.sync()


class TestGridLineCategoryModel:
    def test_factory_has_bubble_height_and_medium_weight(self):
        cat = FACTORY_PAPER_CATEGORIES["Grid Line"]
        assert cat["bubble_label_height_mm"] == 3.0
        assert cat["line_weight"] == "Medium"

    def test_fresh_settings_load_defaults(self, temp_settings):
        cats = load_paper_categories(temp_settings)
        assert cats["Grid Line"]["bubble_label_height_mm"] == 3.0

    def test_legacy_saved_category_backfills_height(self, temp_settings):
        cats = load_paper_categories(temp_settings)
        cats["Grid Line"].pop("bubble_label_height_mm")   # simulate pre-feature save
        cats["Grid Line"]["line_weight"] = "Very Light"   # legacy value must survive
        save_paper_categories(cats, temp_settings)
        loaded = load_paper_categories(temp_settings)
        assert loaded["Grid Line"]["bubble_label_height_mm"] == 3.0  # backfilled
        assert loaded["Grid Line"]["line_weight"] == "Very Light"    # saved value kept

    def test_round_trip(self, temp_settings):
        cats = load_paper_categories(temp_settings)
        cats["Grid Line"]["bubble_label_height_mm"] = 4.5
        save_paper_categories(cats, temp_settings)
        assert load_paper_categories(temp_settings)["Grid Line"]["bubble_label_height_mm"] == 4.5

    def test_project_snapshot_round_trips_bubble_height(self, clean_paper_settings):
        # Arrange: write a non-default bubble height into the real QSettings.
        cats = load_paper_categories()
        cats["Grid Line"]["bubble_label_height_mm"] = 4.5
        save_paper_categories(cats)
        # Act: capture a project snapshot, wipe settings back to factory, then restore.
        snapshot = get_paper_display_for_save()
        save_paper_categories(FACTORY_PAPER_CATEGORIES)  # wipe
        apply_paper_display_from_project(snapshot)
        # Assert: bubble height survived the round-trip.
        assert load_paper_categories()["Grid Line"]["bubble_label_height_mm"] == pytest.approx(4.5)


from PyQt6.QtCore import QPointF

from firepro3d.gridline import GridlineItem


class TestPerItemFieldRetired:
    def test_to_dict_omits_paper_height(self, qapp):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
        assert "paper_height_mm" not in gl.to_dict()

    def test_from_dict_ignores_legacy_key(self, qapp):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
        d = gl.to_dict()
        d["paper_height_mm"] = 7.7          # legacy .fpd content
        gl2 = GridlineItem.from_dict(d)
        assert gl2.grid_label == "1"        # loads cleanly
        assert not hasattr(gl2, "paper_height_mm")
