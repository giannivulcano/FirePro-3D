from firepro3d.underlay_import_dialog import UnderlayImportDialog
from firepro3d import theme


def test_import_dialog_has_own_objectname(qapp):
    dlg = UnderlayImportDialog(None)
    assert dlg.objectName() == "UnderlayImportDialog"
    dlg.deleteLater()


def test_theme_qss_styles_all_house_dialogs_via_property(qapp):
    """The unified builder scopes on QDialog[houseDialog="true"] — not per-dialog
    objectNames. Dialogs that set the property get the full chrome; asserting the
    marker and a representative child rule proves coverage reaches every consumer
    (UnderlayImportDialog, UnderlayManagerDialog, BlockManagerDialog …).
    """
    qss = theme.build_dialog_qss(theme.detect())
    # Unified scope marker — present once, covers every houseDialog consumer.
    assert 'QDialog[houseDialog="true"]' in qss
    # The import dialog sets the houseDialog property True at construction time.
    dlg = UnderlayImportDialog(None)
    assert dlg.property("houseDialog") is True
    dlg.deleteLater()
    # Representative child rules that must be present in the unified stylesheet.
    assert 'QPushButton[variant="primary"]' in qss
    assert "underlayTable" in qss
