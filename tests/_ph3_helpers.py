"""Shared builders for the PH3 sheet-phasing guards (tests/test_ph3_*.py).

Every guard renders a real PaperScene viewport through SheetViewport.paint (VC3).
Raw sources the expected values cite:
- status graphics: constants.PHASE_EXISTING_COLOUR "#808080" and
  constants.PHASE_EXISTING_FILL "#D3D3D3" (D-PH10 factory, phase_registry.factory_statuses);
- weights: paper_display.DEFAULT_LINE_WEIGHTS (LW-DC-1 factory: "Extra Thick" = 1.00 mm,
  "Fine" = 0.25 mm);
- geometry: SCALE (paper mm per model mm) and PX (image px per paper mm) below.
The resolver is a ``MagicMock(spec=ViewResolver)`` resolving to ``(scene, crop)``
(tests/_section_paper_helpers.export_scene idiom): no level isolation runs.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.phase_display import PhaseDisplay

PX = 10                                   # image px per paper mm
SCALE = 0.01                              # a 1:100 viewport
CROP = QRectF(-1000.0, -1000.0, 8000.0, 6000.0)   # model mm -> an 80 x 60 mm box
WHITE = QColor("#ffffff").rgb()
EXISTING_GREY = 0x80                      # PHASE_EXISTING_COLOUR "#808080" (constants.py)
EXISTING_FILL = "#d3d3d3"                 # PHASE_EXISTING_FILL "#D3D3D3" as QColor.name()
TOL = 4                                   # channel tolerance (no antialiasing on these paths)


def viewport_data(kind="plan", crop=CROP, phase_display=None, name="Plan: Level 1"):
    """A SheetViewData whose box is exactly ``crop x SCALE`` (no border)."""
    from firepro3d.paper_space import SheetViewData
    d = SheetViewData(kind, name, "T", SCALE, 10.0, 10.0,
                      crop.width() * SCALE, crop.height() * SCALE,
                      show_border=False, crop_rect=QRectF(crop))
    if phase_display is not None:
        d.phase_display = phase_display
    return d


def add_viewport(scene, data):
    """``(paper scene, viewport)``: *data* placed on a new sheet, showing *scene*
    cropped to ``data.crop_rect``."""
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    rect = QRectF(data.crop_rect)
    res = MagicMock(spec=ViewResolver)
    res.resolve.side_effect = lambda vt, vn: (scene, QRectF(rect))
    res.display_name.side_effect = lambda vt, vn: vn
    ps = PaperScene(Sheet.create_default(), res)
    vp = ps.add_viewport(data)
    assert vp._placeholder is False
    return ps, vp


def make_viewport(scene, **kw):
    """``add_viewport(scene, viewport_data(**kw))``."""
    return add_viewport(scene, viewport_data(**kw))


def phasing(*hidden):
    """Phasing on, the given status ids hidden."""
    return PhaseDisplay(enabled=True, hidden=frozenset(hidden))


def render(vp) -> QImage:
    """The viewport painted on white at PX px per paper mm (the sheet's own paint)."""
    img = QImage(int(round(vp.data.w * PX)), int(round(vp.data.h * PX)),
                 QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.scale(PX, PX)
    vp.paint(p, None, None)
    p.end()
    return img


def to_px(vp, x, y):
    """Image px of model point (x, y) in *vp*'s render."""
    crop = vp._effective_crop()
    return (int((x - crop.left()) * SCALE * PX), int((y - crop.top()) * SCALE * PX))


def model_box(vp, rect, inset=0.0):
    """Image px box ``(x0, y0, x1, y1)`` (exclusive ends) of model *rect*, shrunk
    by *inset* (a fraction of each side) to stay clear of outlines."""
    r = QRectF(rect).adjusted(rect.width() * inset, rect.height() * inset,
                              -rect.width() * inset, -rect.height() * inset)
    x0, y0 = to_px(vp, r.left(), r.top())
    x1, y1 = to_px(vp, r.right(), r.bottom())
    return (x0, y0, x1 + 1, y1 + 1)


def pixels(img, box=None):
    """Every QColor of *img* inside px *box* (clipped), else the whole image."""
    x0, y0, x1, y1 = box if box is not None else (0, 0, img.width(), img.height())
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.width(), x1), min(img.height(), y1)
    return [QColor(img.pixel(x, y)) for y in range(y0, y1) for x in range(x0, x1)]


def inked(colours):
    """The non-white colours."""
    return [c for c in colours if c.rgb() != WHITE]


def is_grey(c, tol=TOL) -> bool:
    return max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) <= tol


def near(c, value, tol=TOL) -> bool:
    return all(abs(ch - value) <= tol for ch in (c.red(), c.green(), c.blue()))


def darkest(colours):
    return min(colours, key=lambda c: c.red() + c.green() + c.blue())


def assert_status_grey(colours):
    """Ink exists, every inked pixel is grey, and the darkest is the Existing
    colour #808080 (a black row colour or an authored hue fails)."""
    ink = inked(colours)
    assert ink, "nothing plotted"
    off = sorted({c.name() for c in ink if not is_grey(c)})
    assert not off, off[:8]
    d = darkest(ink)
    assert near(d, EXISTING_GREY), d.name()


def set_status(sid, **graphics):
    """Set status *sid*'s graphics slots in the live registry (None = "--")."""
    from firepro3d import phase_registry
    for key, value in graphics.items():
        assert phase_registry.project_table().set_graphic(sid, key, value)


def set_row(key, **vals):
    """Write paper category row *key* (the store the pass reads), e.g. opacity=60."""
    from firepro3d import paper_display as pd
    cats = pd.load_paper_categories()
    cats[key].update(vals)
    pd.save_paper_categories(cats)


def fill_block(ms, at=(1000.0, 1000.0)):
    """A placed block: one 1000 x 600 mm rectangle, red stroke, yellow solid fill."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.fill_layers import BackgroundLayer, FillLayers
    from firepro3d.geometry_2d import RectangleItem
    r = RectangleItem(QPointF(0.0, 0.0), QPointF(1000.0, 600.0))
    r.style["colour"] = "#ff0000"
    r.fill_layers = FillLayers(background=BackgroundLayer("#ffff00", 1.0))
    d = BlockDefinition.new(name="PH3Fill", library="L", series="S",
                            primitives=[r.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return ms.place_block_instance(d.id, at)


def underlay(ms, phase):
    """A DXF underlay record + group: one 4000 mm A-WALL line, red layer
    override, "Extra Thick" (1.00 mm) so it plots a solid 10 px band."""
    from tests.test_underlay_display import _record
    rec = _record(layer_overrides={"A-WALL": {"colour": "#ff0000"}},
                  line_weight_name="Extra Thick")
    rec.phase = phase
    group, _ = ms._build_batched_underlay_group(
        [{"kind": "line", "x1": 0, "y1": 3000, "x2": 4000, "y2": 3000, "layer": "A-WALL"}],
        rec)
    ms.underlays.append((rec, group))
    return rec, group
