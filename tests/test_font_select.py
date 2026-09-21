from PyQt6.QtGui import QFontDatabase
from firepro3d.ui_kit import FontSelect


def test_font_select_lists_truetype_families(qapp):
    w = FontSelect()
    fams = [w.itemText(i) for i in range(w.count()) if w.itemData(i, w.ROLE_FAMILY)]
    assert any(f in fams for f in QFontDatabase.families())


def test_font_select_emits_family_and_pins_recents(qapp):
    w = FontSelect()
    seen = []
    w.fontChanged.connect(seen.append)
    target = QFontDatabase.families()[0]
    w.set_current_family(target)
    w.commit_current()                       # simulate an activated selection
    assert seen and seen[-1] == target
    assert w.recent_families()[0] == target  # pinned at top, max 5


def test_font_select_current_family_roundtrip(qapp):
    w = FontSelect()
    fam = QFontDatabase.families()[1]
    w.set_current_family(fam)
    assert w.current_family() == fam


def test_font_select_recents_capped_at_five(qapp):
    w = FontSelect()
    fams = QFontDatabase.families()[:7]
    for f in fams:
        w.set_current_family(f)
        w.commit_current()
    assert len(w.recent_families()) <= 5
    assert w.recent_families()[0] == fams[-1]   # most-recent first


def test_set_current_family_selects_family_row_not_header(qapp):
    w = FontSelect()
    fam = QFontDatabase.families()[0]
    w.set_current_family(fam)
    assert w.itemData(w.currentIndex(), w.ROLE_FAMILY) == fam
