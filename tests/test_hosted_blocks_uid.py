"""D3: gridlines carry a stable uid (AC10 part)."""
from PyQt6.QtCore import QPointF

from firepro3d.gridline import GridlineItem
from tests._hosted_blocks_helpers import gridline


def test_new_gridlines_get_distinct_uids(qapp, make_model_space):
    ms = make_model_space()
    a = gridline(ms, (0, 0), (1000, 0), "A")
    b = gridline(ms, (0, 500), (1000, 500), "A")      # duplicate label allowed
    assert len(a._uid) == 32 and a._uid != b._uid


def test_uid_round_trips_through_dict(qapp, make_model_space):
    ms = make_model_space()
    a = gridline(ms, (0, 0), (1000, 0), "A")
    d = a.to_dict()
    assert d["uid"] == a._uid
    assert GridlineItem.from_dict(d)._uid == a._uid


def test_legacy_dict_without_uid_gets_fresh_one(qapp, make_model_space):
    ms = make_model_space()
    d = gridline(ms, (0, 0), (1000, 0), "A").to_dict()
    del d["uid"]
    g1, g2 = GridlineItem.from_dict(d), GridlineItem.from_dict(d)
    assert len(g1._uid) == 32 and g1._uid != g2._uid


def test_array_copy_gets_new_uid(qapp, make_model_space):
    ms = make_model_space()
    src = gridline(ms, (0, 0), (1000, 0), "A")
    copies = src.array_copies(500.0, 2) + [src.offset_copy(250.0)]
    uids = {src._uid} | {c._uid for c in copies}
    assert len(uids) == 4


def test_paste_gives_gridline_a_new_uid(qapp, make_model_space):
    ms = make_model_space()
    src = gridline(ms, (0, 0), (1000, 0), "A")
    new = ms.paste_items(QPointF(0, 200), data=[src.to_dict()])
    gls = [i for i in new if isinstance(i, GridlineItem)]
    assert len(gls) == 1 and gls[0]._uid != src._uid
