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
