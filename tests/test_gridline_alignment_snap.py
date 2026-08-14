"""Tests for GridlineItem.alignment_reference_points() and the
get_effective_position inference hook in Model_Space.

TDD: tests written first; GREEN after implementation.
See docs/specs/inferred-dimension-driven-placement.md §5.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsView

from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space


# ---------------------------------------------------------------------------
# make_model_space fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def make_model_space(qapp):
    """Factory that builds a Model_Space with an attached QGraphicsView.

    The view is sized 800×800 at identity transform (m11==1.0) and centred
    on the origin so that scene coords in the range ~(-400,400) are in the
    viewport.  Scenes requiring wider coverage call
    ``view.centerOn(x, y)`` or ``view.resize(...)`` on the returned scene's
    first view after construction.
    """
    created: list[tuple[Model_Space, QGraphicsView]] = []

    def _factory() -> Model_Space:
        ms = Model_Space()
        view = QGraphicsView(ms)
        view.resize(800, 800)
        # Identity transform: m11 == 1.0, viewport rect maps 1 px → 1 scene unit.
        view.resetTransform()
        # Centre the view on origin so the 800×800 viewport covers roughly
        # (-400, -400) to (400, 400) in scene units.
        view.centerOn(0.0, 0.0)
        # Pump events so Qt registers the view with the scene.
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        created.append((ms, view))
        return ms

    yield _factory

    # Cleanup — hide views so Qt doesn't complain about open widgets.
    for ms, view in created:
        view.hide()


# ---------------------------------------------------------------------------
# Step 1 — GridlineItem.alignment_reference_points()
# ---------------------------------------------------------------------------

class TestAlignmentReferencePoints:
    """GridlineItem.alignment_reference_points() returns the right features."""

    def test_returns_four_features(self, qapp):
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        feats = gl.alignment_reference_points()
        assert len(feats) == 4

    def test_all_features_kind_point(self, qapp):
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        feats = gl.alignment_reference_points()
        assert {f.kind for f in feats} == {"point"}

    def test_endpoints_match_grip_points(self, qapp):
        """Endpoints must be consistent with grip_points() (scene coords)."""
        p1 = QPointF(100.0, 200.0)
        p2 = QPointF(100.0, 5200.0)
        gl = GridlineItem(p1, p2, label="A")
        feats = gl.alignment_reference_points()
        pts = {(round(f.x, 3), round(f.y, 3)) for f in feats}
        grip = gl.grip_points()
        for gp in grip:
            assert (round(gp.x(), 3), round(gp.y(), 3)) in pts, (
                f"grip point {gp} not found in feature points {pts}"
            )

    def test_all_source_ids_equal_id_of_item(self, qapp):
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        feats = gl.alignment_reference_points()
        assert all(f.source_id == id(gl) for f in feats)

    def test_bubble_features_present(self, qapp):
        """Bubble centres must be included (outboard of the endpoints)."""
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        feats = gl.alignment_reference_points()
        labels = {f.label for f in feats}
        assert "bubble" in labels

    def test_endpoint_features_present(self, qapp):
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        feats = gl.alignment_reference_points()
        labels = {f.label for f in feats}
        assert "endpoint" in labels

    def test_horizontal_gridline_x_axis(self, qapp):
        """Horizontal gridline: endpoints lie on x-axis (y==0)."""
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(5000.0, 0.0), label="A")
        feats = gl.alignment_reference_points()
        pts = {(round(f.x, 1), round(f.y, 1)) for f in feats}
        assert (0.0, 0.0) in pts
        assert (5000.0, 0.0) in pts


# ---------------------------------------------------------------------------
# Step 3 — Model_Space inference hook in get_effective_position
# ---------------------------------------------------------------------------

class TestGetEffectivePositionInferenceHook:
    """Inference block activates only when OSNAP misses, inference is enabled,
    and an active item is set."""

    def test_snaps_to_vertical_gridline_x(self, qapp, make_model_space):
        """Cursor within tol of a vertical gridline's X must snap to that X."""
        ms = make_model_space()
        # Vertical gridline at x=1000.
        ref = GridlineItem(QPointF(1000.0, -500.0), QPointF(1000.0, 5000.0),
                           label="1")
        ms.addItem(ref)
        ms._gridlines.append(ref)

        # Active item (not in scene — just sets the self-exclude id).
        active = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 100.0), label="2")
        ms._inference_active_item = active
        ms._inference_enabled = True

        # Disable OSNAP and underlay snap so the inference path is reached.
        ms._osnap_enabled = False
        ms._snap_to_underlay = False

        # Centre the view on the geometry so items(vp_rect) includes `ref`.
        view = ms.views()[0]
        view.resize(4000, 4000)
        view.centerOn(1000.0, 2500.0)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        # Cursor 2 mm off the gridline — within INFERENCE_TOL_PX at scale 1.
        pos = ms.get_effective_position(QPointF(1002.0, 2500.0))
        assert round(pos.x(), 1) == 1000.0, (
            f"Expected x=1000.0, got x={pos.x()}"
        )

    def test_snaps_to_horizontal_gridline_y(self, qapp, make_model_space):
        """Cursor within tol of a horizontal gridline's Y must snap to that Y."""
        ms = make_model_space()
        ref = GridlineItem(QPointF(-500.0, 2000.0), QPointF(5000.0, 2000.0),
                           label="A")
        ms.addItem(ref)
        ms._gridlines.append(ref)

        active = GridlineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0), label="B")
        ms._inference_active_item = active
        ms._inference_enabled = True
        ms._osnap_enabled = False
        ms._snap_to_underlay = False

        view = ms.views()[0]
        view.resize(4000, 4000)
        view.centerOn(2500.0, 2000.0)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        pos = ms.get_effective_position(QPointF(2500.0, 2003.0))
        assert round(pos.y(), 1) == 2000.0, (
            f"Expected y=2000.0, got y={pos.y()}"
        )

    def test_no_snap_when_inference_disabled(self, qapp, make_model_space):
        """When _inference_enabled is False, inference is not applied."""
        ms = make_model_space()
        ref = GridlineItem(QPointF(1000.0, -500.0), QPointF(1000.0, 5000.0),
                           label="1")
        ms.addItem(ref)
        ms._gridlines.append(ref)

        active = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 100.0), label="2")
        ms._inference_active_item = active
        ms._inference_enabled = False   # disabled
        ms._osnap_enabled = False
        ms._snap_to_underlay = False
        # Also disable grid snap for a clean test.
        ms._grid_snap_enabled = getattr(ms, "_grid_snap_enabled", False)

        view = ms.views()[0]
        view.resize(4000, 4000)
        view.centerOn(1000.0, 2500.0)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        pos = ms.get_effective_position(QPointF(1002.0, 2500.0))
        # Without inference the cursor should NOT snap to x=1000.
        assert round(pos.x(), 1) != 1000.0, (
            f"Inference should be disabled but snapped to x={pos.x()}"
        )

    def test_no_snap_when_no_active_item(self, qapp, make_model_space):
        """When _inference_active_item is None, inference is not applied."""
        ms = make_model_space()
        ref = GridlineItem(QPointF(1000.0, -500.0), QPointF(1000.0, 5000.0),
                           label="1")
        ms.addItem(ref)
        ms._gridlines.append(ref)

        ms._inference_active_item = None  # no active item
        ms._inference_enabled = True
        ms._osnap_enabled = False
        ms._snap_to_underlay = False

        view = ms.views()[0]
        view.resize(4000, 4000)
        view.centerOn(1000.0, 2500.0)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        pos = ms.get_effective_position(QPointF(1002.0, 2500.0))
        assert round(pos.x(), 1) != 1000.0, (
            f"No active item: should not snap but got x={pos.x()}"
        )

    def test_inference_result_stored(self, qapp, make_model_space):
        """_inference_result is populated after a successful inference snap."""
        ms = make_model_space()
        ref = GridlineItem(QPointF(1000.0, -500.0), QPointF(1000.0, 5000.0),
                           label="1")
        ms.addItem(ref)
        ms._gridlines.append(ref)

        active = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 100.0), label="2")
        ms._inference_active_item = active
        ms._inference_enabled = True
        ms._osnap_enabled = False
        ms._snap_to_underlay = False

        view = ms.views()[0]
        view.resize(4000, 4000)
        view.centerOn(1000.0, 2500.0)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        ms.get_effective_position(QPointF(1002.0, 2500.0))
        assert ms._inference_result is not None
        assert ms._inference_result.priority != "free"

    def test_active_item_self_excluded(self, qapp, make_model_space):
        """Reference features from the active item itself must not snap to it."""
        ms = make_model_space()

        # Place the active item in the scene as well (simulating a grip drag
        # where the item being dragged IS in the scene).
        active = GridlineItem(QPointF(1000.0, -500.0), QPointF(1000.0, 5000.0),
                              label="1")
        ms.addItem(active)
        ms._gridlines.append(active)
        ms._inference_active_item = active   # self
        ms._inference_enabled = True
        ms._osnap_enabled = False
        ms._snap_to_underlay = False

        view = ms.views()[0]
        view.resize(4000, 4000)
        view.centerOn(1000.0, 2500.0)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        # Cursor near the active item's own X.  Self-exclusion must prevent snap.
        pos = ms.get_effective_position(QPointF(1002.0, 2500.0))
        # With only the active item present and self-exclusion active, no
        # inference snap should occur — result falls through to grid/free snap.
        assert ms._inference_result is not None
        # priority must be "free" (no external refs)
        assert ms._inference_result.priority == "free"

    def test_inference_new_attributes_present(self, qapp):
        """Model_Space must expose the three new inference attributes."""
        ms = Model_Space()
        assert hasattr(ms, "_inference_engine")
        assert hasattr(ms, "_inference_enabled")
        assert hasattr(ms, "_inference_result")
        assert hasattr(ms, "_inference_active_item")
        assert ms._inference_enabled is True
        assert ms._inference_result is None
        assert ms._inference_active_item is None


# ---------------------------------------------------------------------------
# Step 4 — Guide overlay render tests (behavior-driven pixel checks)
# ---------------------------------------------------------------------------

from PyQt6.QtGui import QPixmap, QColor
from firepro3d.constants import INFERENCE_GUIDE_COLOR


def _render_view(view):
    """Grab the view's full rendered output (including drawForeground overlays)."""
    return view.grab().toImage()


def _has_guide_color(img, tolerance=6):
    """Return True if any pixel within a 1px stride matches INFERENCE_GUIDE_COLOR.

    Uses stride=1 because dashed cosmetic lines may be sparse (only a few
    pixels wide) and larger strides can miss them.
    """
    target = QColor(INFERENCE_GUIDE_COLOR).getRgb()[:3]
    for x in range(0, img.width(), 1):
        for y in range(0, img.height(), 1):
            rgb = QColor(img.pixel(x, y)).getRgb()[:3]
            if all(abs(rgb[i] - target[i]) <= tolerance for i in range(3)):
                return True
    return False


def test_guide_paints_when_result_present(qapp, make_model_space):
    """drawForeground must paint guide-color pixels when _inference_result has guides."""
    from firepro3d.model_view import Model_View
    ms = make_model_space()
    # Attach a real Model_View — the plain QGraphicsView from the fixture
    # does not override drawForeground, so we need Model_View for this test.
    mv = Model_View(ms)
    mv.resize(400, 400)
    mv.resetTransform()
    from firepro3d.inference_engine import InferenceResult, Guide, ReferenceFeature
    ref = ReferenceFeature("point", 0.0, 0.0, 1, "endpoint")
    ms._inference_result = InferenceResult(snapped=(0.0, 0.0),
                                           guides=[Guide("v", 0.0, ref)],
                                           priority="single-guide")
    mv.centerOn(0.0, 0.0)
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
    mv.viewport().repaint()
    img = _render_view(mv)
    assert _has_guide_color(img), (
        "Expected guide-color pixels when _inference_result has guides"
    )
    mv.hide()


def test_no_guide_paint_when_result_none(qapp, make_model_space):
    """drawForeground must NOT paint guide-color pixels when _inference_result is None."""
    from firepro3d.model_view import Model_View
    ms = make_model_space()
    mv = Model_View(ms)
    mv.resize(400, 400)
    mv.resetTransform()
    ms._inference_result = None
    mv.centerOn(0.0, 0.0)
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
    mv.viewport().repaint()
    img = _render_view(mv)
    assert not _has_guide_color(img), (
        "Expected no guide-color pixels when _inference_result is None"
    )
    mv.hide()
