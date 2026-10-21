"""
test_paper_marker_exclusion.py
==============================
Verify that cardinal SectionMarkers are force-hidden during paper render and
restored afterward (PAPER_EXCLUDED hard rule, concern 2) while a placed section's
marker is NOT excluded (spec s6, view-relationships s6.4).
"""
from PyQt6.QtCore import QPointF, QRectF


def _cardinal_marker():
    from firepro3d.section_marker import SectionMarker
    return SectionMarker.for_cardinal("north", QRectF(-5000.0, -5000.0, 10000.0, 10000.0))


def _placed_marker():
    from firepro3d.section_marker import SectionMarker
    return SectionMarker("Section 1", QPointF(0.0, 0.0), QPointF(6000.0, 0.0), 1, 3000.0)


def test_paper_excluded_flag_cardinal_yes_placed_no(qapp):
    assert _cardinal_marker().PAPER_EXCLUDED is True
    assert _placed_marker().PAPER_EXCLUDED is False


def test_cardinal_marker_hidden_during_paper_render_then_restored(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display

    model = QGraphicsScene()
    card = _cardinal_marker()
    card.setVisible(True)
    model.addItem(card)

    saved = apply_paper_overrides(model, QRectF(-6000, -6000, 12000, 12000))
    assert card.isVisible() is False         # force-hidden during paper render
    restore_model_display(saved)
    assert card.isVisible() is True          # restored after


def test_placed_marker_is_in_the_paper_render_set(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display

    model = QGraphicsScene()
    card, placed = _cardinal_marker(), _placed_marker()
    model.addItem(card); model.addItem(placed)

    saved = apply_paper_overrides(model, QRectF(-6000, -6000, 12000, 12000))
    assert card.isVisible() is False         # cardinals never plot
    assert placed.isVisible() is True        # a placed section plots by the default path
    restore_model_display(saved)
    assert card.isVisible() is True and placed.isVisible() is True


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
