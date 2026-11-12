"""SB4g T7: SymbolBlockItem paints a definition's ops at real size (design D3)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem
from tests._sb4g_helpers import _circle_symbol, ink_extent_mm


def test_item_resolves_its_chosen_block_and_reports_real_extent(shown_model_view):
    from firepro3d.symbol_block import SymbolBlockItem
    _view, scene = shown_model_view
    d = _circle_symbol(scene, 300.0)
    item = SymbolBlockItem("Sprinkler")
    item.set_symbol_block(d.id)
    scene.addItem(item)
    assert item.category == "Sprinkler"
    assert item.definition() is d
    # raw source: the circle above, radius 300 / 2 (named weight: no stroke pad)
    assert item.extent_radius() == pytest.approx(150.0, abs=0.01)
    assert item.boundingRect().contains(QRectF(-150, -150, 300, 300))


def test_item_paints_its_ops_at_real_size_in_a_shown_view(shown_model_view):
    from firepro3d.symbol_block import SymbolBlockItem
    view, scene = shown_model_view                # fixture zoom 0.25 px / mm
    d = _circle_symbol(scene, 300.0)
    item = SymbolBlockItem("Sprinkler")
    item.set_symbol_block(d.id)
    scene.addItem(item)
    w, h = ink_extent_mm(view, item)
    # 300 mm circle; +-1 device px of AA each side = 8 mm at 0.25
    assert w == pytest.approx(300.0, abs=10.0)
    assert h == pytest.approx(300.0, abs=10.0)


def test_stroke_tint_recolours_pixels_and_unset_is_authored(shown_model_view):
    from firepro3d.symbol_block import SymbolBlockItem
    view, scene = shown_model_view
    d = _circle_symbol(scene, 300.0)
    item = SymbolBlockItem("Sprinkler")
    item.set_symbol_block(d.id)
    scene.addItem(item)

    def reds():
        QApplication.processEvents()
        img = view.viewport().grab().toImage()
        # The 1 px cosmetic stroke is anti-aliased onto the canvas, so no pixel
        # is pure #ff0000: count clearly red-dominant pixels instead.
        n = 0
        for y in range(img.height()):
            for x in range(img.width()):
                c = QColor(img.pixel(x, y))
                if c.red() > c.green() + 60 and c.red() > c.blue() + 60:
                    n += 1
        return n

    item.set_tint("#ff0000", None)
    assert reds() > 0
    item.set_tint(None, None)
    assert reds() == 0
    item.set_tint("#ffffff", None)                # today's rule: white = authored
    assert reds() == 0


def test_no_resolvable_block_paints_nothing(shown_model_view):
    """Empty System tier (conftest isolation) + no chosen id -> no ops."""
    from firepro3d.symbol_block import SymbolBlockItem
    view, scene = shown_model_view
    item = SymbolBlockItem("Sprinkler")
    scene.addItem(item)
    assert item.definition() is None
    assert item.extent_radius() == 0.0
    assert item.boundingRect().isEmpty()
    assert ink_extent_mm(view, item) == (0.0, 0.0)


def test_refresh_re_resolves_a_replaced_definition(shown_model_view):
    from firepro3d.symbol_block import SymbolBlockItem
    _view, scene = shown_model_view
    d = _circle_symbol(scene, 300.0)
    item = SymbolBlockItem("Sprinkler")
    item.set_symbol_block(d.id)
    scene.addItem(item)
    assert item.extent_radius() == pytest.approx(150.0, abs=0.01)
    bigger = BlockDefinition.from_dict(d.to_dict())
    bigger.primitives = [CircleItem(QPointF(0, 0), 250.0).to_dict()]
    scene.register_block_definition(bigger)       # same id, new object
    item.refresh()
    assert item.extent_radius() == pytest.approx(250.0, abs=0.01)


def test_owner_geometry_is_announced_before_the_extent_changes(shown_model_view):
    """S4: the owner's prepareGeometryChange runs while the OLD extent is still
    cached (Qt reads the old bounds at that call)."""
    from firepro3d.symbol_block import SymbolBlockItem
    from PyQt6.QtWidgets import QGraphicsRectItem
    _view, scene = shown_model_view
    d = _circle_symbol(scene, 300.0)
    seen = []

    class Owner(QGraphicsRectItem):
        def prepareGeometryChange(self):
            seen.append(item.extent_radius())       # the extent at announce time
            super().prepareGeometryChange()

    owner = Owner()
    scene.addItem(owner)
    item = SymbolBlockItem("Sprinkler", owner=owner)
    item.set_symbol_block(d.id)
    scene.addItem(item)
    assert item.extent_radius() == pytest.approx(150.0, abs=0.01)
    seen.clear()
    item.set_symbol_block(None)                   # -> nothing resolves (empty System tier)
    assert seen == [pytest.approx(150.0, abs=0.01)]
    assert item.extent_radius() == 0.0
