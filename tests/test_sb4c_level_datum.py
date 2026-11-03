"""SB4c half B -- the level datum head drawn by the "Level" annotation block
(design docs/superpowers/specs/2026-11-03-sb4c-elev-bubble-datum-design.md D3-D5)."""
import hashlib

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QTransform

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition

HEAD_R = 5.0              # test circle radius, authored mm (= the seed, OQ1 option A)
# Non-circular, ORIGIN-ASYMMETRIC test block: a 12 x 6 mm rectangle spanning
# x -4 .. +8, so the ray toward the line's far end (+h) leaves it at 8 mm and the
# opposite ray at 4 mm -- a sign error in the trim direction reads 4, not 8.
SQ_X0, SQ_W, SQ_H = -4.0, 12.0, 6.0
SQ_TRIM = SQ_X0 + SQ_W    # 8.0: the +h exit
BG = 0xFF101010


def _level_def(ms, shape="circle", name="TestLevelHead"):
    """An eligible Level head: Annotative, Scale with zoom, host Level; *shape*
    'circle' = a HEAD_R circle, 'square' = the asymmetric 12 x 6 mm rectangle
    (non-circular trim, sign-pinning); @[Level.Name] above-right,
    @[Level.Elevation] below-right (the seed's layout). Mapped as the project
    default."""
    if shape == "circle":
        geom = {"type": "draw_circle", "cx": 0.0, "cy": 0.0, "radius": HEAD_R,
                "color": "token:auto", "lineweight": 1.0}
    else:
        geom = {"type": "draw_rectangle", "x": SQ_X0, "y": -SQ_H / 2, "w": SQ_W,
                "h": SQ_H, "color": "token:auto", "lineweight": 1.0}
    name_t = {"type": "text", "text": "@[Level.Name]", "x": 6.25, "y": -5.5,
              "height_mm": 3.0, "wrap_width_mm": 30.0, "box_height_mm": 5.0,
              "align": "L", "valign": "B"}
    elev_t = {"type": "text", "text": "@[Level.Elevation]", "x": 6.25, "y": 0.5,
              "height_mm": 2.4, "wrap_width_mm": 30.0, "box_height_mm": 4.0,
              "align": "L", "valign": "T"}
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[geom, name_t, elev_t])
    d.scale_mode = "annotative"
    d.host_category = "Level"
    d.attributes = [
        normalise_attr({"key": "Level.Name", "source": "host", "host_key": "Level.Name",
                        "placeholder": "-"}),
        normalise_attr({"key": "Level.Elevation", "source": "host",
                        "host_key": "Level.Elevation", "placeholder": "-"}),
    ]
    ms.register_block_definition(d)
    ms.annotation_defaults["Level"] = d.id
    return d


def _datum_scene(section_scene_for, shape="circle", direction="north"):
    """(ms, sec, Level 1 datum, definition): a real SectionScene over a real
    Model_Space (LevelManager seeds Level 1 / 2 / 3 at 0 / 3048 / 6096 mm,
    level_manager.DEFAULT_LEVELS), the Level block mapped, rebuilt."""
    from firepro3d.section_scene import ElevDatumItem
    ms, sec = section_scene_for(direction)
    d = _level_def(ms, shape)
    sec.rebuild()
    (dt,) = [i for i in sec.items() if isinstance(i, ElevDatumItem) and abs(i._v) < 1e-6]
    return ms, sec, dt, d


def _render(scene, rect, w, h, bg=BG):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(bg)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _digest(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


# -- T7: registries ----------------------------------------------------------------

def test_level_is_an_element_and_annotation_category(qapp):
    from firepro3d import element_params as ep
    from firepro3d import system_blocks as sb
    assert ep.CATEGORIES[-1] == "Level"
    assert [(k, s.tier, s.kind, s.label) for k, s in ep.PARAMS["Level"].items()] == [
        ("Level.Name", 1, "text", "Name"), ("Level.Elevation", 1, "length", "Elevation")]
    assert sb.ANNOTATION_CATEGORIES == ("Room", "Pipe", "Gridline", "Level")
    assert sb.LABEL_FIELD["Level"] == "Level.Name"
    assert sb.SYSTEM_DEFAULTS["Level"] == "system-tags-leveldatum"
    assert "Level" not in sb.PAINT_WHEN_BLANK


def test_category_of_an_elevation_datum_is_level_and_others_are_unchanged(qapp, section_scene_for):
    from firepro3d import element_params as ep
    from firepro3d.section_scene import ElevDatumItem
    _ms, sec = section_scene_for("north")
    sec.rebuild()
    dts = [i for i in sec.items() if isinstance(i, ElevDatumItem)]
    assert len(dts) == 3                                    # Level 1 / 2 / 3 (DEFAULT_LEVELS)
    assert {ep.category_of(d) for d in dts} == {"Level"}
    assert ep.category_of(object()) is None
