"""tests/test_arc_polygon_slice_parity.py — Slice 9 C0 characterisation net.

Exercises concern #6's Arc (3-step centre→radius/start→span) and Polygon (3-step
centre→radius→rotate, with ↑/↓ sides + ←/→ inscribed) drawing behaviour as it
lands AFTER the relocation into ``GeometryDrawingController`` (slice 9), proving
zero behavioural regression: the moved *methods* live on the controller while all
drawing *state* (the persisted ``_draw_arcs`` / ``_draw_polygons`` lists and every
transient anchor/preview/flag) stays ON the scene (behaviour-home model, design
§0 / model-space-architecture.md §5.3), so every assertion reads scene-side state.

Drive strategy mirrors the slice-8 file: the REAL entry point — posted
``QMouseEvent`` / ``QKeyEvent`` on a shown+activated view — routes through
``Model_View`` → scene ``mousePressEvent`` → dispatch → the scene shell → the
controller, exactly the seam this slice must not break.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication


# ── real-entry-point drive helpers ───────────────────────────────────────────


def _press_at(view, scene_pt: QPointF, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    """Post a real left-button click (press+release) at *scene_pt* through *view*."""
    vp = view.mapFromScene(scene_pt)
    for etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(
            etype,
            QPointF(vp),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            modifiers,
        )
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# C0-1  Back-compat: every relocating handler/applier/keyhelper still on scene
# ─────────────────────────────────────────────────────────────────────────────


def test_arc_polygon_shells_present(shown_model_view):
    """The moved arc/polygon handlers/appliers keep scene-side shells (dispatch,
    coordinator ``getattr(self._scene, name)``, keyPressEvent, and test callers
    all resolve them by name)."""
    _view, scene = shown_model_view

    expected = [
        # arc (dispatch + applier + test-called commit helpers)
        "_press_draw_arc", "_move_draw_arc", "_preview_from_arc",
        "_apply_arc_dynamic_input", "_commit_draw_arc_at",
        "_commit_draw_arc_rim_at", "_arc_end_point_for_span",
        # polygon (dispatch + applier + keyPress + coordinator + instruction)
        "_press_polygon", "_move_polygon", "_preview_from_polygon",
        "_apply_polygon_dynamic_input", "_polygon_rotation_angle_to",
        "_polygon_readout", "_cycle_polygon_sides", "_toggle_polygon_inscribed",
        "_commit_polygon_at", "_preview_polygon_rotation",
    ]
    missing = [n for n in expected if not callable(getattr(scene, n, None))]
    assert not missing, f"Scene is missing callable shell(s): {missing}"

    # And each shell actually delegates to the controller.
    assert scene._geom_ctl is not None
    for name in expected:
        assert hasattr(scene._geom_ctl, name), f"controller missing {name}"


# ─────────────────────────────────────────────────────────────────────────────
# C0-2  Arc: three real clicks (centre → start → end) → one ArcItem
# ─────────────────────────────────────────────────────────────────────────────


def test_draw_arc_three_click_creates_arc(shown_model_view):
    from firepro3d.construction_geometry import ArcItem

    view, scene = shown_model_view
    scene.set_mode("draw_arc")
    assert len(scene._draw_arcs) == 0

    _press_at(view, QPointF(0, 0))        # centre
    _press_at(view, QPointF(400, 0))      # start angle / radius
    _press_at(view, QPointF(0, -400))     # end angle → commit

    assert len(scene._draw_arcs) == 1, "one arc must be committed by three clicks"
    assert isinstance(scene._draw_arcs[-1], ArcItem)
    assert scene._draw_arc_step == 0, "arc state resets after commit"


# ─────────────────────────────────────────────────────────────────────────────
# C0-3  Polygon: three real clicks (centre → radius → rotate) → one polygon
# ─────────────────────────────────────────────────────────────────────────────


def test_draw_polygon_three_click_creates_polygon(shown_model_view):
    from firepro3d.construction_geometry import RegularPolygonItem

    view, scene = shown_model_view
    scene.set_mode("polygon")
    assert len(scene._draw_polygons) == 0

    _press_at(view, QPointF(0, 0))        # centre
    _press_at(view, QPointF(400, 0))      # radius → rotate step
    _press_at(view, QPointF(0, -400))     # rotate → commit

    assert len(scene._draw_polygons) == 1, "one polygon committed by three clicks"
    assert isinstance(scene._draw_polygons[-1], RegularPolygonItem)
    assert scene._polygon_center is None, "polygon state resets after commit"


# ─────────────────────────────────────────────────────────────────────────────
# C0-4  Polygon live-variant shells: ↑/↓ sides + ←/→ inscribed delegate + repaint
# ─────────────────────────────────────────────────────────────────────────────


def test_polygon_variant_shells_delegate(shown_model_view):
    _view, scene = shown_model_view
    scene.set_mode("polygon")

    n0 = scene._polygon_sides
    scene._cycle_polygon_sides(+1)
    assert scene._polygon_sides == n0 + 1, "sides shell must delegate to controller"

    was = scene._polygon_inscribed
    scene._toggle_polygon_inscribed()
    assert scene._polygon_inscribed is (not was), "inscribed toggle must delegate"

    # Readout reflects the live state (shell → controller).
    assert f"{scene._polygon_sides} sides" in scene._polygon_readout()


# ─────────────────────────────────────────────────────────────────────────────
# C0-5  HUD applier paths (coordinator → scene shell → controller) unchanged
# ─────────────────────────────────────────────────────────────────────────────


def test_arc_applier_step_aware(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_arc")
    _press_at(view, QPointF(0, 0))        # centre → step 1
    assert scene._draw_arc_step == 1
    # step-1 rim applier advances to span step
    assert scene._apply_arc_dynamic_input(QPointF(400, 0)) is True
    assert scene._draw_arc_step == 2
    # step-2 span applier commits
    assert scene._apply_arc_dynamic_input({"span_deg": 90.0}) is True
    assert len(scene._draw_arcs) == 1


def test_polygon_applier_step_aware(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("polygon")
    _press_at(view, QPointF(0, 0))        # centre
    # sizing applier (QPointF) advances to rotate step
    assert scene._apply_polygon_dynamic_input(QPointF(400, 0)) is True
    assert scene._polygon_rotating is True
    # rotate applier (dict) commits
    assert scene._apply_polygon_dynamic_input({"angle_deg": 30.0}) is True
    assert len(scene._draw_polygons) == 1


# ─────────────────────────────────────────────────────────────────────────────
# C0-6  clear() teardown contract for arc + polygon (RED-demo target)
# ─────────────────────────────────────────────────────────────────────────────


def test_setmode_clears_in_progress_arc(shown_model_view):
    """Leaving ``draw_arc`` mid-placement discards centre/step/radius-line.
    ``GeometryDrawingController.clear()`` defends this — stub its arc block to a
    no-op and this goes RED."""
    view, scene = shown_model_view
    scene.set_mode("draw_arc")

    _press_at(view, QPointF(0, 0))        # centre → step 1, radius line created
    assert scene._draw_arc_center is not None
    assert scene._draw_arc_step == 1
    radius_line = scene._draw_arc_radius_line
    assert radius_line is not None and radius_line.scene() is scene

    scene.set_mode("select")              # leave mid-placement
    QApplication.processEvents()

    assert scene._draw_arc_center is None, "arc centre cleared on mode change"
    assert scene._draw_arc_step == 0, "arc step reset on mode change"
    assert scene._draw_arc_radius_line is None, "radius-line handle cleared"
    assert radius_line.scene() is not scene, "radius line removed from scene"


def test_setmode_clears_in_progress_polygon(shown_model_view):
    """Leaving ``polygon`` mid-placement discards centre/rotating/ref-items."""
    view, scene = shown_model_view
    scene.set_mode("polygon")

    _press_at(view, QPointF(0, 0))        # centre
    _press_at(view, QPointF(400, 0))      # radius → rotate step (ref items created)
    assert scene._polygon_center is not None
    assert scene._polygon_rotating is True
    ref_circle = scene._polygon_ref_circle
    assert ref_circle is not None and ref_circle.scene() is scene

    scene.set_mode("select")
    QApplication.processEvents()

    assert scene._polygon_center is None, "polygon centre cleared on mode change"
    assert scene._polygon_rotating is False, "polygon rotate flag reset"
    assert scene._polygon_ref_circle is None, "ref circle handle cleared"
    assert ref_circle.scene() is not scene, "ref circle removed from scene"
