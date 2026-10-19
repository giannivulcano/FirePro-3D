"""G1 (UP1): legacy solid / hatch fills render identically after the two-layer
change. Goldens are generated on the pre-UP1 tree:

    FP3D_REGEN_UP1_GOLDEN=1 ./venv/Scripts/python.exe -m pytest tests/test_up1_legacy_fill_golden.py

Shapes span several hatch pitches (the shipped diagonal hatch is ~300 mm apart),
rendered at 20 mm per pixel, so the hatch goldens hold real hatch lines; every
render is also checked for content (hatch partly inked, solid fully inked) so a
blank golden cannot pass.

Real paths: ``RectangleItem/CircleItem.from_dict`` + paint, and
``BlockDefinition`` compile + ``BlockInstance`` paint in a ``Model_Space``.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem, RectangleItem

GOLDEN_DIR = Path(__file__).parent / "data" / "up1_legacy_fill"
_SIZE = 160                      # image px
_SPAN = 3200.0                   # scene mm rendered into the image (20 mm/px)
_POS = (5000.0, 5000.0)          # instance away from the origin marker

_RECT = {"type": "draw_rectangle", "x": 200.0, "y": 200.0, "w": 2400.0, "h": 2400.0,
         "color": "#000000", "lineweight": 1.0}
_CIRC = {"type": "draw_circle", "cx": 1400.0, "cy": 1400.0, "radius": 1200.0,
         "color": "#000000", "lineweight": 1.0}

CASES = {
    "rect_solid": dict(_RECT, fill={"type": "solid", "pattern": "diagonal",
                                    "color": "#3366cc", "opacity": 0.45}),
    "rect_hatch_alias": dict(_RECT, fill={"type": "hatch", "pattern": "diagonal",
                                          "color": "#cc3333", "opacity": 0.45}),
    "circle_hatch_full": dict(_CIRC, fill={"type": "hatch",
                                           "pattern": "builtin-hatch-diagonal",
                                           "color": "#228822", "opacity": 1.0}),
    "rect_solid_defaults": dict(_RECT, fill={"type": "solid"}),
}
_FACTORY = {"draw_rectangle": RectangleItem, "draw_circle": CircleItem}

# Central 50x50 px square (scene 900..1900 mm): strictly inside both shapes.
_INNER = range(45, 95)


def _render(scene, src: QRectF) -> QImage:
    img = QImage(_SIZE, _SIZE, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, _SIZE, _SIZE), src)
    p.end()
    return img


def _scene(qapp, shipped_hatches):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    shipped_hatches(ms)
    return ms


def _assert_content(case: str, img: QImage) -> None:
    """A hatch interior is partly inked; a solid interior is fully inked."""
    white = QColor("white").rgba()
    inked = sum(1 for y in _INNER for x in _INNER if img.pixel(x, y) != white)
    total = len(_INNER) ** 2
    if CASES[case]["fill"]["type"] == "hatch":
        assert 0 < inked < total, f"{case}: hatch interior inked {inked}/{total}"
    else:
        assert inked == total, f"{case}: solid interior inked {inked}/{total}"


def _check(name: str, img: QImage) -> None:
    path = GOLDEN_DIR / f"{name}.png"
    if os.environ.get("FP3D_REGEN_UP1_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        assert img.save(str(path))
        return
    want = QImage(str(path)).convertToFormat(img.format())
    assert not want.isNull(), f"missing golden {path}"
    assert img == want, f"{name}: pixels differ from the pre-UP1 golden"


@pytest.mark.parametrize("case", sorted(CASES))
def test_loose_shape_legacy_fill_matches_golden(qapp, shipped_hatches, case):
    ms = _scene(qapp, shipped_hatches)
    prim = CASES[case]
    item = _FACTORY[prim["type"]].from_dict(prim)
    ms.addItem(item)
    img = _render(ms, QRectF(0, 0, _SPAN, _SPAN))
    _assert_content(case, img)
    _check(f"{case}__loose", img)


@pytest.mark.parametrize("case", sorted(CASES))
def test_block_instance_legacy_fill_matches_golden(qapp, shipped_hatches, case):
    ms = _scene(qapp, shipped_hatches)
    d = BlockDefinition.new(name="G1", library="L", series="S",
                            origin=(0.0, 0.0), primitives=[CASES[case]])
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, _POS)
    img = _render(ms, QRectF(_POS[0], _POS[1], _SPAN, _SPAN))
    _assert_content(case, img)
    _check(f"{case}__block", img)
