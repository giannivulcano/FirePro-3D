from firepro3d.underlay_import_dialog import UnderlayImportDialog
from firepro3d import theme


def test_import_dialog_has_own_objectname(qapp):
    dlg = UnderlayImportDialog(None)
    assert dlg.objectName() == "UnderlayImportDialog"
    dlg.deleteLater()


def test_theme_qss_styles_both_dialog_ids():
    qss = theme.build_underlay_manager_qss(theme.detect())
    assert "#UnderlayImportDialog" in qss
    assert "#UnderlayManagerDialog" in qss
    # shared chrome must actually reach the import dialog, not just the top rule
    assert '#UnderlayImportDialog QPushButton[variant="primary"]' in qss
    assert qss.count("#UnderlayImportDialog") > 1
