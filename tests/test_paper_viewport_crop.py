import pytest
from PyQt6.QtCore import QRectF
from firepro3d.paper_space import SheetViewData


def _base_kwargs():
    return dict(source_view_type="plan", source_view_name="Level 1",
                title="PLAN", scale=0.01, x=10.0, y=20.0, w=100.0, h=80.0)


def test_sheetviewdata_defaults_crop_and_hidden():
    d = SheetViewData(**_base_kwargs())
    assert isinstance(d.crop_rect, QRectF)
    assert d.crop_rect.isNull() or d.crop_rect.isEmpty()
    assert d.hidden_detail_ids == set()


def test_sheetviewdata_roundtrip_crop_and_hidden():
    d = SheetViewData(**_base_kwargs())
    d.crop_rect = QRectF(5.0, 6.0, 300.0, 200.0)
    d.hidden_detail_ids = {"Detail A", "Detail B"}
    d2 = SheetViewData.from_dict(d.to_dict())
    assert d2.crop_rect == QRectF(5.0, 6.0, 300.0, 200.0)
    assert d2.hidden_detail_ids == {"Detail A", "Detail B"}


def test_sheetviewdata_migration_missing_fields():
    legacy = dict(source_view_type="plan", source_view_name="Level 1",
                  title="PLAN", scale=0.01, x=1.0, y=2.0, w=3.0, h=4.0,
                  show_border=True, view_number="")
    d = SheetViewData.from_dict(legacy)
    assert d.crop_rect.isNull() or d.crop_rect.isEmpty()
    assert d.hidden_detail_ids == set()


# ── Task 2: effective-crop + size-derivation helpers ──────────────────────────

class _FakeMarker:
    def __init__(self, rect): self._r = rect
    @property
    def crop_rect(self): return QRectF(self._r)


class _FakeDetailMgr:
    def __init__(self, markers): self._m = markers
    def get_marker(self, name): return self._m.get(name)
    @property
    def detail_names(self): return list(self._m)


class _FakePlanMgr:
    def __init__(self): self._views = {"Level 1": object()}
    def get(self, name): return self._views.get(name)


def _resolver(model_scene, markers=None):
    from firepro3d.paper_space import ViewResolver
    return ViewResolver(model_scene, _FakePlanMgr(),
                        _FakeDetailMgr(markers or {}), elevation_manager=None)


def test_plan_viewport_size_derives_from_crop_and_scale(qapp):
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)
    assert data.crop_rect.width() == pytest.approx(1000, abs=1.0)
    assert data.w == pytest.approx(1000 * 0.1, abs=0.5)
    assert data.h == pytest.approx(500 * 0.1, abs=0.5)


def test_detail_viewport_effective_crop_tracks_marker(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
    model = QGraphicsScene()
    markers = {"D1": _FakeMarker(QRectF(100, 100, 200, 150))}
    sheet = Sheet.create_default()
    data = SheetViewData("detail", "D1", "DET", 0.2, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model, markers))
    scene.add_viewport(data)
    assert data.w == pytest.approx(200 * 0.2, abs=0.5)
    assert data.h == pytest.approx(150 * 0.2, abs=0.5)


def test_plan_viewport_renders_only_its_crop(qapp):
    """A plan viewport whose crop is smaller than the full scene extent must
    render ONLY the crop region. Geometry outside the crop (but inside the full
    scene extent, so it survives Qt's own source-rect cull) must not appear.
    This is the concern-1 bleed."""
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from PyQt6.QtGui import QImage, QPainter, QColor, QBrush, QPen
    from PyQt6.QtCore import QRectF, Qt
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData

    model = QGraphicsScene()
    inside = QGraphicsRectItem(QRectF(10, 10, 30, 30))
    inside.setBrush(QBrush(QColor("black"))); inside.setPen(QPen(Qt.PenStyle.NoPen))
    model.addItem(inside)
    outside = QGraphicsRectItem(QRectF(200, 200, 60, 60))
    outside.setBrush(QBrush(QColor(255, 0, 0))); outside.setPen(QPen(Qt.PenStyle.NoPen))
    model.addItem(outside)   # inside the full extent (~0..260) but outside the crop

    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.0, 0, 0, 100, 100)
    scene = PaperScene(sheet, _resolver(model))
    scene.add_viewport(data)
    # Force a crop SMALLER than the full scene extent.
    data.crop_rect = QRectF(0, 0, 100, 100)

    img = QImage(120, 120, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 120, 120), QRectF(-10, -10, 120, 120))
    p.end()

    red = QColor(255, 0, 0).rgb()
    found_red = any(img.pixel(x, y) == red
                    for x in range(0, 120, 2) for y in range(0, 120, 2))
    assert not found_red, "geometry outside the crop bled into the viewport"


# ── Task 4: grip rework + ViewportGeometryCommand carries crop_rect ───────────
#
# Grips retired (Task 7): resize now flows through the SelectionManipulator's
# manip_scale.  _drag_grip translates the legacy 8-handle index + paper delta
# into the equivalent manip_scale(fx, fy, anchor) call (same crop×scale
# outcome — proven byte-for-byte in test_selection_manipulator_paper.py).

# Legacy handle index -> (moves_left, moves_right, moves_top, moves_bottom).
_LEGACY_HANDLE_EDGES = {
    0: (True, False, True, False),    # TL
    1: (False, False, True, False),   # T
    2: (False, True, True, False),    # TR
    3: (True, False, False, False),   # ML
    4: (False, True, False, False),   # MR
    5: (True, False, False, True),    # BL
    6: (False, False, False, True),   # B
    7: (False, True, False, True),    # BR
}


def _drag_grip(vp, handle_index, dx, dy):
    from PyQt6.QtCore import QPointF
    ml, mr, mt, mb = _LEGACY_HANDLE_EDGES[handle_index]
    data = vp.data
    x, y, w, h = data.x, data.y, data.w, data.h
    # New on-paper size after moving the active edges by the paper delta.
    new_w = w + (dx if mr else 0.0) - (dx if ml else 0.0)
    new_h = h + (dy if mb else 0.0) - (dy if mt else 0.0)
    fx = new_w / w if w else 1.0
    fy = new_h / h if h else 1.0
    # Anchor = the corner opposite the moving edges (fixed on paper).
    ax = (x + w) if ml else x
    ay = (y + h) if mt else y
    vp.manip_scale(fx, fy, QPointF(ax, ay))


def test_plan_grip_edits_crop_keeps_scale(qapp):
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)
    scale_before = data.scale
    crop_w_before = data.crop_rect.width()
    _drag_grip(vp, 4, 30, 0)   # middle-right grip +30mm paper → +300 model at 0.1
    assert data.scale == scale_before
    assert data.crop_rect.width() == pytest.approx(crop_w_before + 300, abs=1.0)
    assert data.w == pytest.approx(data.crop_rect.width() * data.scale, abs=0.5)


def test_detail_viewport_has_no_resize_grips(qapp):
    """Detail viewports are marker-owned: the manipulator shows no resize
    handles (scale capability dropped), and manip_scale is inert."""
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtCore import QRectF, QPointF
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
    from firepro3d.selection_manipulator import item_capabilities
    model = QGraphicsScene()
    markers = {"D1": _FakeMarker(QRectF(0, 0, 100, 100))}
    sheet = Sheet.create_default()
    data = SheetViewData("detail", "D1", "DET", 0.2, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model, markers))
    vp = scene.add_viewport(data)
    vp.setSelected(True)
    assert "scale" not in item_capabilities(vp)
    # Inert: a manip_scale on a detail viewport changes nothing.
    w_before = data.w
    vp.manip_scale(2.0, 2.0, QPointF(0, 0))
    assert data.w == w_before


def test_viewport_geometry_undo_restores_crop(qapp):
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)
    crop_before = QRectF(data.crop_rect)
    old = (data.x, data.y, data.w, data.h,
           (data.crop_rect.x(), data.crop_rect.y(),
            data.crop_rect.width(), data.crop_rect.height()))
    _drag_grip(vp, 4, 50, 0)
    new = (data.x, data.y, data.w, data.h,
           (data.crop_rect.x(), data.crop_rect.y(),
            data.crop_rect.width(), data.crop_rect.height()))
    from firepro3d.paper_commands import ViewportGeometryCommand
    scene.undo_stack.push(ViewportGeometryCommand(scene, data, old, new))
    scene.undo_stack.undo()
    assert data.crop_rect == crop_before


# ── Task 5: scale change keeps crop, recomputes size ─────────────────────────

def test_scale_change_keeps_crop_recomputes_size(qapp):
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)
    crop_before = QRectF(data.crop_rect)
    # Simulate a scale change to 0.2 via the derive helper (unit-level).
    data.scale = 0.2
    vp._recompute_size_from_scale()
    assert data.crop_rect == crop_before                    # crop unchanged
    assert data.w == pytest.approx(crop_before.width() * 0.2, abs=0.5)
    assert data.h == pytest.approx(crop_before.height() * 0.2, abs=0.5)


def test_scale_change_via_properties_keeps_crop(qapp):
    """Changing scale (via the shared commit_viewport_edit) preserves a non-default crop."""
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from PyQt6.QtCore import QRectF
    from firepro3d.paper_space import PaperScene, Sheet, SheetViewData

    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)

    # Shrink the crop to a sub-region of the source.
    sub_crop = QRectF(100, 100, 400, 200)
    data.crop_rect = sub_crop

    scene.commit_viewport_edit(vp, scale=0.2)

    # Crop must be unchanged; size must be crop × new_scale.
    assert data.crop_rect == sub_crop
    assert data.scale == pytest.approx(0.2)
    assert data.w == pytest.approx(sub_crop.width() * 0.2, abs=0.5)
    assert data.h == pytest.approx(sub_crop.height() * 0.2, abs=0.5)
