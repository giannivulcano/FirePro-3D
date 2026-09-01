from PyQt6.QtCore import QSettings
from firepro3d.underlay_mru import RecentSources


def _fresh_settings(tmp_path):
    s = QSettings(str(tmp_path / "mru.ini"), QSettings.Format.IniFormat)
    s.clear()
    return s


def test_add_then_list_most_recent_first(tmp_path):
    mru = RecentSources(_fresh_settings(tmp_path), cap=5)
    mru.add("/a.pdf"); mru.add("/b.dwg")
    assert mru.list() == ["/b.dwg", "/a.pdf"]


def test_dedupe_moves_to_front(tmp_path):
    mru = RecentSources(_fresh_settings(tmp_path), cap=5)
    mru.add("/a.pdf"); mru.add("/b.dwg"); mru.add("/a.pdf")
    assert mru.list() == ["/a.pdf", "/b.dwg"]


def test_cap_enforced(tmp_path):
    mru = RecentSources(_fresh_settings(tmp_path), cap=3)
    for p in ("/1", "/2", "/3", "/4"):
        mru.add(p)
    assert mru.list() == ["/4", "/3", "/2"]
