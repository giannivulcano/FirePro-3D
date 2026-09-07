"""HouseDialog structural contract (headless-meaningful: regions + footer order)."""
from PyQt6.QtWidgets import QLabel, QDialogButtonBox, QFrame
from firepro3d.house_dialog import HouseDialog


def _dlg(qapp):
    return HouseDialog(None, title="T", icon=None, min_width=300)


def test_regions_and_marker(qapp):
    d = _dlg(qapp)
    assert d.property("houseDialog") is True
    assert d._titlebar.objectName() == "shellHeader"
    body = d.findChild(QFrame, "dialogBody")
    assert body is not None


def test_footer_cancel_left_primary_right(qapp):
    d = _dlg(qapp)
    d.show()  # geometry needed for x-position comparison
    qapp.processEvents()
    btns = d.set_footer_buttons(primary=("Create", lambda: None), cancel=True)
    qapp.processEvents()
    box = d._footer_box
    cancel = box.button(QDialogButtonBox.StandardButton.Cancel)
    primary = btns["primary"]
    assert cancel.mapToGlobal(cancel.rect().topLeft()).x() < primary.mapToGlobal(primary.rect().topLeft()).x(), \
        "Cancel must sit left of the primary button"
    assert primary.property("variant") == "primary"
    d.close()


def test_danger_footer_variant(qapp):
    d = _dlg(qapp)
    btns = d.set_footer_buttons(primary=("Delete", lambda: None), danger=True)
    assert btns["primary"].property("variant") == "danger"


def test_header_context_slot(qapp):
    d = _dlg(qapp)
    d.set_header_context("myfile.pdf")
    labels = [w.text() for w in d._titlebar.findChildren(QLabel)]
    assert any("myfile.pdf" in x for x in labels)
