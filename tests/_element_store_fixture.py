"""Every-kind scene builder for the element store guards (docs/specs/element-store.md G1-G4)."""
from __future__ import annotations

import json
import re

from PyQt6.QtCore import QPointF

from tests._ph1_helpers import (add_block, add_floor_opening, add_opening, add_roof,
                                add_room, scene)

ROW_ATTRS = ("design_areas", "_polylines", "_draw_lines", "_draw_rects", "_draw_circles",
             "_draw_arcs", "_draw_ellipses", "_draw_splines", "_filled_regions",
             "_draw_polygons", "_texts", "_gridlines", "_walls", "_floor_slabs", "_roofs",
             "_rooms", "_block_instances")   # the 17 rows, spec D2 order (test-side copy)


def _add(ms, item, attr):
    ms.addItem(item)
    getattr(ms, attr).append(item)
    return item


def build_every_kind(ms=None):
    """A scene holding >= 1 item of every row; returns (ms, {attr: first item})."""
    from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                       PolylineItem, RectangleItem, RegularPolygonItem,
                                       SplineItem)
    from firepro3d.filled_region import FilledRegionItem
    from firepro3d.text_item import TextItem, TextAnnotationData
    from firepro3d.gridline import GridlineItem
    from firepro3d.design_area import DesignArea
    from firepro3d.gridline import reset_grid_counters
    reset_grid_counters()          # the auto-label counters are module globals (order independence)
    ms = ms or scene()
    out = {}
    out["_draw_lines"] = _add(ms, LineItem(QPointF(0, 0), QPointF(500, 0)), "_draw_lines")
    out["_draw_rects"] = _add(ms, RectangleItem(QPointF(0, 0), QPointF(100, 100)), "_draw_rects")
    out["_draw_circles"] = _add(ms, CircleItem(QPointF(0, 0), 50.0), "_draw_circles")
    out["_draw_arcs"] = _add(ms, ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0), "_draw_arcs")
    out["_draw_ellipses"] = _add(ms, EllipseItem(QPointF(0, 0), 60.0, 30.0), "_draw_ellipses")
    out["_draw_splines"] = _add(ms, SplineItem([QPointF(0, 0), QPointF(50, 80),
                                                QPointF(100, 0), QPointF(150, 60)]),
                                "_draw_splines")
    out["_draw_polygons"] = _add(ms, RegularPolygonItem(QPointF(0, 0), sides=5, radius_mm=40.0),
                                 "_draw_polygons")
    pl = PolylineItem(QPointF(0, 0))          # test_geo2d_serialization.py: append_point shape
    pl.append_point(QPointF(100, 0))
    pl.append_point(QPointF(0, 100))
    out["_polylines"] = _add(ms, pl, "_polylines")
    # test_filled_region.py ring_region(): from_pieces([[LineItem x4], [CircleItem]])
    a, b, c, d = QPointF(10, 10), QPointF(110, 10), QPointF(110, 110), QPointF(10, 110)
    fr = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d),
                                        LineItem(d, a)],
                                       [CircleItem(QPointF(60, 60), 15)]])
    out["_filled_regions"] = _add(ms, fr, "_filled_regions")
    out["_texts"] = _add(ms, TextItem(TextAnnotationData(text="T", x=10.0, y=10.0)),
                         "_texts")             # precedent: paper_parity_support.py:82
    gl = GridlineItem(QPointF(0, -1000), QPointF(0, 5000))
    out["_gridlines"] = _add(ms, gl, "_gridlines")
    add_opening(ms)                            # wall + one owned opening
    out["_walls"] = ms._walls[0]
    add_floor_opening(ms)                      # slab + one owned void
    out["_floor_slabs"] = ms._floor_slabs[0]
    out["_roofs"] = add_roof(ms)
    out["_rooms"] = add_room(ms)
    out["_block_instances"] = add_block(ms)
    da = DesignArea([])                        # test_design_area.py:231 shape
    ms.addItem(da)
    ms.design_areas.append(da)
    out["design_areas"] = da
    for attr in ROW_ATTRS:
        assert getattr(ms, attr), f"fixture left {attr} empty"
    return ms, out


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX32 = re.compile(r'(?<=")[0-9a-f]{32}(?=")')
_UID_HEX =re.compile(r'"(uid|_uid|id|block_id)": "([0-9a-f]{12,32})"')
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?")


def normalise(text: str) -> str:
    """EOL + uuid + uid-hex + date normalised; ids keep their identity (first-seen index)."""
    text = text.replace("\r\n", "\n")
    seen: dict = {}

    def _sub(m, grp=0, fmt="<id{}>"):
        key = m.group(grp)
        seen.setdefault(key, len(seen))
        return fmt.format(seen[key])

    text = _UUID.sub(lambda m: _sub(m), text)
    text = _HEX32.sub(lambda m: _sub(m), text)   # also catches ids used as dict keys
    text = _UID_HEX.sub(lambda m: f'"{m.group(1)}": "' + _sub(m, 2) + '"', text)
    return _DATE.sub("<date>", text)


def undo_bytes(ms) -> str:
    return normalise(json.dumps(ms._capture_network(), default=str, indent=1))


def save_bytes(ms, path) -> str:
    assert ms.save_to_file(str(path), backup=False)
    with open(path, encoding="utf-8") as fh:
        return normalise(fh.read())
