"""A text's box (border + fill) renders inside a placed block (block-system
text compile; linetypes.md WM-12 border half) -- static and field texts."""
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition, _local_path  # noqa: F401
from firepro3d.model_space import Model_Space
from firepro3d.render_op import FILL, STROKE
from firepro3d.text_item import TextItem

_PX = 400                     # image side (px)
_SRC = QRectF(-500, -1500, 4000, 4000)   # scene crop rendered into the image


def _prim(text, **kw):
    d = {"type": "text", "text": text, "x": 0.0, "y": 0.0, "height_mm": 500.0,
         "color": "#ffffff", "border": True, "border_weight": "Thick"}
    d.update(kw)
    return d


def _place(prim, overrides=None):
    ms = Model_Space()
    d = BlockDefinition.new(name="T", library="", series="", origin=(0.0, 0.0),
                            primitives=[prim])
    d.attributes = [normalise_attr({"key": "W", "default": "D1"})]
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level,
                                   overrides=overrides)
    return ms, inst


def _box(prim):
    """The authored box in scene coords (instance at the origin, no pose)."""
    it = TextItem.from_dict(prim)
    return it.mapRectToParent(it._box_rect_local())


def _render(ms):
    img = QImage(_PX, _PX, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, _PX, _PX), _SRC)
    p.end()
    return img


def _px(x, y):
    k = _PX / _SRC.width()
    return int((x - _SRC.left()) * k), int((y - _SRC.top()) * k)


def _lit_near(img, x, y, r=2):
    cx, cy = _px(x, y)
    return any(QColor(img.pixel(i, j)).lightness() > 128
               for i in range(cx - r, cx + r + 1) for j in range(cy - r, cy + r + 1))


def _edge_mids(b):
    return [(b.center().x(), b.top()), (b.center().x(), b.bottom()),
            (b.left(), b.center().y()), (b.right(), b.center().y())]


@pytest.mark.parametrize("text", ["AB", "@[W]"])
def test_border_draws_on_the_box_edges(qapp, text):
    prim = _prim(text)
    b = _box(_prim("D1" if text == "@[W]" else text))
    on = _render(_place(prim)[0])
    off = _render(_place(_prim(text, border=False))[0])
    for x, y in _edge_mids(b):
        assert _lit_near(on, x, y), (x, y)
        assert not _lit_near(off, x, y), (x, y)          # control: no border, no frame


@pytest.mark.parametrize("text", ["AB", "@[W]"])
def test_border_op_is_the_box_at_its_weight_and_takes_the_override(qapp, text):
    prim = _prim(text, border_line_type="dashed")
    b = _box(_prim("D1" if text == "@[W]" else text))
    _ms, inst = _place(prim)
    strokes = [op for op in inst.render_ops() if op.kind == STROKE]
    assert len(strokes) == 1
    r = strokes[0].path.boundingRect()
    assert abs(r.left() - b.left()) < 1e-6 and abs(r.right() - b.right()) < 1e-6
    assert abs(r.top() - b.top()) < 1e-6 and abs(r.bottom() - b.bottom()) < 1e-6
    assert strokes[0].weight == "Thick"
    assert strokes[0].pen.style().name == "DashLine"
    _ms, inst = _place(prim, overrides={"weight": "Thin"})
    assert [op.weight for op in inst.render_ops() if op.kind == STROKE] == ["Thin"]


@pytest.mark.parametrize("text", ["AB", "@[W]"])
def test_fill_renders_inside_the_box(qapp, text):
    prim = _prim(text, border=False, fill_color="#ff0000")
    b = _box(_prim("D1" if text == "@[W]" else text))
    ms, inst = _place(prim)
    assert [op.kind for op in inst.render_ops()].count(FILL) == 1
    img = _render(ms)
    # Just inside the top-left corner: box padding, no glyph ink.
    c = QColor(img.pixel(*_px(b.left() + 0.02 * b.width(), b.top() + 0.04 * b.height())))
    assert c.red() > 200 and c.green() < 60 and c.blue() < 60, c.name()


@pytest.mark.parametrize("text", ["AB", "@[W]"])
def test_nested_record_override_reaches_the_child_border(qapp, text):
    from tests.wm2_support import nested_record
    ms = Model_Space()
    child = BlockDefinition.new(name="C", library="", series="", origin=(0.0, 0.0),
                                primitives=[_prim(text)])
    child.attributes = [normalise_attr({"key": "W", "default": "D1"})]
    ms.register_block_definition(child)
    parent = BlockDefinition.new(name="P", library="", series="", origin=(0.0, 0.0),
                                 primitives=[nested_record(child.id, {"weight": "Thin"})])
    ms.register_block_definition(parent)
    inst = ms.place_block_instance(parent.id, (0.0, 0.0), level=ms.active_level)
    assert [op.weight for op in inst.render_ops() if op.kind == STROKE] == ["Thin"]


def test_rotated_box_rotates_with_the_text(qapp):
    prim = _prim("AB", angle=90.0)
    it = TextItem.from_dict(prim)
    want = it.mapToParent(it._rotation_transform().map(it._frame_path())).boundingRect()
    _ms, inst = _place(prim)
    r = [op for op in inst.render_ops() if op.kind == STROKE][0].path.boundingRect()
    assert abs(r.width() - want.width()) < 1e-6 and abs(r.height() - want.height()) < 1e-6
    assert abs(r.center().x() - want.center().x()) < 1e-6
