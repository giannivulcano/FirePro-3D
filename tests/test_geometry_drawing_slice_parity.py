"""tests/test_geometry_drawing_slice_parity.py — Slice 8 C0 characterisation net.

Exercises concern #6's simple 2D-drawing primitives (Line / Rectangle / Circle /
Polyline) as they behave TODAY on ``Model_Space`` so the later relocation commits
(C1-C3) that lift the drawing *methods* into ``GeometryDrawingController`` can
prove zero behavioural regression by keeping every test green.

Behaviour-home model (design §0)
--------------------------------
This slice moves the drawing *methods* to the controller but leaves all drawing
*state* (the persisted ``_draw_lines`` / ``_draw_rects`` / ``_draw_circles`` /
``_polylines`` lists and every transient anchor/preview/flag) ON the scene,
because the already-extracted ``PlacementInputCoordinator`` reads it.  So every
assertion here reads scene-side state directly (``scene._draw_lines`` etc.) and
stays valid across the whole refactor without any home-indirection helper.

Drive strategy
--------------
Placement is driven through the REAL entry point — posted ``QMouseEvent`` /
``QKeyEvent`` on a shown+activated view (``shown_model_view``) — never by calling
a private handler directly (``QTest.mouseMove`` is inert here; real events route
through ``Model_View`` → scene ``mousePressEvent`` → dispatch → the shell → the
controller, which is exactly the seam we must not break).
"""

from __future__ import annotations

import pytest
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


def _key(view, key: Qt.Key) -> None:
    """Post a real key press+release through *view*."""
    for etype in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        ev = QKeyEvent(etype, key, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# C0-1  Back-compat: every relocating handler/applier is still callable on scene
# ─────────────────────────────────────────────────────────────────────────────


def test_drawing_shells_present(shown_model_view):
    """The moved handlers/appliers keep scene-side shells (dispatch + coordinator
    + main.py/model_view resolve them via ``getattr(self|self._scene, name)``)."""
    _view, scene = shown_model_view

    expected = [
        # line (shared with draw_gridline dispatch)
        "_press_draw_line", "_move_draw_line", "_preview_from_line",
        "_commit_draw_line_at",
        # rectangle
        "_press_draw_rectangle", "_move_draw_rectangle", "_preview_from_rectangle",
        "_apply_rectangle_dynamic_input", "_commit_rectangle_rotated",
        "_advance_rectangle_to_rotate_step",
        # circle
        "_press_draw_circle", "_move_draw_circle", "_preview_from_circle",
        "_commit_draw_circle_at",
        # polyline
        "_press_polyline", "_move_polyline", "_preview_from_polyline",
        "_commit_polyline_at",
        # dual-concern factory + generic ref helpers that MUST stay scene-side
        "_make_line_like", "_make_ref_line", "_make_ref_circle",
    ]
    missing = [n for n in expected if not callable(getattr(scene, n, None))]
    assert not missing, f"Scene is missing callable(s): {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# C0-2  Line: two real clicks → one LineItem
# ─────────────────────────────────────────────────────────────────────────────


def test_draw_line_two_click_creates_line(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line")
    assert len(scene._draw_lines) == 0

    _press_at(view, QPointF(0, 0))
    _press_at(view, QPointF(600, 0))

    assert len(scene._draw_lines) == 1, "one line must be committed by two clicks"


# ─────────────────────────────────────────────────────────────────────────────
# C0-3  Circle: two real clicks → one CircleItem
# ─────────────────────────────────────────────────────────────────────────────


def test_draw_circle_two_click_creates_circle(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_circle")
    assert len(scene._draw_circles) == 0

    _press_at(view, QPointF(0, 0))       # centre
    _press_at(view, QPointF(400, 0))     # radius

    assert len(scene._draw_circles) == 1, "one circle must be committed by two clicks"


# ─────────────────────────────────────────────────────────────────────────────
# C0-4  Rectangle: three real clicks (anchor → size → rotate-commit) → one rect
# ─────────────────────────────────────────────────────────────────────────────


def test_draw_rectangle_three_click_creates_rect(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_rectangle")
    assert len(scene._draw_rects) == 0

    _press_at(view, QPointF(0, 0))       # anchor + preview
    _press_at(view, QPointF(400, 200))   # size → enter rotate step
    _press_at(view, QPointF(600, 200))   # commit at orientation

    assert len(scene._draw_rects) == 1, "one rectangle must be committed by three clicks"


# ─────────────────────────────────────────────────────────────────────────────
# C0-5  Polyline: clicks + Enter finalise → one PolylineItem
# ─────────────────────────────────────────────────────────────────────────────


def test_draw_polyline_clicks_enter_creates_polyline(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("polyline")
    assert len(scene._polylines) == 0

    _press_at(view, QPointF(0, 0))
    _press_at(view, QPointF(300, 0))
    _press_at(view, QPointF(300, 300))
    _key(view, Qt.Key.Key_Return)        # finalise the polyline

    assert len(scene._polylines) == 1, "Enter must finalise one polyline"
    assert scene._polyline_active is None, "no in-progress polyline after finalise"


# ─────────────────────────────────────────────────────────────────────────────
# C0-6  draw_gridline stays scene-side (concern #7 untouched by this slice)
# ─────────────────────────────────────────────────────────────────────────────


def test_draw_gridline_still_builds_gridline_item(shown_model_view):
    """The line handlers are shared with ``draw_gridline``; the dual-concern
    factory ``_make_line_like`` (which builds a ``GridlineItem``) stays scene-side,
    so drawing a gridline still produces a gridline, not a plain line."""
    from firepro3d.gridline import GridlineItem

    view, scene = shown_model_view
    lines_before = len(scene._draw_lines)
    grids_before = len(scene._gridlines)

    scene.set_mode("draw_gridline")
    _press_at(view, QPointF(0, 0))
    _press_at(view, QPointF(0, 600))

    assert len(scene._gridlines) == grids_before + 1, "a GridlineItem must be created"
    assert len(scene._draw_lines) == lines_before, "no plain LineItem for a gridline"
    assert isinstance(scene._gridlines[-1], GridlineItem)


# ─────────────────────────────────────────────────────────────────────────────
# C0-7  clear() teardown contract (RED-demo target)
# ─────────────────────────────────────────────────────────────────────────────


def test_setmode_clears_in_progress_rectangle(shown_model_view):
    """Leaving a draw mode mid-placement must discard the in-progress anchor +
    preview.  This is the invariant that ``GeometryDrawingController.clear()``
    defends after C3 — stubbing ``clear()`` to a no-op makes this go RED."""
    view, scene = shown_model_view
    scene.set_mode("draw_rectangle")

    _press_at(view, QPointF(0, 0))       # arm anchor + create preview
    assert scene._draw_rect_anchor is not None, "anchor armed after first click"
    preview = scene._draw_rect_preview
    assert preview is not None and preview.scene() is scene

    scene.set_mode("select")             # leave mid-placement
    QApplication.processEvents()

    assert scene._draw_rect_anchor is None, "anchor must be cleared on mode change"
    assert scene._draw_rect_preview is None, "preview handle must be cleared"
    assert preview.scene() is not scene, "preview item must be removed from scene"


def test_setmode_cancels_in_progress_polyline(shown_model_view):
    """An in-progress polyline is discarded (removed from scene + list) when the
    mode changes away from ``polyline`` — the second half of the clear contract."""
    view, scene = shown_model_view
    scene.set_mode("polyline")

    _press_at(view, QPointF(0, 0))
    _press_at(view, QPointF(300, 0))
    active = scene._polyline_active
    assert active is not None, "a polyline is in progress after two clicks"

    scene.set_mode("select")
    QApplication.processEvents()

    assert scene._polyline_active is None, "in-progress polyline cleared on mode change"
    assert active not in scene._polylines, "in-progress polyline removed from the list"
