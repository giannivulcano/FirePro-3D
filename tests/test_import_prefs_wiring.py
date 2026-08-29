"""Item 1 of the PDF Import Polish cluster: PDF DPI/import-mode defaults live in
Preferences (ImportPane) and the import dialog seeds its combos from them."""
from PyQt6.QtCore import QSettings

from firepro3d.preferences_dialog import ImportPane, _QSETTINGS_ORG, _QSETTINGS_APP


def _clear_keys():
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    s.remove("import/pdf_dpi")
    s.remove("import/pdf_import_mode")


def test_import_pane_writes_dpi_and_mode(qapp):
    _clear_keys()
    pane = ImportPane()
    pane.load()
    pane._dpi_combo.setCurrentText("300")
    pane._mode_combo.setCurrentText("Vectors")
    pane.apply()

    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    assert s.value("import/pdf_dpi", type=int) == 300
    assert s.value("import/pdf_import_mode", type=str) == "vectors"
    _clear_keys()


def test_import_pane_loads_existing_defaults(qapp):
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    s.setValue("import/pdf_dpi", 72)
    s.setValue("import/pdf_import_mode", "raster")
    pane = ImportPane()
    pane.load()
    assert pane._dpi_combo.currentText() == "72"
    assert pane._mode_combo.currentText() == "Raster"
    _clear_keys()


def test_import_dialog_seeds_from_prefs(qapp):
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    s.setValue("import/pdf_dpi", 300)
    s.setValue("import/pdf_import_mode", "raster")
    from firepro3d.dxf_preview_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None)
    dlg._seed_pdf_options_from_prefs()
    assert dlg._dpi_combo.currentText() == "300"
    assert dlg._mode_combo.currentText() == "Raster"
    _clear_keys()
