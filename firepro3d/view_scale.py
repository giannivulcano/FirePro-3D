"""Zoom (px per scene unit) of the view a scene is actually shown in.

Every zoom-dependent tolerance must read the *visible* view — never
``scene.views()[0]``, which in the app is the vestigial never-shown
``MainWindow.view`` frozen at ``m11 == 1.0`` (snapping-engine.md §14.4).

Item hit shapes need this because cosmetic pens draw a fixed screen-pixel
width while ``shape()`` is in scene units: without converting a pixel width
at the current zoom, thin items are unclickable zoomed out and fat zoomed in.
"""
from __future__ import annotations


def scene_view_scale(scene) -> float:
    """On-screen zoom for *scene*: its active view's ``|m11|``; 1.0 with no view.

    Prefers the scene's own ``_active_view_scale()`` (Model_Space: the visible
    plan view); otherwise the first visible view, else the last-attached one
    (headless tests attach views without ``show()``).

    Args:
        scene: A ``QGraphicsScene`` (or None).

    Returns:
        Pixels per scene unit, always > 0.
    """
    if scene is None:
        return 1.0
    fn = getattr(scene, "_active_view_scale", None)
    if callable(fn):
        try:
            return abs(fn()) or 1.0
        except (AttributeError, RuntimeError):
            # AttributeError: Model_Space mid-construction (placement shell not
            # built yet); RuntimeError: a view's C++ object already deleted.
            pass
    views = scene.views()
    if not views:
        return 1.0
    view = next((v for v in views if v.isVisible()), views[-1])
    return abs(view.transform().m11()) or 1.0


def scene_hit_width(item, px: float, default: float) -> float:
    """Scene-unit width equal to *px* screen pixels at *item*'s view zoom.

    Args:
        item: The graphics item whose ``shape()`` is being built.
        px: Desired hit width in screen pixels.
        default: Scene-unit width when the item has no scene or view.

    Returns:
        The width in scene units.
    """
    sc = item.scene()
    if sc is None or not sc.views():
        return default
    return px / scene_view_scale(sc)   # scene_view_scale is always > 0
