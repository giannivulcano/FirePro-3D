from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space
from firepro3d.halo import halo_scene_path
from firepro3d.construction_geometry import RectangleItem


def _approx_rect(a, b, tol=6.0):
    # tol absorbs the scene-hit stroke width that shape() adds vs the unstroked
    # sceneBoundingRect (~5px total on w/h, ~2.8px on origin); the double-transform
    # bug is off by tens of px, so 6px still cleanly separates correct from buggy.
    return (abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol
            and abs(a.width() - b.width()) < tol and abs(a.height() - b.height()) < tol)


def test_rotated_rect_halo_matches_rendered_footprint(qapp):
    sc = Model_Space()
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))   # two opposite corners
    sc.addItem(r)
    r.set_angle(45.0)                                      # baked-at-rest rotation
    # The HALO path must match the item's actual rendered footprint
    # (sceneBoundingRect = sceneTransform.mapRect(boundingRect) = rotated footprint):
    assert _approx_rect(halo_scene_path(r).boundingRect(), r.sceneBoundingRect())
    # And it must DIFFER from the old double-transformed path (proves the bug/fix):
    old = r.mapToScene(r.shape()).boundingRect()
    assert not _approx_rect(old, r.sceneBoundingRect())


def test_unrotated_rect_halo_ok(qapp):
    sc = Model_Space()
    r = RectangleItem(QPointF(10, 10), QPointF(90, 50))
    sc.addItem(r)
    assert _approx_rect(halo_scene_path(r).boundingRect(), r.sceneBoundingRect())
