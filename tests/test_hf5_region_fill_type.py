"""HF5 Task 3 -- region fill_type + sparse overrides (R2/R3)."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import fill_types as ft
from firepro3d.constants import TOKEN_ELEMENT
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer, to_record
from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))
BLUE = FillLayers(BackgroundLayer("#0000ff", 1.0))


# -- helpers copied verbatim from tests/test_filled_region.py ----------------
def _render(scene, area=QRectF(0, 0, 120, 120), size=120) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), area)
    p.end()
    return img


def _px(img, x, y) -> QColor:
    return QColor(img.pixel(x, y))


def _is_white(c: QColor) -> bool:
    return c.red() > 250 and c.green() > 250 and c.blue() > 250


def square_pieces(size=100.0):
    a, b, c, d = QPointF(10, 10), QPointF(10 + size, 10), QPointF(10 + size, 10 + size), QPointF(10, 10 + size)
    return [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]


def editor_scene():
    """A Block Editor scene (containment C1) -- the only scene that holds regions."""
    return Model_Space(scene_role="block_editor")


def add_region(scene, region):
    scene.addItem(region)
    scene._filled_regions.append(region)
    return region
# ---------------------------------------------------------------------------


def _square():
    """100x100 square at (10,10), no islands."""
    return FilledRegionItem.from_pieces([square_pieces()])


def _rgb(img, x, y):
    return _px(img, x, y).getRgb()[:3]


def _typed_table():
    t = ft.FillTypeTable([ft.FillType("red", "Red", RED)])
    ft.set_project_table(t)
    return t


def test_typed_region_paints_the_type_and_follows_a_restyle(qapp):
    t = _typed_table()
    sc = editor_scene()
    r = add_region(sc, _square())
    r.set_fill_type("red")
    img = _render(sc)
    assert _rgb(img, 30, 30) == (255, 0, 0) and _is_white(_px(img, 5, 5))
    t.replace(ft.FillType("red", "Red", BLUE))
    ft.notify_changed()
    r.update()
    assert _rgb(_render(sc), 30, 30) == (0, 0, 255)


def test_record_is_sparse_and_round_trips(qapp):
    _typed_table()
    r = _square()
    r.set_fill_type("red")
    assert "fill" not in r.to_dict() and r.to_dict()["fill_type"] == "red"
    r.fill_layers = FillLayers(BackgroundLayer("#ff0000", 0.5))
    d = r.to_dict()
    assert d["fill"] == {"background": {"opacity": 0.5}}
    back = FilledRegionItem.from_dict(d)
    assert back.fill_type == "red" and back.fill_layers == r.fill_layers


def test_custom_region_record_unchanged(qapp):
    r = _square()
    r.fill_layers = RED
    d = r.to_dict()
    assert "fill_type" not in d and d["fill"] == to_record(RED)
    assert FilledRegionItem.from_dict(d).to_dict() == d          # R2: legacy bytes stable


def test_picking_custom_copies_the_resolved_look(qapp):
    _typed_table()
    r = _square()
    r.set_fill_type("red")
    r.set_fill_type(None)
    assert r.fill_type is None and r.fill_layers == RED
    assert r.to_dict()["fill"] == to_record(RED)


def test_picking_a_type_clears_overrides(qapp):
    _typed_table()
    r = _square()
    r.set_fill_type("red")
    r.fill_layers = FillLayers(BackgroundLayer("#ff0000", 0.5))
    r.set_fill_type("red")
    assert "fill" not in r.to_dict()


def test_missing_type_draws_fallback(qapp):
    ft.set_project_table(ft.FillTypeTable())
    r = _square()
    r.set_fill_type("gone")
    assert r.fill_layers == ft.FALLBACK_LAYERS and r.fill_type_missing


def test_by_element_pattern_uses_region_colour(qapp):
    pat = FillLayers(None, PatternLayer("diagonal", TOKEN_ELEMENT, 1.0, 1.0))
    ft.set_project_table(ft.FillTypeTable([ft.FillType("e", "E", pat)]))
    r = _square()
    r.set_fill_type("e")
    r.style["colour"] = "#00ff00"
    c = r._layer_qcolor(TOKEN_ELEMENT, 1.0)
    assert c.rgb() == QColor("#00ff00").rgb()       # the region's stroke colour, not the token
    r.style["colour"] = "#0000ff"
    assert r._layer_qcolor(TOKEN_ELEMENT, 1.0).rgb() == QColor("#0000ff").rgb()


def test_duplicate_named_row_realiases_regions_to_first_type(qapp):
    """Group A review I1: a name-duplicate row's regions resolve to the kept type."""
    rows = [{"id": "keep", "name": "Red", "background": {"color": "#ff0000", "opacity": 1.0}},
            {"id": "dup", "name": "red", "background": {"color": "#0000ff", "opacity": 1.0}}]
    table = ft.FillTypeTable.from_payload(rows)
    assert len(table.all()) == 1
    assert table.get("dup") is table.get("keep")
    assert table.copy().get("dup").id == "keep"
    ft.set_project_table(table)
    sc = editor_scene()
    r = add_region(sc, _square())
    r.set_fill_type("dup")
    assert not r.fill_type_missing and r.fill_type == "dup"      # saved id untouched
    assert r.to_dict()["fill_type"] == "dup"
    assert _rgb(_render(sc), 30, 30) == (255, 0, 0)
    assert ft.resolve("dup", {}, table)[1] is False
