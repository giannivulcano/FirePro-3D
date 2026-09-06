"""build_dialog_qss: marker-scoped, metrics-interpolated, no raw dialog objectnames."""
from firepro3d import theme as th
from firepro3d.theme import M


def test_scopes_on_marker_not_dialog_objectname():
    qss = th.build_dialog_qss(th.detect())
    assert 'QDialog[houseDialog="true"]' in qss
    assert "#UnderlayManagerDialog" not in qss
    assert "#UnderlayImportDialog" not in qss
    assert "#MakeBlockDialog" not in qss
    assert "#BlockManagerDialog" not in qss


def test_shared_child_objectnames_present():
    qss = th.build_dialog_qss(th.detect())
    for sel in ("#shellHeader", "#footerBar", "#dialogBody", "#detailsPanel",
                "#toolbarBar", "QTreeView#underlayTable", "QTableView#underlayTable"):
        assert sel in qss, f"missing shared selector {sel}"


def test_metrics_interpolated():
    qss = th.build_dialog_qss(th.detect())
    assert f"border-radius: {M.RADIUS_INPUT}px" in qss or f"border-radius:{M.RADIUS_INPUT}px" in qss


def test_no_raw_hex_only_tokens():
    qss = th.build_dialog_qss(th.detect())
    assert "$" not in qss  # all placeholders substituted
