"""DM smoke round 2 -- the retired Scale / Font columns: a saved scale or font
(QSettings current + default keys, project payload, per-item override) is never
applied; the factory value is. Drives the real load paths on real scene items
(QSettings is isolated by conftest)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings

from firepro3d.display_manager import (
    _CATEGORY_MAP, DisplayManager, apply_default_display_settings,
    apply_project_display_settings, apply_saved_display_settings,
    get_display_settings_for_save)
from firepro3d.model_space import Model_Space

_BAD_SCALE, _BAD_FONT = 3.0, 24


def _seed_stale_values(ms, spr, marker, detail):
    s = QSettings("GV", "FirePro3D")
    for key in ("Sprinkler", "Detail Marker", "Elevation Marker"):
        for prefix in ("", "default_"):
            s.setValue(f"display/{key}/{prefix}scale", _BAD_SCALE)
    for key in ("Detail Marker", "Elevation Marker"):
        for prefix in ("", "default_"):
            s.setValue(f"display/{key}/{prefix}font", _BAD_FONT)
    for it in (spr, marker, detail):
        it._display_overrides = {"scale": _BAD_SCALE, "font": _BAD_FONT, "opacity": 50}
    return {"Sprinkler": {"scale": _BAD_SCALE},
            "Elevation Marker": {"scale": _BAD_SCALE, "font": _BAD_FONT},
            "Detail Marker": {"scale": _BAD_SCALE, "font": _BAD_FONT}}


@pytest.fixture()
def scene(qapp):
    from firepro3d.detail_view import DetailMarker
    from firepro3d.section_marker import SectionMarker
    ms = Model_Space()
    node = ms.add_node(0, 0)
    ms.add_sprinkler(node)
    marker = SectionMarker("Section 1", QPointF(0, 0), QPointF(100, 0))
    ms.addItem(marker)
    detail = DetailMarker("D1", QRectF(0, 0, 400, 300))
    ms.addItem(detail)
    return ms, node.sprinkler, marker, detail


def _factory_width(spr):
    spr._display_scale = 1.0
    spr._centre_on_node()
    return spr.sceneBoundingRect().width()


def _assert_factory(spr, marker, detail, factory_w):
    assert spr.sceneBoundingRect().width() == pytest.approx(factory_w)   # rendered size
    assert spr._display_scale == 1.0
    assert detail.scale() == 1.0
    assert marker._display_scale == 1.0
    assert marker._display_font_size == _CATEGORY_MAP["Elevation Marker"]["font"]


def test_positive_control_a_scale_does_change_the_rendered_size(scene):
    ms, spr, marker, detail = scene
    w1 = _factory_width(spr)
    spr._display_scale = _BAD_SCALE
    spr._centre_on_node()
    assert spr.sceneBoundingRect().width() == pytest.approx(w1 * _BAD_SCALE)


@pytest.mark.parametrize("path", ["saved", "project", "default"])
def test_stored_scale_and_font_are_not_applied(scene, path):
    ms, spr, marker, detail = scene
    factory_w = _factory_width(spr)
    payload = _seed_stale_values(ms, spr, marker, detail)
    if path == "saved":
        apply_saved_display_settings(ms)
    elif path == "project":
        apply_project_display_settings(ms, payload)
    else:
        apply_default_display_settings(ms)
    _assert_factory(spr, marker, detail, factory_w)
    if path != "default":       # the default path ignores per-item overrides by design
        assert marker.opacity() == pytest.approx(0.5)   # override path still runs for its other keys


def test_save_paths_no_longer_write_scale_or_font(scene):
    ms, spr, marker, detail = scene
    s = QSettings("GV", "FirePro3D")
    for k in list(s.allKeys()):
        if k.endswith(("/scale", "/font", "/default_scale", "/default_font")):
            s.remove(k)
    assert all("scale" not in e and "font" not in e
               for e in get_display_settings_for_save().values())
    dlg = DisplayManager(ms)
    try:
        dlg._set_model_as_default()
        dlg._apply_preview()
    finally:
        dlg.reject()
    written = [k for k in s.allKeys()
               if k.startswith("display/") and k.endswith(
                   ("/scale", "/font", "/default_scale", "/default_font"))]
    assert written == []
