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


def _load_geoms(dlg, geoms):
    """Push a page's geoms through the real rebuild path."""
    dlg._all_geoms = geoms
    dlg._layers = ["A"]
    dlg._selected_indices = None
    dlg._rebuild_preview()


def test_canonical_fit_is_deterministic_across_pages(qapp):
    """Same geometry → same fit transform, regardless of where the geometry
    sits relative to the origin (the base-marker/cursor overlays no longer
    pollute the fit rect). Page-1 (offset from origin) fits to the SAME scale
    as page-0 (at origin), and switching back reproduces the identical zoom."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")
    dlg._preview_view.resize(400, 300)

    # Two 100×100 drawings — one at the origin, one far from it.
    page0 = [
        {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 0.0, "layer": "A"},
        {"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 100.0, "layer": "A"},
    ]
    page1 = [
        {"kind": "line", "x1": 5000.0, "y1": 5000.0, "x2": 5100.0, "y2": 5000.0, "layer": "A"},
        {"kind": "line", "x1": 5000.0, "y1": 5000.0, "x2": 5000.0, "y2": 5100.0, "layer": "A"},
    ]

    _load_geoms(dlg, page0)
    m0 = dlg._preview_view.transform().m11()
    _load_geoms(dlg, page1)
    m1 = dlg._preview_view.transform().m11()
    _load_geoms(dlg, page0)
    m0b = dlg._preview_view.transform().m11()

    # Truly fitted, not identity (a no-fit would leave m11 == 1.0).
    assert m0 != 1.0
    # Same-size geometry → same fit scale even when offset far from origin.
    assert abs(m0 - m1) < 1e-9, (m0, m1)
    # Switch-and-back is deterministic: identical transform.
    assert m0 == m0b
    dlg.deleteLater()


def test_content_rect_excludes_base_marker(qapp):
    """The canonical fit rect is the geometry's bounds only — the base-point
    crosshair (drawn at the origin by default) must NOT inflate it."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")
    dlg._preview_view.resize(400, 300)
    _load_geoms(dlg, [
        {"kind": "line", "x1": 5000.0, "y1": 5000.0, "x2": 5100.0, "y2": 5000.0, "layer": "A"},
        {"kind": "line", "x1": 5000.0, "y1": 5000.0, "x2": 5000.0, "y2": 5100.0, "layer": "A"},
    ])
    # Zero out the default preview rotation so the group's bounds map 1:1 to
    # the geometry (rotation is about the origin base point, which would shift
    # the bounds and obscure the origin-pollution check).
    dlg._set_rotation(0.0)
    rect = dlg._content_rect()
    # Geometry lives at (5000,5000)-(5100,5100), a 100×100 box. The origin base
    # marker must NOT drag the rect back to the origin (that ballooned it to
    # ~5100 across before the fix).
    assert rect.left() >= 4999.0
    assert rect.top() >= 4999.0
    assert rect.width() < 200.0 and rect.height() < 200.0
    dlg.deleteLater()
