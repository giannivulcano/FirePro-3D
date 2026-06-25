"""Tests for paper-space PDF export / print (firepro3d/paper_export.py)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtCore import QRectF

from firepro3d.paper_space import (
    Sheet, SheetViewData, SheetViewport, PaperScene, ViewResolver,
)


def _real_source_resolver():
    """Resolver returning a real model QGraphicsScene + rect (for rendering)."""
    model_scene = QGraphicsScene()
    model_scene.addRect(0, 0, 10000, 8000)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = (model_scene, QRectF(0, 0, 10000, 8000))
    return resolver, model_scene


class TestLifecycleTeardown:
    def test_viewport_disconnect_source_drops_connection(self, qapp):
        resolver, model_scene = _real_source_resolver()
        data = SheetViewData("plan", "L1", "L1", 0.01, 50, 50, 400, 300)
        vp = SheetViewport(data, resolver)
        assert vp._source_scene is model_scene
        vp.disconnect_source()
        assert vp._source_scene is None
        # Mutating the (now-disconnected) source must not call mark_dirty.
        with patch.object(vp, "update") as mock_update:
            model_scene.addRect(0, 0, 1, 1)
            qapp.processEvents()
            mock_update.assert_not_called()

    def test_paper_scene_dispose_disconnects_all_viewports(self, qapp):
        resolver, _ = _real_source_resolver()
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 50, 50, 400, 300),
        ]
        scene = PaperScene(sheet, resolver)
        assert len(scene.get_viewports()) == 1
        scene.dispose()
        assert all(vp._source_scene is None for vp in scene.get_viewports())
