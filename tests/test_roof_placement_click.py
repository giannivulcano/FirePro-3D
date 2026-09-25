"""Guard — roof polygon placement survives real clicks.

The first roof click used to abort the process: ``_get_roof_template``
imported the non-existent ``firepro3d.roof_item`` (``RoofItem`` lives in
``firepro3d/roof.py``). Two real clicks through a shown view must leave an
in-progress roof with two vertices. Never close the polygon here — closing
opens the modal ``RoofDialog``.
"""
from PyQt6.QtCore import QPointF

from tests._snap_polish_helpers import click, close_view, make_view


def test_roof_polygon_two_real_clicks(qapp):
    view, scene = make_view(role="plan", mode="roof")
    try:
        assert scene.mode == "roof"
        click(view, QPointF(0, 0))
        click(view, QPointF(1000, 0))
        roof = scene._roof_active
        assert roof is not None
        assert len(roof._points) == 2, roof._points
        assert roof in scene._roofs
    finally:
        close_view(view, scene)
