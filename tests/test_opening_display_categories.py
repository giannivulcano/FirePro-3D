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


def _red_pixels(scene, op):
    """Count clearly-red pixels where *op* paints (real render, VC3)."""
    r = op.sceneBoundingRect().adjusted(-50, -50, 50, 50)
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 400, 400), r)
    p.end()
    n = 0
    for y in range(0, 400, 2):
        for x in range(0, 400, 2):
            c = img.pixelColor(x, y)
            if c.red() > 180 and c.green() < 90 and c.blue() < 90:
                n += 1
    return n


def test_model_rows_exist_under_architecture():
    from firepro3d import display_manager as dm
    keys = [c["key"] for c in dm._CATEGORIES if c["group"] == "Architecture"]
    for k in ("Door", "Window", "Opening"):
        assert k in keys
    assert keys.index("Wall") < keys.index("Door") < keys.index("Window") < keys.index("Opening")


@pytest.mark.parametrize("target", ["Door", "Window", "Opening"])
def test_project_colour_reaches_only_its_feature(qapp, model_scene, target):
    from firepro3d.display_manager import apply_project_display_settings
    scene, ops = _scene_with_openings(model_scene)
    data = {k: {"color": "#0000ff"} for k in _IDS}
    data[target] = {"color": "#ff0000"}
    apply_project_display_settings(scene, data)
    for cat, op in ops.items():
        red = _red_pixels(scene, op)
        assert (red > 0) == (cat == target), (cat, red)


def test_category_defaults_for_new_window(qapp, model_scene):
    from firepro3d.display_manager import apply_category_defaults
    scene, ops = _scene_with_openings(model_scene)
    # After the build: scene construction rewrites the current display keys.
    QSettings("GV", "FirePro3D").setValue("display/Window/visible", "false")
    for op in ops.values():
        apply_category_defaults(op)
    assert not ops["Window"].isVisible()
    assert ops["Door"].isVisible() and ops["Opening"].isVisible()
