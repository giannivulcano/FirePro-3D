"""Real-object builders shared by the SB4d guards (design
docs/superpowers/specs/2026-11-03-sb4d-view-marker-heads-design.md).
Every builder makes REAL domain objects on a real Model_Space."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QApplication, QTabWidget

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition

HEAD_R = 5.0        # test circle head radius, authored mm
SQ_HALF = 4.0       # test square head half side, authored mm (circumradius 4 * sqrt 2)


def plan_scene():
    """``(ms, sec, det, tabs)``: a Model_Space with LevelManager (Level 1 / 2 / 3
    at 0 / 3048 / 6096 mm, level_manager.DEFAULT_LEVELS) and ScaleManager
    (drawing scale 100), a SectionManager and a DetailViewManager wired the
    way main.py wires them (``ms._section_manager`` / ``ms._detail_manager``)."""
    from firepro3d.detail_view import DetailViewManager
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    ms = Model_Space()
    lm = LevelManager()
    ms._level_manager = lm
    sm = ScaleManager()
    ms.scale_manager = sm
    tabs = QTabWidget()
    sec = SectionManager(ms, lm, sm, tabs)
    ms._section_manager = sec
    det = DetailViewManager(ms, lm, sm, tabs)
    ms._detail_manager = det
    return ms, sec, det, tabs


_PAPER_VIEWS = []        # (view, paper_scene) pairs paper_view() made; dispose() frees them


def dispose(ms, sec, tabs):
    """Tear a plan_scene down (section scenes, managers, the DXF worker, and
    every paper view / scene ``paper_view`` handed out)."""
    while _PAPER_VIEWS:
        view, ps = _PAPER_VIEWS.pop()
        view.deleteLater()
        ps.deleteLater()
    scenes = list(sec.open_scenes)
    sec.close_all()
    for s in scenes:
        s._rebuild_timer.stop()
        s.deleteLater()
    ms._section_manager = None
    ms._detail_manager = None
    ms.cleanup()
    tabs.deleteLater()
    QApplication.processEvents()


def add_sheet(ms, number, views=()):
    """A real Sheet appended to ``ms._sheets`` (the list SheetManager wraps),
    holding one SheetViewData per ``(view_type, view_name)`` in *views*."""
    from firepro3d.paper_space import Sheet, SheetViewData
    s = Sheet.create_default()
    s.number = number
    for vt, vn in views:
        s.sheet_views.append(SheetViewData(vt, vn, "", 0.01, 20.0, 20.0, 100.0, 80.0))
    ms._sheets.append(s)
    return s


def paper_view(ms, sec, det, sheet):
    """``(view, paper_scene)``: a real PaperGraphicsView over *sheet* with a
    real ViewResolver bound to the model scene and both managers."""
    from firepro3d.level_manager import PlanViewManager
    from firepro3d.paper_space import PaperGraphicsView, PaperScene, ViewResolver
    pvm = PlanViewManager()
    pvm.create("Level 1", ms._level_manager)
    resolver = ViewResolver(ms, pvm, det, sec, level_manager=ms._level_manager)
    ps = PaperScene(sheet, resolver)
    view = PaperGraphicsView(ps)
    view.resize(900, 700)
    _PAPER_VIEWS.append((view, ps))
    return view, ps


def find_leaf(browser, role, name):
    """The ProjectBrowser leaf with ``(_ROLE_TYPE, _ROLE_NAME) == (role, name)``."""
    from firepro3d.project_browser import _ROLE_NAME, _ROLE_TYPE
    tree = browser._tree
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if it.data(0, _ROLE_TYPE) == role and it.data(0, _ROLE_NAME) == name:
            return it
        stack.extend(it.child(i) for i in range(it.childCount()))
    return None


def drop_leaf(view, browser, role, name):
    """Drag the REAL browser leaf payload (``_tree.mimeData``) onto the paper
    view's centre: DragEnter, DragMove, Drop sent to the viewport."""
    from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
    from firepro3d.paper_space import sheet_page_mm
    mime = browser._tree.mimeData([find_leaf(browser, role, name)])
    ps = view.scene()
    pw, ph = sheet_page_mm(ps.sheet)
    view.centerOn(pw / 2, ph / 2)
    pt = view.mapFromScene(QPointF(pw / 2, ph / 2))
    act = Qt.DropAction.CopyAction
    for ev in (QDragEnterEvent(pt, act, mime, Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier),
               QDragMoveEvent(pt, act, mime, Qt.MouseButton.LeftButton,
                              Qt.KeyboardModifier.NoModifier),
               QDropEvent(QPointF(pt), act, mime, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)):
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def head_def(ms, category, *, shape="circle", colour="token:auto", texts=(), name=None):
    """An eligible head block for *category* (Annotative, Scale with zoom,
    host *category*), mapped as the project default: a HEAD_R circle or a
    2 * SQ_HALF square centred on the origin, plus one bound text per
    ``(host_key, y)`` in *texts* (placeholder "")."""
    if shape == "circle":
        geom = {"type": "draw_circle", "cx": 0.0, "cy": 0.0, "radius": HEAD_R,
                "color": colour, "lineweight": 1.0}
    else:
        geom = {"type": "draw_rectangle", "x": -SQ_HALF, "y": -SQ_HALF,
                "w": 2 * SQ_HALF, "h": 2 * SQ_HALF, "color": colour, "lineweight": 1.0}
    prims, attrs = [geom], []
    for key, y in texts:
        prims.append({"type": "text", "text": f"@[{key}]", "x": -4.0, "y": y,
                      "height_mm": 2.0, "wrap_width_mm": 8.0, "box_height_mm": 2.5,
                      "align": "C", "valign": "M"})
        attrs.append(normalise_attr({"key": key, "source": "host", "host_key": key,
                                     "placeholder": ""}))
    d = BlockDefinition.new(name=name or f"Test{category}Head", library="", series="",
                            origin=(0.0, 0.0), primitives=prims)
    d.scale_mode = "annotative"
    d.host_category = category
    d.attributes = attrs
    ms.register_block_definition(d)
    ms.annotation_defaults[category] = d.id
    return d


def tag_def(ms, *, category="Room", colour="#ff0000", half=1000.0, name="TestTagBlock"):
    """A placeable block: one filled 2 * half square (real size, scene mm).
    *category* non-empty = a host-bound tag (SB4d D5 -> Z_ANNOT_TAG); "" = a
    symbol block (stays model). Registered, never a project default."""
    loop = [{"type": "draw_line", "pt1": [-half, -half], "pt2": [half, -half]},
            {"type": "draw_line", "pt1": [half, -half], "pt2": [half, half]},
            {"type": "draw_line", "pt1": [half, half], "pt2": [-half, half]},
            {"type": "draw_line", "pt1": [-half, half], "pt2": [-half, -half]}]
    prims = [{"type": "draw_filled_region", "outline": False,
              "fill": {"background": {"color": colour, "opacity": 1.0}},
              "loops": [loop]}]
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=prims)
    d.host_category = category
    ms.register_block_definition(d)
    return d


def wall(ms, *, base="Level 1", top="Level 1", top_offset=3048.0, y=0.0):
    """A real WallSegment (0, y) -> (8000, y), 200 mm thick, registered so
    apply_to_scene governs it; z top = top level elevation + *top_offset*."""
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0.0, y), QPointF(8000.0, y), thickness_mm=200.0)
    w.level = base
    w._base_level = base
    w._top_level = top
    w._top_offset_mm = top_offset
    ms.addItem(w)
    ms._walls.append(w)
    return w


def top_z(item):
    """Effective stacking z of *item* against other top-level trees: Qt child
    z is local to the parent, so the top-level ancestor's z decides."""
    while item.parentItem() is not None:
        item = item.parentItem()
    return item.zValue()


def ink(img, pred):
    """``[(x, y)]`` of the pixels of QImage *img* whose QColor satisfies *pred*."""
    from PyQt6.QtGui import QColor
    return [(x, y) for y in range(img.height()) for x in range(img.width())
            if pred(QColor(img.pixel(x, y)))]


def pixel_at(ms, pt):
    """``#rrggbb`` of the scene as rendered at *pt* (10 mm per px, *pt* on a
    pixel centre so a 1 px cosmetic line through it covers that pixel fully)."""
    from PyQt6.QtGui import QColor, QImage, QPainter
    img = QImage(200, 200, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 200, 200),
              QRectF(pt.x() - 1005.0, pt.y() - 1005.0, 2000.0, 2000.0),
              Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return QColor(img.pixel(100, 100)).name()


def is_red(c):
    return c.red() > 200 and c.green() < 60 and c.blue() < 60
