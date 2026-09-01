"""Modify prefill loads geometry BEFORE the dialog is shown, so the original
fitInView ran against an unsized viewport (reads "100%" while zoomed out —
Bug 2). showEvent now defers a re-fit; _fit_preview_to_content performs it.

Offscreen viewport sizing is unreliable, so these assert the fit MECHANISM
(the helper fits content and no-ops on empty). The visual fit needs a live
smoke test.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QGraphicsLineItem


def test_fit_helper_noops_when_empty(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")
    # Nothing loaded — must not raise and must leave the view alone.
    before = dlg._preview_view.transform()
    dlg._fit_preview_to_content()
    assert dlg._preview_view.transform() == before
    dlg.deleteLater()


def test_fit_helper_fits_when_content_present(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")
    # Give the view a real size so fitInView has something to fit into.
    dlg._preview_view.resize(400, 300)
    # Add geometry directly to the preview scene, well away from the origin so a
    # no-fit transform would leave it far off-screen.
    line = QGraphicsLineItem(1000.0, 1000.0, 2000.0, 1500.0)
    dlg._preview_scene.addItem(line)

    dlg._fit_preview_to_content()

    # After the fit the content's scene bounds map inside the viewport rect.
    br = dlg._preview_scene.itemsBoundingRect()
    poly = dlg._preview_view.mapFromScene(br)
    vp = dlg._preview_view.viewport().rect()
    bounds = poly.boundingRect()
    # KeepAspectRatio + the 10-unit margin means it sits within (a little slack).
    assert bounds.width() <= vp.width() + 2
    assert bounds.height() <= vp.height() + 2
    dlg.deleteLater()
