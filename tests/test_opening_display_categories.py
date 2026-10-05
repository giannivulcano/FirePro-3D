"""Door / Window / Opening Display Manager categories (model side).

Ratified 2026-10-04: per-Feature rows on the Model + Paper tabs; legacy
"Opening" settings seed Door / Window when their own keys are absent.
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening

_IDS = {"Door": "door_914", "Window": "window_900", "Opening": "blank_900"}


def _scene_with_openings(model_scene):
    """Wall 0..6000 with a door, window and blank opening (wall.openings)."""
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(6000, 0), thickness_mm=200.0)
    scene.addItem(w)
    scene._walls.append(w)
    ops = {}
    for i, (cat, fid) in enumerate(_IDS.items()):
        op = WallOpening(wall=w, feature_id=fid, offset_along=1500.0 + 1500.0 * i)
        scene.addItem(op)
        w.openings.append(op)
        op._reposition()
        ops[cat] = op
    return scene, ops


@pytest.mark.parametrize("cat,fid", list(_IDS.items()))
def test_display_category_follows_feature(qapp, cat, fid):
    assert WallOpening(feature_id=fid).display_category == cat
