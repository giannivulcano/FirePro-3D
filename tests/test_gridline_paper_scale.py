"""Tests for gridline-bubble true-scale paper rendering (paper-space spec §9.9.1)."""
import pytest

from firepro3d.gridline import bubble_paper_geometry


@pytest.fixture(autouse=True)
def _clear_bubble_geometry_cache():
    """bubble_paper_geometry is a module-level lru_cache — shared session state."""
    bubble_paper_geometry.cache_clear()
    yield
    bubble_paper_geometry.cache_clear()


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


from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem

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


def _full_bubble_state(b):
    return (QRectF(b.rect()),
            b._label.font().pixelSize(), b._label.font().family(), b._label.font().bold(),
            b._label.scale(), b._label.pos().x(), b._label.pos().y(),
            bool(b.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations))


class TestBubblePaperMode:
    def test_enter_sets_scene_geometry(self, qapp):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
        b = gl.bubble1
        saved = b.enter_paper_mode(radius_scene=476.0, em_scene=428.0)
        assert not (b.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        assert b.rect() == QRectF(-476.0, -476.0, 952.0, 952.0)
        assert b._label.scale() == pytest.approx(428.0 / 1000)  # TEXT_METRIC_REF_PX
        assert saved  # opaque state dict for exit_paper_mode

    def test_exit_restores_exactly(self, qapp):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
        b = gl.bubble1
        before = _full_bubble_state(b)
        saved = b.enter_paper_mode(radius_scene=476.0, em_scene=428.0)
        b.exit_paper_mode(saved)
        assert _full_bubble_state(b) == before


# ─────────────────────────────────────────────────────────────────────────────
# Render-measurement tests — bubbles true-scale through sheet viewports
# ─────────────────────────────────────────────────────────────────────────────

import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

import firepro3d.paper_display as pd


PX_PER_MM = 8  # render density for measurement tests

# Fixture geometry: A4 portrait sheet, two 80mm-square viewports of the same
# plan view at 1:50 and 1:100, each crop CENTERED on the gridline's bubble1
# at scene (0,0) — the bubble renders at each viewport's paper center.
_VP_W = 80.0
_VP1_X, _VP1_Y = 65.0, 30.0     # center (105, 70)
_VP2_X, _VP2_Y = 65.0, 130.0    # center (105, 170)
_CROPS = {
    "V50":  QRectF(-2000.0, -2000.0, 4000.0, 4000.0),   # S = 80/4000  = 1:50
    "V100": QRectF(-4000.0, -4000.0, 8000.0, 8000.0),   # S = 80/8000  = 1:100
}


@pytest.fixture
def paper_env(monkeypatch):
    """Controlled paper display settings — never touches the real QSettings.

    apply_paper_overrides reads load_paper_color_mode / load_paper_categories /
    (via resolve_line_weight_mm) load_line_weights as module globals; patching
    the module attributes redirects all three to in-test state.
    """
    env = SimpleNamespace(
        cats=copy.deepcopy(pd.FACTORY_PAPER_CATEGORIES),
        mode=pd.PaperColorMode.BW,
    )
    monkeypatch.setattr(pd, "load_paper_categories",
                        lambda settings=None: copy.deepcopy(env.cats))
    monkeypatch.setattr(pd, "load_paper_color_mode",
                        lambda settings=None: env.mode)
    monkeypatch.setattr(pd, "load_line_weights",
                        lambda settings=None: list(pd.FACTORY_LINE_WEIGHTS))
    return env


@pytest.fixture
def two_scale_sheet(qapp, paper_env):
    """Model_Space with one vertical gridline + a two-viewport PaperScene."""
    from firepro3d.model_space import Model_Space
    from firepro3d.paper_space import Sheet, SheetViewData, PaperScene, ViewResolver

    scene = Model_Space()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 10000), label="1")
    scene.addItem(gl)
    scene._gridlines.append(gl)

    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (scene, QRectF(_CROPS[vn]))

    sheet = Sheet.create_default()
    sheet.paper_size = "A4"  # programmatic title block — no DXF artwork load
    sheet.sheet_views = [
        SheetViewData("plan", "V50", "V50", 0.02, _VP1_X, _VP1_Y, _VP_W, _VP_W),
        SheetViewData("plan", "V100", "V100", 0.01, _VP2_X, _VP2_Y, _VP_W, _VP_W),
    ]
    paper = PaperScene(sheet, resolver)
    yield SimpleNamespace(model=scene, gl=gl, paper=paper, sheet=sheet,
                          env=paper_env)
    paper.dispose()


def _render_paper(scene):
    """Render the whole PaperScene at exactly PX_PER_MM pixels per paper mm."""
    r = scene.sceneRect()
    img = QImage(int(r.width() * PX_PER_MM), int(r.height() * PX_PER_MM),
                 QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    # Explicit target+source with IgnoreAspectRatio: exact PX_PER_MM density
    # on both axes (default KeepAspectRatio letterboxes on int truncation).
    scene.render(p, QRectF(0, 0, img.width(), img.height()), r,
                 Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _render_model(scene, rect=QRectF(-3000, -3000, 6000, 6000), px=600):
    """Render a model-scene region to a fixed-size image (fidelity checks)."""
    img = QImage(px, px, QImage.Format.Format_RGB32)
    img.fill(0xFF101010)  # dark backdrop — model items are light-colored
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, px, px), QRectF(rect),
                 Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _paper_px(scene, x_mm, y_mm):
    """Map paper-mm coordinates to image pixel coordinates."""
    r = scene.sceneRect()
    return int((x_mm - r.x()) * PX_PER_MM), int((y_mm - r.y()) * PX_PER_MM)


def _dark_run_width(img, y_px, x0, x1):
    """Widest contiguous run of non-white pixels on row y between x0..x1."""
    best = run = 0
    for x in range(x0, x1):
        if QColor(img.pixel(x, y_px)).lightness() < 200:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _np_bgr(img):
    """QImage (Format_RGB32) → numpy (h, w, 3) int arrays as (b, g, r)."""
    import numpy as np
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(
        img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()]
    a = arr.astype(int)
    return a[..., 0], a[..., 1], a[..., 2]


class TestViewportTrueScale:
    def _measure_head(self, ts, center_x_mm, center_y_mm):
        img = getattr(ts, "_img", None)
        if img is None:
            img = _render_paper(ts.paper)
            ts._img = img
        cx, cy = _paper_px(ts.paper, center_x_mm, center_y_mm)
        # Scan the row through the bubble center, strictly inside the viewport
        # (excludes the viewport border lines).
        x0, _ = _paper_px(ts.paper, center_x_mm - _VP_W / 2 + 2, 0)
        x1, _ = _paper_px(ts.paper, center_x_mm + _VP_W / 2 - 2, 0)
        return _dark_run_width(img, cy, x0, x1)

    def test_head_measures_paper_size_at_two_scales(self, two_scale_sheet):
        ts = two_scale_sheet
        ts.env.cats["Grid Line"]["fill"] = "#000000"  # solid head → run = diameter
        radius_mm, _ = bubble_paper_geometry(3.0)
        expected = 2 * radius_mm * PX_PER_MM
        d1 = self._measure_head(ts, _VP1_X + _VP_W / 2, _VP1_Y + _VP_W / 2)
        d2 = self._measure_head(ts, _VP2_X + _VP_W / 2, _VP2_Y + _VP_W / 2)
        assert d1 == pytest.approx(expected, abs=PX_PER_MM)  # ±1mm equivalent
        assert d2 == pytest.approx(expected, abs=PX_PER_MM)
        assert abs(d1 - d2) <= 2  # both viewports agree on paper size

    def test_restore_fidelity_model_render_unchanged(self, two_scale_sheet):
        ts = two_scale_sheet
        img_a = _render_model(ts.model)
        _render_paper(ts.paper)  # triggers apply → render → restore, twice
        img_b = _render_model(ts.model)
        assert img_a == img_b

    def test_selection_never_plots(self, two_scale_sheet):
        ts = two_scale_sheet
        ts.gl.setSelected(False)
        img_a = _render_paper(ts.paper)
        ts.gl.setSelected(True)  # grips/ring/lock now visible on screen
        img_b = _render_paper(ts.paper)
        assert img_a == img_b

    def test_duplicate_orange_never_plots_full_color(self, two_scale_sheet):
        from firepro3d.gridline import apply_duplicate_warnings
        ts = two_scale_sheet
        gl2 = GridlineItem(QPointF(1000, 0), QPointF(1000, 10000), label="1")
        ts.model.addItem(gl2)
        ts.model._gridlines.append(gl2)
        apply_duplicate_warnings(ts.model._gridlines)  # production invocation
        assert ts.gl.bubble1.pen().color().name() == "#ff8800"  # warning armed
        ts.env.mode = pd.PaperColorMode.FULL_COLOR
        img = _render_paper(ts.paper)
        b, g, r = _np_bgr(img)
        # Warning pen is exactly #ff8800, drawn without antialiasing — a tight
        # hue band avoids false hits from subpixel-AA fringes on black text.
        orange = (r >= 240) & (g >= 110) & (g <= 160) & (b <= 60)
        # Scan only the viewport interiors: gridline content renders there;
        # the title block / view titles contain AA text, no model content.
        for vx, vy in ((_VP1_X, _VP1_Y), (_VP2_X, _VP2_Y)):
            x0, y0 = _paper_px(ts.paper, vx + 1, vy + 1)
            x1, y1 = _paper_px(ts.paper, vx + _VP_W - 1, vy + _VP_W - 1)
            assert not orange[y0:y1, x0:x1].any()

    def test_origin_cross_never_plots(self, two_scale_sheet):
        ts = two_scale_sheet
        # Hide the gridline: its bubble1 sits exactly on (0,0) at higher Z and
        # would occlude the origin cross (ITT 14px bubble over the ±11px cross).
        ts.gl.setVisible(False)
        origin_items = [it for it in ts.model.items() if it.data(0) == "origin"]
        assert origin_items  # Model_Space.__init__ calls draw_origin()
        for it in origin_items:
            pen = QPen(QColor("#ff0000"))
            pen.setWidthF(3.0)
            pen.setCosmetic(True)
            it.setPen(pen)
        # Both crops are centered on (0,0) → origin inside every viewport.
        img = _render_paper(ts.paper)
        b, g, r = _np_bgr(img)
        red = (r >= 200) & (g <= 60) & (b <= 60)
        assert not red.any()
        assert all(it.isVisible() for it in origin_items)  # restored

    def test_model_display_scale_isolated(self, two_scale_sheet):
        ts = two_scale_sheet
        img_a = _render_paper(ts.paper)
        # Display Manager model-side bubble scale: sets the attribute AND
        # bubble.setScale (display_manager._apply_gridline) — apply both.
        ts.gl._display_scale = 2.0
        ts.gl.bubble1.setScale(2.0)
        ts.gl.bubble2.setScale(2.0)
        img_b = _render_paper(ts.paper)
        assert img_a == img_b
        assert ts.gl.bubble1.scale() == 2.0  # model state untouched by pass

    def test_line_weight_drives_border(self, two_scale_sheet):
        ts = two_scale_sheet

        def line_thickness():
            img = _render_paper(ts.paper)
            cx = _VP1_X + _VP_W / 2
            cy = _VP1_Y + _VP_W / 2
            best = 0
            # Rows 10..35mm below the bubble center (line is DashDotLine —
            # take the max across rows so dash gaps don't zero the measure).
            for dy_mm in range(10, 35):
                _, py = _paper_px(ts.paper, 0, cy + dy_mm)
                x0, _ = _paper_px(ts.paper, cx - 5, 0)
                x1, _ = _paper_px(ts.paper, cx + 5, 0)
                best = max(best, _dark_run_width(img, py, x0, x1))
            return best

        ts.env.cats["Grid Line"]["line_weight"] = "Very Heavy"   # 0.50mm
        heavy = line_thickness()
        ts.env.cats["Grid Line"]["line_weight"] = "Very Light"   # 0.13mm
        light = line_thickness()
        assert heavy > light
        assert heavy == pytest.approx(0.50 * PX_PER_MM, abs=2)
        assert 1 <= light <= 2  # 0.13mm × 8px/mm ≈ 1px


class TestOverridePassExceptionSafety:
    def test_mid_pass_failure_unwinds_applied_overrides(self, two_scale_sheet,
                                                        monkeypatch):
        """A raise inside a per-item apply must not strand items in paper mode.

        Without the unwind, the exception escapes before the caller receives
        `saved`, so everything mutated up to that point stays stuck in paper
        geometry — and the next pass would snapshot that as model state.
        """
        ts = two_scale_sheet
        b1_rect_before = QRectF(ts.gl.bubble1.rect())
        real_apply = pd._apply_gridline

        def apply_then_boom(*args, **kwargs):
            real_apply(*args, **kwargs)   # gridline reaches paper mode first
            raise RuntimeError("mid-pass failure")

        monkeypatch.setattr(pd, "_apply_gridline", apply_then_boom)
        with pytest.raises(RuntimeError):
            pd.apply_paper_overrides(ts.model, QRectF(_CROPS["V50"]),
                                     paper_scale=0.02)
        # The gridline's saved entry precedes the raise, so restore must have
        # run: not stuck in paper mode, bubble geometry back to model state.
        assert ts.gl._paper_render is False
        assert bool(ts.gl.bubble1.flags()
                    & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        assert ts.gl.bubble1.rect() == b1_rect_before
        # Origin-cross entries are visibility-only saves — restored too.
        origin_items = [it for it in ts.model.items() if it.data(0) == "origin"]
        assert origin_items and all(it.isVisible() for it in origin_items)


@pytest.fixture
def aspect_diverged_sheet(qapp, paper_env):
    """One 80x40mm viewport of the square V50 crop (grip-resized aspect).

    scene.render() defaults to KeepAspectRatio, so the true render scale is
    min(w_ratio, h_ratio) = the height ratio here — half the width ratio.
    """
    from firepro3d.model_space import Model_Space
    from firepro3d.paper_space import Sheet, SheetViewData, PaperScene, ViewResolver

    scene = Model_Space()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 10000), label="1")
    scene.addItem(gl)
    scene._gridlines.append(gl)

    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (scene, QRectF(_CROPS[vn]))

    sheet = Sheet.create_default()
    sheet.paper_size = "A4"  # programmatic title block — no DXF artwork load
    sheet.sheet_views = [
        SheetViewData("plan", "V50", "V50", 0.02,
                      _VP1_X, _VP1_Y, _VP_W, _VP_W / 2),
    ]
    paper = PaperScene(sheet, resolver)
    yield SimpleNamespace(model=scene, gl=gl, paper=paper, env=paper_env)
    paper.dispose()


class TestAspectDivergedViewport:
    def test_head_measures_true_rendered_size_under_keep_aspect(
            self, aspect_diverged_sheet):
        ts = aspect_diverged_sheet
        ts.env.cats["Grid Line"]["fill"] = "#000000"  # solid head → run = diameter
        crop = _CROPS["V50"]
        vp_h = _VP_W / 2
        # True geometric scale under KeepAspectRatio is the min ratio — and it
        # genuinely diverges from the width-only ratio in this fixture.
        true_scale = min(_VP_W / crop.width(), vp_h / crop.height())
        assert true_scale < _VP_W / crop.width()
        # paint() must author the bubble at radius r_mm / true_scale scene
        # units; rendered at true_scale that measures exactly 2*r_mm on paper.
        # (Width-only S would author r_mm / (2*true_scale) → half-size head.)
        radius_mm, _ = bubble_paper_geometry(3.0)
        expected = 2 * (radius_mm / true_scale) * true_scale * PX_PER_MM
        img = _render_paper(ts.paper)
        # KeepAspectRatio centers the square crop in the 80x40 viewport, so
        # bubble1 (scene (0,0) = crop center) sits at the viewport center.
        cx_mm = _VP1_X + _VP_W / 2
        cy_mm = _VP1_Y + vp_h / 2
        _, cy = _paper_px(ts.paper, cx_mm, cy_mm)
        x0, _ = _paper_px(ts.paper, cx_mm - _VP_W / 2 + 2, 0)
        x1, _ = _paper_px(ts.paper, cx_mm + _VP_W / 2 - 2, 0)
        measured = _dark_run_width(img, cy, x0, x1)
        assert measured == pytest.approx(expected, abs=PX_PER_MM)  # ±1mm equiv
