"""U5 Leg B — Task 4b: read-only proxy frame parity.

The elevation scene projects model entities (walls/openings/pipes/sprinklers/
floor-slabs/roofs) as READ-ONLY proxy items. Selecting a proxy must show the
SelectionManipulator FRAME (parity with the plan scene) but with ZERO editing
handles — proxies are read-only projections (view-relationships §3.1).

The mechanism: proxy subclasses carry a NO-OP ``manip_translate(dx, dy)`` so
``item_capabilities`` grants ``{"translate"}`` (the manipulator wraps them),
and an explicit ``manip_handles() -> []`` that authoritatively suppresses the
rigid resize fallback (no ``manip_scale``/``manip_rotate``) so zero handles
surface. Interior-drag is inert (bakes nothing).

Uses the ``elevation_scene_for`` fixture (real Model_Space) from conftest.py.
"""
from PyQt6.QtWidgets import QGraphicsRectItem

from firepro3d.elevation_scene import (
    _ElevProxyRect, _ElevProxyLine, _ElevProxyEllipse,
)
from firepro3d.selection_manipulator import item_capabilities


def test_proxy_capabilities_translate_only(qapp):
    """Each proxy type declares exactly {"translate"} — no scale/rotate."""
    for cls, args in (
        (_ElevProxyRect, (0.0, 0.0, 10.0, 10.0)),
        (_ElevProxyLine, (0.0, 0.0, 10.0, 10.0)),
        (_ElevProxyEllipse, (0.0, 0.0, 10.0, 10.0)),
    ):
        proxy = cls(*args)
        assert item_capabilities(proxy) == {"translate"}, cls.__name__
        # No scale/rotate capability (frame-only, no group transform).
        assert not hasattr(proxy, "manip_scale"), cls.__name__
        assert not hasattr(proxy, "manip_rotate"), cls.__name__
        # manip_handles is declared but ZERO — authoritatively suppresses the
        # rigid resize fallback (design decision #4).
        assert proxy.manip_handles() == [], cls.__name__


def test_proxy_selection_shows_frame_zero_handles(qapp, elevation_scene_for):
    """A selected proxy shows the manipulator frame with zero editing handles."""
    _ms, elev = elevation_scene_for("north")
    proxy = _ElevProxyRect(0.0, 0.0, 100.0, 50.0)
    proxy.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
    elev.addItem(proxy)

    proxy.setSelected(True)

    manip = elev._live_manip()
    assert manip is not None
    assert manip.isVisible()
    # Frame only — a read-only proxy surfaces no editing handles.
    assert len(manip._active_handles()) == 0


def test_proxy_interior_move_is_inert(qapp):
    """A no-op ``manip_translate`` leaves the proxy geometry unchanged."""
    proxy = _ElevProxyRect(5.0, 7.0, 100.0, 50.0)
    before = proxy.rect()
    before_pos = proxy.pos()

    proxy.manip_translate(10.0, 10.0)   # inert — bakes nothing

    assert proxy.rect() == before
    assert proxy.pos() == before_pos
