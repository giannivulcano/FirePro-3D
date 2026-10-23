"""G7 (wall polish AC6, L42): no selection highlight plots on a sheet, for
every item kind; the canvas still shows it.  Precedent:
tests/test_gridline_paper_scale.py::test_selection_never_plots."""
from __future__ import annotations

import copy
import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsItem

import firepro3d.paper_display as pd

PX_PER_MM = 8
_CROP = QRectF(-1500.0, -1500.0, 3000.0, 3000.0)     # 1:50 into a 60 mm viewport


@pytest.fixture
def paper_env(monkeypatch):
    """Controlled paper settings -- never the real QSettings (copied from
    test_gridline_paper_scale.py's fixture)."""
    env = SimpleNamespace(cats=copy.deepcopy(pd.factory_paper_categories()),
                          mode=pd.PaperColorMode.BW)
    monkeypatch.setattr(pd, "load_paper_categories",
                        lambda settings=None: copy.deepcopy(env.cats))
    monkeypatch.setattr(pd, "load_paper_color_mode",
                        lambda settings=None: env.mode)
    monkeypatch.setattr(pd, "load_line_weights",
                        lambda settings=None: list(pd.FACTORY_LINE_WEIGHTS))
    return env


def _digest(img: QImage) -> str:
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


def _render(scene, rect, w, h, bg=0xFFFFFFFF):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(bg)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect,
                 Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _paper(paper):
    r = paper.sceneRect()
    return _render(paper, r, int(r.width() * PX_PER_MM),
                   int(r.height() * PX_PER_MM))


def _canvas(model):
    return _render(model, _CROP, 600, 600, bg=0xFF101010)


# Each factory adds ONE selectable item of its kind near the origin and
# returns it.  Constructors as used by the existing tests (grep "= <Class>(").
def _wall(s):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(-800, 0), QPointF(800, 0))
    s.addItem(w); s._walls.append(w)
    return w

def _pipe(s):
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    n1, n2 = Node(-800.0, 0.0), Node(800.0, 0.0)
    for n in (n1, n2):
        s.addItem(n)
    p = Pipe(n1, n2)
    s.addItem(p)
    return p

def _node(s):
    from firepro3d.node import Node
    n = Node(0.0, 0.0)
    s.addItem(n)
    n.add_sprinkler()      # a bare node paints nothing off-selection (vacuous)
    return n

def _roof(s):
    from firepro3d.roof import RoofItem
    r = RoofItem(points=[QPointF(-600, -600), QPointF(600, -600),
                         QPointF(600, 600), QPointF(-600, 600)])
    s.addItem(r)
    return r

def _room(s):
    from firepro3d.room import Room
    r = Room(boundary=[QPointF(-600, -600), QPointF(600, -600),
                       QPointF(600, 600), QPointF(-600, 600)])
    s.addItem(r)
    return r

def _slab(s):
    from firepro3d.floor_slab import FloorSlab
    f = FloorSlab(points=[QPointF(-600, -600), QPointF(600, -600),
                          QPointF(600, 600), QPointF(-600, 600)])
    s.addItem(f)
    return f

def _opening(s):
    from firepro3d.wall_opening import WallOpening
    w = _wall(s)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=800.0)
    w.openings.append(op)
    s.addItem(op)
    return op

def _detail(s):
    from firepro3d.detail_view import DetailMarker
    d = DetailMarker("D1", QRectF(-500, -500, 1000, 1000))
    s.addItem(d)
    return d

def _badge(s):
    from firepro3d.hydraulic_node_badge import HydraulicNodeBadge
    n = _node(s)
    return HydraulicNodeBadge(n, 1, 50.0, 40.0, 10.0, 100.0)

def _region(s):
    from firepro3d.filled_region import FilledRegionItem
    from firepro3d.geometry_2d import CircleItem
    r = FilledRegionItem.from_pieces([[CircleItem(QPointF(0, 0), 500.0)]])
    s.addItem(r)
    return r

def _g2d(cls_name, *args, **kw):
    def make(s):
        import firepro3d.geometry_2d as g
        it = getattr(g, cls_name)(*args, **kw)
        s.addItem(it)
        return it
    return make


_KINDS = {
    "wall": _wall, "pipe": _pipe, "node": _node, "roof": _roof,
    "room": _room, "floor_slab": _slab, "wall_opening": _opening,
    "detail_marker": _detail, "hydraulic_badge": _badge,
    "filled_region": _region,
    "line": _g2d("LineItem", QPointF(-800, 0), QPointF(800, 0)),
    "rectangle": _g2d("RectangleItem", QPointF(-600, -400), QPointF(600, 400)),
    "circle": _g2d("CircleItem", QPointF(0, 0), 500.0),
    "arc": _g2d("ArcItem", QPointF(0, 0), 500.0, 0.0, 180.0),
    "polygon": _g2d("RegularPolygonItem", QPointF(0, 0), sides=6,
                    radius_mm=500.0, rotation_deg=0.0),
    "ellipse": _g2d("EllipseItem", QPointF(0, 0), 600.0, 300.0, 0.0),
    "spline": _g2d("SplineItem", [QPointF(-600, 0), QPointF(0, 500),
                                  QPointF(600, 0)]),
}


@pytest.fixture
def sheet(qapp, paper_env):
    from firepro3d.model_space import Model_Space
    from firepro3d.paper_space import (Sheet, SheetViewData, PaperScene,
                                       ViewResolver)
    model = Model_Space()
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (model, QRectF(_CROP))
    sh = Sheet.create_default()
    sh.paper_size = "A4"
    sh.sheet_views = [SheetViewData("plan", "V", "V", 0.02,
                                    65.0, 60.0, 60.0, 60.0)]
    paper = PaperScene(sh, resolver)
    yield SimpleNamespace(model=model, paper=paper)
    paper.dispose()


@pytest.mark.parametrize("kind", list(_KINDS))
def test_selection_never_plots(sheet, kind, monkeypatch):
    # The manipulator frame (a model-only overlay) suppresses the per-item
    # highlight of the shared stroke paths; with it off the highlight runs.
    import firepro3d.filled_region as fr
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "_manip_wraps", lambda item: False)
    monkeypatch.setattr(fr, "_manip_wraps", lambda item: False)
    item = _KINDS[kind](sheet.model)
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, \
        f"{kind} is not selectable -- drop it with a note, do not force it"
    item.setSelected(False)
    canvas_off, paper_off = _digest(_canvas(sheet.model)), _digest(_paper(sheet.paper))
    item.setVisible(False)
    paper_none = _digest(_paper(sheet.paper))
    item.setVisible(True)
    assert paper_off != paper_none, f"{kind} does not plot at all (vacuous)"
    item.setSelected(True)
    assert _digest(_canvas(sheet.model)) != canvas_off, \
        f"{kind}: selection no longer shows on the canvas"
    assert _digest(_paper(sheet.paper)) == paper_off, \
        f"{kind}: selection highlight plots on paper"
