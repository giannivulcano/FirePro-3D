"""
test_paper_marker_exclusion.py
==============================
Verify that elevation-marker furniture (SharedCropBox, ViewMarkerArrow) is
force-hidden during paper render and restored afterward — PAPER_EXCLUDED hard
rule (concern 2).
"""
from PyQt6.QtCore import QRectF


def test_shared_cropbox_has_paper_excluded_flag(qapp):
    from firepro3d.view_marker import SharedCropBox
    box = SharedCropBox(QRectF(0, 0, 500, 500))
    assert getattr(type(box), "PAPER_EXCLUDED", False) is True


def test_view_marker_arrow_has_paper_excluded_flag(qapp):
    from firepro3d.view_marker import ViewMarkerArrow
    assert getattr(ViewMarkerArrow, "PAPER_EXCLUDED", False) is True


def test_elevation_furniture_hidden_during_paper_render_then_restored(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from firepro3d.view_marker import SharedCropBox
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display

    model = QGraphicsScene()
    box = SharedCropBox(QRectF(0, 0, 500, 500))
    box.setVisible(True)
    model.addItem(box)

    saved = apply_paper_overrides(model, QRectF(0, 0, 500, 500))
    assert box.isVisible() is False          # force-hidden during paper render
    restore_model_display(saved)
    assert box.isVisible() is True           # restored after


def _make_detail_marker(name, rect):
    """Construct a DetailMarker with the given name + crop rect."""
    from firepro3d.detail_view import DetailMarker
    return DetailMarker(name, rect)


def test_detail_self_hide_and_per_sheet_hide(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_space import SheetViewData
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display

    model = QGraphicsScene()
    d1 = _make_detail_marker("D1", QRectF(0, 0, 100, 100))
    d2 = _make_detail_marker("D2", QRectF(50, 50, 100, 100))
    model.addItem(d1); model.addItem(d2)

    # Rendering DETAIL "D1": self-hide D1, show D2.
    vd = SheetViewData("detail", "D1", "DET", 0.2, 0, 0, 20, 20)
    saved = apply_paper_overrides(model, QRectF(0, 0, 200, 200), viewport_data=vd)
    assert d1.isVisible() is False
    assert d2.isVisible() is True
    restore_model_display(saved)
    assert d1.isVisible() is True

    # Rendering PLAN with D2 hidden per-sheet: D1 shows, D2 hidden.
    vp = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 20, 20)
    vp.hidden_detail_ids = {"D2"}
    saved = apply_paper_overrides(model, QRectF(0, 0, 200, 200), viewport_data=vp)
    assert d1.isVisible() is True
    assert d2.isVisible() is False
    restore_model_display(saved)
    assert d2.isVisible() is True


def test_toggle_hidden_detail_is_undoable(qapp):
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
    from firepro3d.paper_commands import ChangeViewportPropertiesCommand

    class _PlanMgr:
        def __init__(self): self._views = {"Level 1": object()}
        def get(self, n): return self._views.get(n)

    model = QGraphicsScene(); model.addItem(QGraphicsRectItem(QRectF(0, 0, 100, 100)))
    resolver = ViewResolver(model, _PlanMgr(), None, None)
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, resolver)
    vp = scene.add_viewport(data)

    cmd = ChangeViewportPropertiesCommand(
        scene, data, {"hidden_detail_ids": set()},
        {"hidden_detail_ids": {"D9"}})
    scene.undo_stack.push(cmd)
    assert data.hidden_detail_ids == {"D9"}
    scene.undo_stack.undo()
    assert data.hidden_detail_ids == set()


def test_toggle_hidden_detail_method(qapp):
    """SheetViewport._toggle_hidden_detail flips membership + is undoable."""
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtCore import QRectF
    from firepro3d.detail_view import DetailMarker
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver

    class _DetailMgr:
        def __init__(self, m): self._m = m
        def get_marker(self, n): return self._m.get(n)
        @property
        def detail_names(self): return list(self._m)
    class _PlanMgr:
        def __init__(self): self._views = {"Level 1": object()}
        def get(self, n): return self._views.get(n)

    model = QGraphicsScene()
    dm = DetailMarker("D1", QRectF(0, 0, 100, 100)); model.addItem(dm)
    resolver = ViewResolver(model, _PlanMgr(), _DetailMgr({"D1": dm}), None)
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, resolver)
    vp = scene.add_viewport(data)

    vp._toggle_hidden_detail("D1")
    assert "D1" in data.hidden_detail_ids
    scene.undo_stack.undo()
    assert "D1" not in data.hidden_detail_ids
    scene.undo_stack.redo()
    assert "D1" in data.hidden_detail_ids
