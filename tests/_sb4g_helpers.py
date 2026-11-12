"""SB4g guard helpers (shared by T7-T14): user symbol blocks, a shown-view ink
measure, scene builders, renders, and the riser scene.

Raw colour sources: graphics/sprinkler_graphics/sprinkler0.svg (circle fill
#2e2e2e, stroke #ffffff) and water_supply.svg (circle fill #2b2b2e, stroke
#ffffff) -- the seeds convert them faithfully (design D9, T4)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space

BG = 0xFF101010
SPR0_FILL = "#2e2e2e"          # sprinkler0.svg circle fill
WS_FILL = "#2b2b2e"            # water_supply.svg circle fill
SPR_IDS = ("system-symbols-sprinkler0", "system-symbols-sprinkler1",
           "system-symbols-sprinkler2")
WS_ID = "system-symbols-watersupply"
RISER_ID = "system-symbols-riser"


# -- user symbol blocks -----------------------------------------------------
def _circle_symbol(scene, diameter, category="Sprinkler"):
    """A project user symbol block: one circle of *diameter* mm (named
    weight), real size, flagged ``symbol_for`` *category*."""
    d = BlockDefinition.new(name=f"Sym{diameter}", library="Test", series="Symbols",
                            primitives=[CircleItem(QPointF(0, 0), diameter / 2.0).to_dict()],
                            origin=(0.0, 0.0))
    d.symbol_for = category
    scene.register_block_definition(d)
    return d


def lib_symbol(root, name, block_id, symbol_for, *, annotative=False,
               library="Styles", series="Symbols", prims=None):
    """A user-library .fpdb: a real-size (or annotative) block flagged
    ``symbol_for`` (design D7 / R10). Default primitive: one 200 mm line."""
    d = BlockDefinition.new(
        name=name, library=library, series=series, origin=(0.0, 0.0),
        primitives=prims or [LineItem(QPointF(-100.0, 0.0), QPointF(100.0, 0.0)).to_dict()])
    d.scale_mode = "annotative" if annotative else "real_size"
    d.symbol_for = symbol_for
    d.id = block_id
    folder = Path(root) / library / series
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.fpdb"
    path.write_text(json.dumps(d.to_dict()), encoding="utf-8")
    return str(path)


# -- shown-view ink ---------------------------------------------------------
def ink_extent_mm(view, item):
    """Scene-mm width/height of the pixels *item* changes in the SHOWN view
    (grab with the item visible vs hidden), so the canvas background and grid
    cancel out. Returns (0, 0) when nothing differs."""
    QApplication.processEvents()
    on = view.viewport().grab().toImage()
    item.setVisible(False)
    QApplication.processEvents()
    off = view.viewport().grab().toImage()
    item.setVisible(True)
    QApplication.processEvents()
    dpr = on.devicePixelRatio()
    xs, ys = [], []
    for y in range(on.height()):
        for x in range(on.width()):
            if on.pixel(x, y) != off.pixel(x, y):
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0.0, 0.0
    k = view.transform().m11() * dpr          # device px per scene mm
    return (max(xs) - min(xs) + 1) / k, (max(ys) - min(ys) + 1) / k


# -- scene builders + renders -------------------------------------------------
def scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def head(ms, x=0.0, y=0.0):
    n = ms.add_node(x, y)
    return n, ms.add_sprinkler(n)


def water_supply(ms, x=0.0, y=0.0):
    """The deserialize_water_supply registration (network_codec)."""
    from firepro3d.water_supply import WaterSupply
    ws = WaterSupply(x, y)
    ms.addItem(ws)
    ms.water_supply_node = ws
    ms.sprinkler_system.supply_node = ws
    return ws


def render(ms, rect: QRectF, w=400, h=400, bg=BG) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(bg)
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def names(img: QImage) -> set:
    return {QColor(img.pixel(x, y)).name()
            for x in range(img.width()) for y in range(img.height())}


# -- riser --------------------------------------------------------------------
def riser_scene():
    """The tests/test_visibility_display.py riser idiom: two nodes at one XY."""
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    ms = scene()
    nodes = []
    for z in (3000.0, 0.0):
        n = Node(0.0, 0.0)
        ms.addItem(n)
        n.z_pos = z
        ms.sprinkler_system.add_node(n)
        nodes.append(n)
    p = Pipe(*nodes)
    ms.addItem(p)
    ms.sprinkler_system.add_pipe(p)
    for n in nodes:
        n.fitting.type = n.fitting.determine_type(n.pipes)
    p.update_label()
    assert p._properties["Line Type"]["value"] == "Branch"
    assert p._riser_symbol is not None and p._riser_symbol.isVisible()
    return ms, nodes, p


def ring_hits(ms, colour: QColor):
    """Pixels of *colour* outside the pipe's own round-cap dot (radius
    Pipe.BRANCH_WIDTH_MM / 2 + 5 mm) -- only the riser ring (r 69.64 mm, R14) lies there."""
    from firepro3d.pipe import Pipe
    img = render(ms, QRectF(-100.0, -100.0, 200.0, 200.0), 400, 400)   # 2 px / mm
    excl = Pipe.BRANCH_WIDTH_MM / 2.0 + 5.0
    want = colour.rgb()
    return sum(1 for x in range(400) for y in range(400)
               if math.hypot((x - 200) / 2.0, (y - 200) / 2.0) > excl
               and img.pixel(x, y) == want)
