"""SB4g T8-T10: Sprinkler, WaterSupply and the riser draw from symbol blocks
at real size (G1, G3, G8, AC10). Shipped seeds need ``real_system_library``."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import QGraphicsItem

from firepro3d.constants import RISER_SYMBOL_SIZE_MM, Z_SPRINKLER
from firepro3d.node import Node
from firepro3d.symbol_block import SymbolBlockItem
from tests._sb4g_helpers import _circle_symbol, ink_extent_mm

# Raw sources: Sprinkler.TARGET_MM = 24.0 * 25.4 at 119fbbf0 (sprinkler.py:24,
# water_supply.py:37) and RISER_SYMBOL_SIZE_MM = 150 map each SVG's 20-unit viewBox
# (K = size / 20). R14: strokes are By Linetype centre lines, so a seed's extent is
# its centre-line geometry: 2 x the circle r of the SVG, or sprinkler2's full-span
# hairlines (0.22619057 .. 20.226191).
HEAD_MM = 24.0 * 25.4                       # 609.6 (today's SVG box)
RISER_MM = RISER_SYMBOL_SIZE_MM             # 150 (today's SVG box; the unresolved fallback)
KH, KR = HEAD_MM / 20.0, RISER_MM / 20.0
EXTENT_MM = {
    "system-symbols-sprinkler0": 2 * 9.51192 * KH,                 # 579.847 (sprinkler0.svg)
    "system-symbols-sprinkler1": 2 * 9.7560978 * KH,               # 594.732 (sprinkler1.svg)
    "system-symbols-sprinkler2": (20.226191 - 0.22619057) * KH,    # 609.600 (sprinkler2.svg)
    "system-symbols-watersupply": 2 * 9.51192 * KH,                # 579.847 (water_supply.svg)
    "system-symbols-riser": 2 * 9.2852659 * KR,                    # 139.279 (riser_passthrough.svg)
}
INK_TOL = 10.0                              # +-1 device px AA each side at zoom 0.25


def _head(scene, x=0.0, y=0.0):
    n = Node(x, y)
    scene.addItem(n)
    scene.sprinkler_system.add_node(n)
    n.add_sprinkler()
    return n


@pytest.mark.parametrize("block_id", [None, "system-symbols-sprinkler1",
                                      "system-symbols-sprinkler2"],
                         ids=["sprinkler0-default", "sprinkler1", "sprinkler2"])
def test_g1_sprinkler_draws_its_block_at_real_size(shown_model_view, real_system_library,
                                                    block_id):
    view, scene = shown_model_view
    node = _head(scene)
    spr = node.sprinkler
    if block_id is not None:
        spr.set_symbol_block(block_id)
    assert isinstance(spr, SymbolBlockItem) and not isinstance(spr, QGraphicsSvgItem)
    want = block_id or "system-symbols-sprinkler0"
    assert spr.definition() is not None and spr.definition().id == want
    assert spr.extent_radius() * 2 == pytest.approx(EXTENT_MM[want], abs=0.01)
    w, h = ink_extent_mm(view, spr)
    assert w == pytest.approx(EXTENT_MM[want], abs=INK_TOL)
    assert h == pytest.approx(EXTENT_MM[want], abs=INK_TOL)


def test_g3_user_symbol_300mm_and_node_shape_follow_it(shown_model_view):
    view, scene = shown_model_view
    node = _head(scene)
    d = _circle_symbol(scene, 300.0, "Sprinkler")
    node.sprinkler.set_symbol_block(d.id)
    assert node.sprinkler.extent_radius() == pytest.approx(150.0, abs=0.01)
    w, _h = ink_extent_mm(view, node.sprinkler)
    assert w == pytest.approx(300.0, abs=INK_TOL)
    # Node pick disk = the symbol extent (max with Node.RADIUS = 13)
    assert node.shape().boundingRect().width() / 2.0 == pytest.approx(150.0, abs=0.01)
    # bounds = 1.15 x extent for the selection ring (node.py ratio, kept)
    assert node.boundingRect().width() / 2.0 == pytest.approx(150.0 * 1.15, abs=0.01)
    hits = scene.items(QPointF(140.0, 0.0))
    assert node in hits                          # inside the 150 mm disk
    assert node not in scene.items(QPointF(170.0, 0.0))


def test_ac10_sprinkler_not_selectable_z_kept(shown_model_view, real_system_library):
    _view, scene = shown_model_view
    node = _head(scene)
    spr = node.sprinkler
    assert not (spr.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
    assert spr.parentItem() is node
    assert spr.zValue() == Z_SPRINKLER
    assert node.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def test_unresolved_head_falls_back_to_node_radius(shown_model_view):
    """Empty System tier (broken install): nothing draws, the node keeps a pick disk."""
    _view, scene = shown_model_view
    node = _head(scene)
    assert node.sprinkler.extent_radius() == 0.0
    assert node.shape().boundingRect().width() / 2.0 == pytest.approx(Node.RADIUS)
