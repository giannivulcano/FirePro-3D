"""Regression test for the ``QFont::setPointSize: Point size <= 0`` warning
emitted when the import dialog's combo popups are measured.

Root cause: the app-wide QSS rule ``QWidget { font-size: 13px; }``
(``firepro3d/theme.py``) gives inheriting widgets a *pixel-size* font, whose
``pointSize()`` is ``-1``. When a ``QComboBox`` popup is shown on a real
screen, Qt copies the combo's ``pointSize()`` into a measuring font via
``QFont::setPointSize(-1)`` -> the warning. The three import-dialog combos
(``_dpi_combo``/``_mode_combo``/``_scale_combo``) must therefore carry a font
with a valid (>0) point size so the popup measurement path never sees ``-1``.

The full app stylesheet is applied here (the ``qapp`` fixture does not) so the
combos resolve to the same font they get in the live app.
"""
from __future__ import annotations

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtGui import QFont


def _apply_app_qss(qapp):
    """Mirror ``main.main()`` startup: house UI font + app QSS."""
    import firepro3d.theme as th
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))


def test_opening_combos_emits_no_pointsize_warning(qapp):
    _apply_app_qss(qapp)
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    seen: list[str] = []
    qInstallMessageHandler(lambda mode, ctx, msg: seen.append(str(msg)))
    dlg = None
    try:
        dlg = UnderlayImportDialog(None)
        dlg.show()
        qapp.processEvents()
        seen.clear()

        for combo in (dlg._dpi_combo, dlg._mode_combo, dlg._scale_combo):
            f = combo.font()
            # (1) Structural guarantee: the resolved font must expose a valid
            #     point size. A pixel-only font (pointSize() == -1) is exactly
            #     what makes Qt's popup measurement call setPointSize(-1).
            assert f.pointSize() > 0, (
                f"combo font has pointSize={f.pointSize()} "
                f"(px={f.pixelSize()}, fam={f.family()}) — the popup path "
                f"will emit setPointSize<=0"
            )
            # (2) Reproduce the exact copy Qt performs when sizing the popup
            #     items, so the message handler observes any warning.
            probe = QFont(f)
            probe.setPointSize(f.pointSize())

            # Also exercise the real popup build/measure path.
            _ = combo.view()
            _ = combo.sizeHint()
            combo.showPopup()
            qapp.processEvents()
            combo.view().doItemsLayout()
            qapp.processEvents()
            combo.hidePopup()
            qapp.processEvents()

        assert not any("setPointSize" in m or "Point size" in m for m in seen), seen
    finally:
        qInstallMessageHandler(None)
        if dlg is not None:
            dlg.deleteLater()
        qapp.processEvents()


def test_combo_rendered_pixel_size_matches_13px(qapp):
    """The fix must keep the on-screen size identical to the inherited 13px."""
    from PyQt6.QtGui import QFontMetrics
    _apply_app_qss(qapp)
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    dlg = None
    try:
        dlg = UnderlayImportDialog(None)
        dlg.show()
        qapp.processEvents()
        for combo in (dlg._dpi_combo, dlg._mode_combo, dlg._scale_combo):
            px = QFontMetrics(combo.font()).height()
            ref = QFontMetrics(_px_font(13)).height()
            assert px == ref, (
                f"combo line height {px}px != 13px reference {ref}px "
                f"(font pt={combo.font().pointSize()} px={combo.font().pixelSize()})"
            )
    finally:
        if dlg is not None:
            dlg.deleteLater()
        qapp.processEvents()


def _px_font(px: int) -> QFont:
    from PyQt6.QtWidgets import QApplication
    f = QFont(QApplication.instance().font())
    f.setFamily("Arial")
    f.setPixelSize(px)
    return f
