"""Editor/Build slice 2 Task 2: walls carry a stable uid (constraint refs);
a pasted / duplicated / arrayed wall is a NEW wall (fresh uid) that takes
the Display Manager category defaults like a placed one (design s2 Wall uid;
slice 2 scope add 2026-10-26). Guard T10 (paste half)."""
from __future__ import annotations

import re

from PyQt6.QtCore import QPointF, QSettings

from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment

_HEX32 = re.compile(r"[0-9a-f]{32}")


def test_wall_uid_minted_and_round_trips(qapp):
    a = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    b = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    assert _HEX32.fullmatch(a._uid) and a._uid != b._uid
    d = a.to_dict()
    assert d["uid"] == a._uid
    assert WallSegment.from_dict(d)._uid == a._uid
    legacy = dict(d)
    legacy.pop("uid")                       # a pre-slice-2 .fpd wall record
    assert _HEX32.fullmatch(WallSegment.from_dict(legacy)._uid)


def _paste_walls(sc, items, offset=QPointF(0, 500)):
    data = sc._clipboard_item_dicts(items)
    return [it for it in sc.paste_items(offset, data=data, constraints=[])
            if isinstance(it, WallSegment)]


def test_pasted_wall_gets_a_new_uid(qapp):
    sc = Model_Space()
    try:
        src = WallSegment(QPointF(0, 0), QPointF(1000, 0))
        sc.addItem(src)
        sc._walls.append(src)
        (w,) = _paste_walls(sc, [src])
        assert _HEX32.fullmatch(w._uid) and w._uid != src._uid
    finally:
        sc.cleanup()


def test_pasted_wall_takes_category_defaults(qapp):
    """The pasted wall's stroke is the Display Manager 'Wall' default (what a
    placed wall gets via apply_category_defaults: the _display_color override,
    not the base _colour), not the source's (unset) override.
    conftest isolates QSettings; the key is removed afterwards anyway."""
    from firepro3d.display_manager import apply_category_defaults
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/color", "#ff00ff")
    sc = Model_Space()
    try:
        src = WallSegment(QPointF(0, 0), QPointF(1000, 0), color="#123456")
        sc.addItem(src)
        sc._walls.append(src)
        ref = WallSegment(QPointF(0, 0), QPointF(1, 0), color="#123456")
        apply_category_defaults(ref)            # the placement path's result
        assert ref._display_color == "#ff00ff" != src._display_color  # non-vacuous
        (w,) = _paste_walls(sc, [src])
        assert w._display_color == ref._display_color
    finally:
        s.remove("display/Wall/color")
        sc.cleanup()
