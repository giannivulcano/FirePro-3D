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
