import pytest
from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space
from firepro3d.construction_geometry import EllipseItem


@pytest.fixture
def scene(qapp):
    return Model_Space()


def _add_ellipse(scene):
    e = EllipseItem(QPointF(100, 200), 40, 20, 30.0)
    scene.addItem(e)
    scene._draw_ellipses.append(e)
    return e


def test_ellipse_list_exists(scene):
    assert hasattr(scene, "_draw_ellipses")
    assert scene._draw_ellipses == []


def test_ellipse_capture_restore_roundtrip(scene):
    _add_ellipse(scene)
    state = scene._capture_network()
    _add_ellipse(scene)                      # add a second
    assert len(scene._draw_ellipses) == 2
    scene._restore_network(state)            # restore the 1-ellipse snapshot
    assert len(scene._draw_ellipses) == 1
    e = scene._draw_ellipses[0]
    assert e._rx == 40 and e._ry == 20 and e._rotation_deg == 30.0


def test_ellipse_file_roundtrip(scene, tmp_path):
    _add_ellipse(scene)
    p = tmp_path / "e.fpd"
    scene.save_to_file(str(p))
    s2 = Model_Space()
    s2.load_from_file(str(p))
    assert len(s2._draw_ellipses) == 1
    e = s2._draw_ellipses[0]
    assert e._rx == 40 and e._ry == 20 and e._rotation_deg == pytest.approx(30.0)


def test_ellipse_in_primitive_factory():
    from firepro3d.block_definition import _PRIMITIVE_FACTORY
    assert _PRIMITIVE_FACTORY.get("draw_ellipse") is EllipseItem


def test_ellipse_in_2d_geometry_display_category(scene):
    _add_ellipse(scene)
    # Use the functional collector to verify EllipseItem is included.
    from firepro3d.display_manager import _items_for_category_static
    items = _items_for_category_static(scene, "2D Geometry")
    assert any(isinstance(it, EllipseItem) for it in items)
