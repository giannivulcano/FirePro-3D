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


def test_level_table_and_glyph_rules_present():
    """The Level Manager table joins the shared house-table rule set (no duplicated values)
    and the glyph QToolButton row has a house rule (mockup level-manager-tuner.html)."""
    qss = th.build_dialog_qss(th.detect())
    shared = [ln for ln in qss.splitlines() if "QTableView#underlayTable" in ln and "{" in ln]
    assert shared and all("QTableWidget#levelTable" in ln for ln in shared), shared
    assert f"QTableWidget#levelTable::item {{ padding: 0 {M.LEVEL_CELL_PAD}px; }}" in qss
    assert 'QToolButton[glyph="true"]' in qss
    assert f"padding: 7px {M.TABLE_HEADER_PAD_X}px" in qss
    # Table 9.75pt / header 10px are the house root + QHeaderView rules (one home each).
    root = next(ln for ln in qss.splitlines() if ln.startswith('QDialog[houseDialog="true"] {'))
    assert "font-size: 9.75pt" in root
    assert f"font-size: {M.TABLE_HEADER_PX}px; font-weight: 600;" in qss
