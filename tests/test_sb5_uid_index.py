"""SB5 Task 4 -- G-index (AC3): add / remove keep the index; a sprinkler child
resolves via its node; clear(), load and undo restore leave no stale entries;
a miss rebuilds once and is memoized until the next add / remove; a register
collision re-mints the incoming item."""
from firepro3d.room import Room
from tests._ph1_helpers import SQ, add_room, ph1_cleanup, save_raw, scene  # noqa: F401
from tests._sb5_helpers import FIND, managed_scene, one_of_each, save_load, uids


def test_add_and_remove_keep_the_index_without_a_rebuild(qapp):
    ms = scene()
    room = add_room(ms)
    n0 = ms._uid_rebuilds
    assert ms.element_by_uid(room._uid) is room
    assert ms._uid_rebuilds == n0                       # found by the add, no rebuild
    ms.removeItem(room)
    assert ms.element_by_uid(room._uid) is None


def test_a_sprinkler_child_resolves_via_its_node(qapp):
    ms = scene()
    n = ms.add_node(0.0, 0.0)
    spr = ms.add_sprinkler(n)
    assert spr.parentItem() is n                        # joined by setParentItem, not addItem
    assert ms.element_by_uid(spr._uid) is spr
    assert ms.element_by_uid(n._uid) is n
    ms.removeItem(n)                                    # the head leaves with its node
    assert ms.element_by_uid(spr._uid) is None
    assert ms.element_by_uid(n._uid) is None


def test_undo_restore_clear_and_load_leave_no_stale_entries(qapp, tmp_path):
    ms = scene()
    room = add_room(ms)
    old = room._uid
    ms.push_undo_state()
    add_room(ms)
    ms.push_undo_state()
    ms.undo()                                           # restore rebuilds every room
    live = ms.element_by_uid(old)
    assert live is ms._rooms[0] and live is not room and live.scene() is ms
    path, _raw = save_raw(ms, tmp_path)
    ms._clear_scene()                                   # the New / Open reset (Qt clear())
    assert old not in ms._uid_index
    assert ms.element_by_uid(old) is None
    ms2 = scene()
    assert ms2.load_from_file(path)
    assert ms2.element_by_uid(old) is ms2._rooms[0]
    assert all(it.scene() is ms2 for it in ms2._uid_index.values())


def test_a_miss_rebuilds_once_until_the_next_add_or_remove(qapp):
    ms = scene()
    n0 = ms._uid_rebuilds
    assert ms.element_by_uid("0" * 32) is None
    assert ms.element_by_uid("0" * 32) is None
    assert ms._uid_rebuilds == n0 + 1                   # the confirmed miss is memoized
    add_room(ms)
    assert ms.element_by_uid("0" * 32) is None
    assert ms._uid_rebuilds == n0 + 2                   # the add invalidated the memo


def test_a_register_collision_re_mints_the_incoming_item(qapp):
    ms = scene()
    first = add_room(ms)
    second = Room(list(SQ))
    second._uid = first._uid
    ms.addItem(second)
    assert second._uid != first._uid and len(second._uid) == 32
    assert ms.element_by_uid(first._uid) is first
    assert ms.element_by_uid(second._uid) is second
    assert ms._uid_repairs == 1


def test_gridline_by_uid_resolves_through_the_index(qapp):
    from tests._hosted_blocks_helpers import gridline
    ms = scene()
    gl = gridline(ms, (0, 0), (1000, 0), "A")
    room = add_room(ms)
    assert ms.gridline_by_uid(gl._uid) is gl
    assert ms.gridline_by_uid(room._uid) is None        # a live non-gridline is not a gridline
    assert ms.gridline_by_uid(None) is None


def test_saved_uids_applied_after_addItem_reach_the_index(qapp, tmp_path):
    """Reviewer note 2: a pipe (uid applied after scene.add_pipe), a sprinkler
    (child of its node via setParentItem, sprinkler_uid applied after) and a
    detail marker (DetailViewManager.from_list -> create_detail -> addItem, uid
    applied after) resolve by their SAVED uid through ``_uid_reindex``."""
    ms = managed_scene()
    one_of_each(ms)
    saved = uids(ms)
    out, _raw = save_load(ms, tmp_path)
    n0 = out._uid_rebuilds
    for kind in ("pipe", "sprinkler", "detail"):
        item = FIND[kind](out)
        assert item._uid == saved[kind], kind
        assert out.element_by_uid(saved[kind]) is item, kind
        assert out._uid_index[saved[kind]] is item, kind           # not a stale entry
    assert out._uid_rebuilds == n0                      # every hit came from the index, no rebuild
    assert out._uid_repairs == 0
    assert all(it.scene() is out for it in out._uid_index.values())


def test_uid_less_add_remove_keeps_the_miss_memo_but_a_uid_item_drops_it(qapp):
    """Preview items (no uid) are added / removed every mouse move; they must
    not invalidate a memoized dangling-host miss."""
    from PyQt6.QtWidgets import QGraphicsLineItem
    ms = scene()
    missing = "0" * 32
    assert ms.element_by_uid(missing) is None
    n0 = ms._uid_rebuilds
    line = QGraphicsLineItem(0, 0, 10, 10)               # plain item, no _uid
    ms.addItem(line)
    ms.removeItem(line)
    assert ms.element_by_uid(missing) is None
    assert ms._uid_rebuilds == n0                        # memo survived
    add_room(ms)                                         # carries a uid
    assert ms.element_by_uid(missing) is None
    assert ms._uid_rebuilds == n0 + 1                    # the uid item did rebuild


def test_a_memoized_miss_is_dropped_when_a_sprinkler_joins_its_node(qapp, monkeypatch):
    from firepro3d import sprinkler as sprinkler_mod
    ms = scene()
    n = ms.add_node(0.0, 0.0)
    uid = "a" * 32
    assert ms.element_by_uid(uid) is None
    assert ms.element_by_uid(uid) is None               # the miss is memoized
    monkeypatch.setattr(sprinkler_mod.element_uid, "new_uid", lambda: uid)
    n.add_sprinkler()                                    # joins by setParentItem only
    monkeypatch.undo()
    assert ms.element_by_uid(uid) is n.sprinkler
