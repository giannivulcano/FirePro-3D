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
