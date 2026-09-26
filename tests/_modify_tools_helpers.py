"""Primitive factories + undo helpers for the modify-tool guards (scene-tools.md I4)."""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (
    ArcItem, CircleItem, EllipseItem, LineItem, PolylineItem, RectangleItem,
    ReferenceLineItem, RegularPolygonItem, SplineItem,
)
from firepro3d.text_item import TextAnnotationData, TextItem

# name -> (factory, scene list attribute)
def _line():      return LineItem(QPointF(0, 0), QPointF(100, 0))
def _refline():   return ReferenceLineItem(QPointF(0, 0), QPointF(100, 0))
def _poly_open():
    p = PolylineItem(QPointF(0, 0)); p.append_point(QPointF(100, 0)); p.append_point(QPointF(100, -100)); return p
def _poly_closed():
    p = _poly_open(); p.append_point(QPointF(0, -100)); p.close(); return p
def _rect():      return RectangleItem(QPointF(0, 0), QPointF(100, -50))
def _rect_rot():
    r = RectangleItem(QPointF(0, 0), QPointF(100, -50)); r.set_angle(30.0); return r
def _circle():    return CircleItem(QPointF(0, 0), 50.0)
def _arc():       return ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0)
def _polygon():   return RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=50.0)
def _ellipse():   return EllipseItem(QPointF(0, 0), 80.0, 40.0)
def _spline():    return SplineItem([QPointF(0, 0), QPointF(50, -60), QPointF(100, 0), QPointF(150, -40)])
def _text():      return TextItem(TextAnnotationData(text="T", x=0.0, y=0.0, height_mm=20.0))
def _text_rot():
    t = _text(); t.set_angle(30.0); return t

PRIMITIVES = {
    "line": (_line, "_draw_lines"),
    "refline": (_refline, "_reference_lines"),
    "polyline_open": (_poly_open, "_polylines"),
    "polyline_closed": (_poly_closed, "_polylines"),
    "rect": (_rect, "_draw_rects"),
    "rect_rotated": (_rect_rot, "_draw_rects"),
    "circle": (_circle, "_draw_circles"),
    "arc": (_arc, "_draw_arcs"),
    "polygon": (_polygon, "_draw_polygons"),
    "ellipse": (_ellipse, "_draw_ellipses"),
    "spline": (_spline, "_draw_splines"),
    "text": (_text, "_texts"),
    "text_rotated": (_text_rot, "_texts"),
}


def add_primitive(scene, name):
    """Add primitive *name* to *scene* (+ its tracking list), select it, set the undo baseline."""
    factory, attr = PRIMITIVES[name]
    item = factory()
    scene.addItem(item)
    getattr(scene, attr).append(item)
    scene.push_undo_state()
    scene.clearSelection()
    item.setSelected(True)
    return item, attr


def grips(item):
    return [(round(p.x(), 3), round(p.y(), 3)) for p in item.grip_points()]
