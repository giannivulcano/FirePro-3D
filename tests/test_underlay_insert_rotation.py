"""Regression: insert-at-origin + rotation must pivot about the drawing's
base point (which the import transform maps to group-local (0,0)), matching
the import-dialog preview — NOT about the geometry centroid.

Bug: for "Insert at origin" with a non-zero rotation, the placed underlay
was flung far from where the preview showed it. Root cause:
``_apply_underlay_display`` set the group's transform origin to
``boundingRect().center()`` and then applied ``record.rotation``. The dialog
preview instead rotates about the base point (``setTransformOriginPoint(bx,
by)``). After ``apply_import_transform`` bakes ``coord -> (coord-base)*scale``
into the geometry, the base point sits at group-local (0, 0); rotating about
the centroid keeps the centroid fixed but swings the base point away from the
insert point, so an off-centre base point lands the drawing far from the
preview. The fix pivots vector underlay groups about local (0, 0).

See docs/specs/underlay-workflow.md and MEMORY note
"Rotation conventions: Y-up vs Qt".
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.underlay_import_dialog import ImportParams


# Raw source box (1100,1100)-(1300,1200); base point offset from the box so a
# centroid-pivot vs base-point-pivot bug diverges visibly.
_RAW_POINTS = [(1100, 1100), (1300, 1100), (1300, 1200), (1100, 1200), (1100, 1100)]


def _geom():
    return [{"kind": "path_points", "layer": "0", "closed": True,
             "points": list(_RAW_POINTS)}]


def _commit(scene: Model_Space, *, rotation, insert, base_x, base_y, scale=1.0):
    p = ImportParams()
    p.file_type = "dxf"
    p.geom_list = _geom()
    p.scale = scale
    p.base_x = base_x
    p.base_y = base_y
    p.insert_at_origin = (insert == QPointF(0, 0))
    p.rotation = rotation
    scene._place_import_params = p
    scene._place_import_ghost = None
    scene._commit_place_import(insert)
    return scene.underlays[-1]  # (record, group)


def _qt_rotate(pt: QPointF, deg: float, pivot: QPointF) -> QPointF:
    """Qt setRotation(deg) about *pivot*: x' = x*cos - y*sin, y' = x*sin + y*cos
    (clockwise in Qt's y-down space), applied to (pt - pivot) then re-offset."""
    th = math.radians(deg)
    c, s = math.cos(th), math.sin(th)
    dx, dy = pt.x() - pivot.x(), pt.y() - pivot.y()
    return QPointF(pivot.x() + dx * c - dy * s,
                   pivot.y() + dx * s + dy * c)


class TestInsertAtOriginRotation:
    def test_origin_plus_rotation_pivots_about_base_point(self, qapp):
        """Insert-at-origin (0,0) + 90° must keep the BASE POINT at the scene
        origin (base -> local (0,0)); the centroid swings accordingly."""
        scene = Model_Space()
        rec, grp = _commit(scene, rotation=90, insert=QPointF(0, 0),
                           base_x=1000, base_y=1000)

        # Transformed geometry centroid (base subtracted, scale 1):
        #   ((1100+1300)/2 - 1000, (1100+1200)/2 - 1000) = (200, 150)
        # Base point -> local (0,0) -> scene origin (insert 0,0). Rotating the
        # centroid about the scene origin by Qt's +90:
        expected = _qt_rotate(QPointF(200, 150), 90, QPointF(0, 0))

        c = grp.sceneBoundingRect().center()
        assert c.x() == pytest.approx(expected.x(), abs=1e-3)
        assert c.y() == pytest.approx(expected.y(), abs=1e-3)

    def test_origin_rotation_zero_unchanged(self, qapp):
        """Rotation 0 with insert-at-origin: centroid at transformed position."""
        scene = Model_Space()
        rec, grp = _commit(scene, rotation=0, insert=QPointF(0, 0),
                           base_x=1000, base_y=1000)
        c = grp.sceneBoundingRect().center()
        assert c.x() == pytest.approx(200, abs=1e-3)
        assert c.y() == pytest.approx(150, abs=1e-3)

    def test_non_origin_plus_rotation_pivots_about_insert(self, qapp):
        """Non-origin insert + rotation: base point lands at the insert point
        and the drawing rotates about it (parity with the preview)."""
        scene = Model_Space()
        insert = QPointF(5000, 2000)
        rec, grp = _commit(scene, rotation=90, insert=insert,
                           base_x=1000, base_y=1000)

        # Centroid local (200,150), pivot = base point = local (0,0) which is
        # placed at the insert point; rotate about the insert point.
        expected = _qt_rotate(QPointF(insert.x() + 200, insert.y() + 150),
                              90, insert)
        c = grp.sceneBoundingRect().center()
        assert c.x() == pytest.approx(expected.x(), abs=1e-3)
        assert c.y() == pytest.approx(expected.y(), abs=1e-3)
