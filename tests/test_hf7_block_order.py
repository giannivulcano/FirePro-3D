"""HF7 D5: paint order in the editor and in placed blocks match."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.constants import TOKEN_AUTO
from firepro3d.filled_region import FilledRegionItem
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.geometry_2d import CircleItem, LineItem, PolylineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.render_op import FILL, PATTERN, STROKE


pytestmark = pytest.mark.usefixtures("qapp")    # Model_Space / editor need a QApplication


def _square_region(colour="#ff0000", x0=0.0):
    poly = PolylineItem(QPointF(x0, 0), TOKEN_AUTO, 1.0)
    for p in ((x0 + 100, 0), (x0 + 100, 100), (x0, 100)):
        poly.append_point(QPointF(*p))
    poly.close()
    r = FilledRegionItem.from_pieces([[poly]])
    r.fill_layers = FillLayers(BackgroundLayer(colour, 1.0))
    return r


def _line():
    return LineItem(QPointF(-10, 50), QPointF(110, 50), "#0000ff", 8.0)


def _render(scene, size=120):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0xffffffff)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), QRectF(-10, -10, 120, 120))
    p.end()
    return img


def _placed_pixel(prims):
    proj = Model_Space()
    d = BlockDefinition.new(name="B", library="L", series="S", origin=(0, 0), primitives=prims)
    proj.register_block_definition(d)
    proj.place_block_instance(d.id, (0.0, 0.0))
    return _render(proj).pixelColor(60, 60)


def _editor_pixel(items):
    w = BlockEditorWidget(Model_Space())
    for it in items:
        w._add_primitive(it)
    return _render(w.editor_scene).pixelColor(60, 60)


def test_draw_z_is_sparse():
    assert "draw_z" not in _line().to_dict()


def test_draw_z_round_trips_and_sets_z():
    a = _line()
    a.set_draw_z(-0.5)
    d = a.to_dict()
    assert d["draw_z"] == -0.5
    b = LineItem.from_dict(d)
    assert b.zValue() == -0.5 and b.to_dict()["draw_z"] == -0.5


def test_authored_region_sits_behind_a_line_in_a_placed_block():
    """Primitive lists save lines first: the record order is stroke, fill."""
    px = _placed_pixel([_line().to_dict(), _square_region().to_dict()])
    assert px.blue() > 200 and px.red() < 100


def test_imported_fill_over_a_line_stays_on_top():
    line, region = _line(), _square_region()
    line.set_draw_z(-0.7)
    region.set_draw_z(-0.3)
    px = _placed_pixel([line.to_dict(), region.to_dict()])
    assert px.red() > 200 and px.blue() < 100


def test_editor_and_block_agree():
    line, region = _line(), _square_region()
    line.set_draw_z(-0.7)
    region.set_draw_z(-0.3)
    proj = Model_Space()
    w = BlockEditorWidget(proj)
    w._add_primitive(line)
    w._add_primitive(region)
    px = _render(w.editor_scene).pixelColor(60, 60)
    assert px.red() > 200 and px.blue() < 100


def test_no_region_definition_compiles_in_list_order():
    a, b = _line().to_dict(), LineItem(QPointF(0, 0), QPointF(5, 5)).to_dict()
    d = BlockDefinition.new(name="B", library="L", series="S", origin=(0, 0), primitives=[a, b])
    widths = [op.path.boundingRect().width() for op in d.render_ops()]
    assert widths[0] > 100 and widths[-1] < 10      # a (120 long) then b (5 long)


# -- guards beyond the plan -------------------------------------------------

@pytest.mark.parametrize("region_first", [True, False])
def test_authored_order_does_not_change_pixels_placed_or_in_editor(region_first):
    """(a) Record / add order is irrelevant for authored items: line over region."""
    recs = [_square_region().to_dict(), _line().to_dict()]
    items = [_square_region(), _line()]
    if not region_first:
        recs.reverse()
        items.reverse()
    for px in (_placed_pixel(recs), _editor_pixel(items)):
        assert px.blue() > 200 and px.red() < 100


def _three(order):
    """Three overlapping regions, imported depths low < mid < high; *order* picks the
    record order. Painted top should be the highest depth (blue)."""
    spec = {"low": ("#ff0000", -0.8), "mid": ("#00ff00", -0.5), "high": ("#0000ff", -0.2)}
    out = []
    for k in order:
        r = _square_region(spec[k][0])
        r.set_draw_z(spec[k][1])
        out.append(r)
    return out


@pytest.mark.parametrize("order", [("mid", "high", "low"), ("high", "low", "mid"),
                                   ("low", "high", "mid")])
def test_interleaved_draw_z_paints_in_that_order(order):
    """(b) Imported primitives paint by draw_z, placed and in the editor."""
    items = _three(order)
    placed = _placed_pixel([i.to_dict() for i in items])
    edit = _editor_pixel(_three(order))
    for px in (placed, edit):
        assert px.blue() > 200 and px.red() < 100 and px.green() < 100


def test_region_op_group_is_not_split_by_the_sort():
    """(c) Fill, pattern and outline of one region stay contiguous between the
    neighbours that sort around it."""
    reg = _square_region()
    reg.fill_layers = FillLayers(BackgroundLayer("#ff0000", 1.0),
                                 PatternLayer("hatch_diagonal", "#000000", 1.0, 1.0))
    reg.outline = True
    reg.set_draw_z(-0.5)
    below, above = _line(), _line()
    below.set_draw_z(-0.9)
    above.set_draw_z(-0.1)
    d = BlockDefinition.new(name="B", library="L", series="S", origin=(0, 0),
                            primitives=[above.to_dict(), reg.to_dict(), below.to_dict()])
    kinds = [op.kind for op in d.render_ops()]
    assert kinds[0] == STROKE and kinds[-1] == STROKE
    mid = kinds[1:-1]
    assert mid[0] == FILL and mid[-1] == STROKE and PATTERN in mid
    assert len(kinds) == 2 + len(mid) and len(mid) >= 3


def test_depth_survives_save_and_reopen_in_the_editor():
    """(d) The depth reaches the editor items again after the dict round trip."""
    line, region = _line(), _square_region()
    line.set_draw_z(-0.7)
    region.set_draw_z(-0.3)
    d = BlockDefinition.new(name="B", library="L", series="S", origin=(0, 0),
                            primitives=[line.to_dict(), region.to_dict()])
    d2 = BlockDefinition.from_dict(d.to_dict())
    w = BlockEditorWidget(Model_Space())
    w.seed_from_dicts(list(d2.primitives))
    zs = sorted(it.zValue() for it in w.editor_scene.items()
                if isinstance(it, (LineItem, FilledRegionItem)))
    assert zs == [-0.7, -0.3]
    px = _render(w.editor_scene).pixelColor(60, 60)
    assert px.red() > 200 and px.blue() < 100
    assert _placed_pixel(list(d2.primitives)).red() > 200


def _mk(cls):
    if cls is LineItem:
        return _line()
    if cls is PolylineItem:
        p = PolylineItem(QPointF(0, 0), TOKEN_AUTO, 1.0)
        p.append_point(QPointF(10, 0))
        p.append_point(QPointF(10, 10))
        return p
    if cls is RectangleItem:
        return RectangleItem(QPointF(0, 0), QPointF(10, 10))
    if cls is CircleItem:
        return CircleItem(QPointF(0, 0), 10.0)
    if cls is FilledRegionItem:
        return _square_region()
    raise AssertionError(cls)


@pytest.mark.parametrize("cls", [LineItem, PolylineItem, RectangleItem, CircleItem,
                                 FilledRegionItem])
def test_draw_z_round_trip_each_primitive(cls):
    a = _mk(cls)
    assert "draw_z" not in a.to_dict()
    a.set_draw_z(-0.4)
    d = a.to_dict()
    assert d["draw_z"] == -0.4
    b = cls.from_dict(d)
    assert b.zValue() == -0.4 and b.to_dict()["draw_z"] == -0.4
    c = cls.from_dict(a.to_dict())
    assert c.to_dict() == b.to_dict() or c.to_dict()["draw_z"] == -0.4


def _pinned_definition():
    line, region = _line(), _square_region()
    line.set_draw_z(-0.7)
    region.set_draw_z(-0.3)
    return BlockDefinition.new(name="B", library="L", series="S", origin=(0, 0),
                               primitives=[line.to_dict(), region.to_dict()])


def _depths(d):
    return sorted(p["draw_z"] for p in d.primitives if "draw_z" in p)


def test_draw_z_survives_the_library_round_trip(tmp_path):
    from firepro3d.block_library import load_block_file, save_to_library
    path = save_to_library(_pinned_definition(), str(tmp_path))
    back = load_block_file(path)
    assert back is not None and _depths(back) == [-0.7, -0.3]
    assert _placed_pixel(list(back.primitives)).red() > 200


def test_draw_z_survives_a_project_save_and_load(tmp_path):
    proj = Model_Space()
    d = _pinned_definition()
    proj.register_block_definition(d)
    f = str(tmp_path / "p.fpd")
    proj.save_to_file(f, backup=False)
    fresh = Model_Space()
    fresh.load_from_file(f)
    assert _depths(fresh.get_block_definition(d.id)) == [-0.7, -0.3]


def test_draw_z_survives_editor_undo_and_copy():
    """Undo snapshots and the paste / duplicate path rebuild items from records."""
    d = _pinned_definition()
    w = BlockEditorWidget(Model_Space())
    w.seed_from_dicts(list(d.primitives))
    sc = w.editor_scene
    sc.push_undo_state()
    for it in list(sc.items()):
        if isinstance(it, (LineItem, FilledRegionItem)):
            it.setPos(5, 5)
    sc.push_undo_state()
    sc.undo()
    zs = sorted(it.zValue() for it in sc.items() if isinstance(it, (LineItem, FilledRegionItem)))
    assert zs == [-0.7, -0.3]
    copies = [sc._add_from_dict(p) for p in d.primitives]
    assert sorted(c.zValue() for c in copies) == [-0.7, -0.3]
    assert all(c.to_dict()["draw_z"] == c.zValue() for c in copies)


@pytest.mark.parametrize("cls", [LineItem, PolylineItem, RectangleItem, CircleItem,
                                 FilledRegionItem])
def test_load_prim_keeps_draw_z(cls):
    from firepro3d.block_definition import _load_prim
    a = _mk(cls)
    a.set_draw_z(-0.4)
    assert _load_prim(a.to_dict())["draw_z"] == -0.4
