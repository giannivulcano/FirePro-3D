"""Paper pass protocol (paper-space.md s6.2): the driver's unwind and the
guarded enter (design D2 / D6), and the per-family bare-item round trips
(Tasks 3-14). Builders, snapshot and the paper-settings fixture are the
characterization guards' (tests/test_paper_pass_characterization.py)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

import firepro3d.paper_display as pd
from firepro3d import paper_pass as pp
from tests.test_paper_pass_characterization import (_KINDS, _room_tagged,   # noqa: F401
                                                    paper_env, set_rows, snapshot)


class _Fake:
    def __init__(self, log, name, boom=False):
        self.log, self.name, self.boom = log, name, boom

    def exit_paper_pass(self, token):
        self.log.append(self.name)
        if self.boom:
            raise RuntimeError(self.name)


def test_unwind_runs_in_reverse_and_tolerates_a_raise():
    log = []
    a, b, c = _Fake(log, "a"), _Fake(log, "b", boom=True), _Fake(log, "c")
    saved = pp.PassTokens()
    for o in (a, b, c):
        saved.push(o, o.exit_paper_pass, object())
    with pytest.raises(RuntimeError, match="b"):
        pp.unwind(saved)
    assert log == ["c", "b", "a"]
    assert not saved, "every token is consumed, so a second unwind is a no-op"


def test_unwind_reraises_the_first_error_after_the_full_unwind():
    log = []
    a, b = _Fake(log, "a", boom=True), _Fake(log, "b", boom=True)
    saved = pp.PassTokens()
    for o in (a, b):
        saved.push(o, o.exit_paper_pass, None)
    with pytest.raises(RuntimeError, match="b"):      # b exits first (reverse)
        pp.unwind(saved)
    assert log == ["b", "a"]


def test_enter_guarded_unwinds_a_partly_entered_item():
    log = []

    def write():
        log.append("write")
        raise ValueError("mid")

    with pytest.raises(ValueError):
        pp.enter_guarded(lambda tok: log.append(("exit", tok)), "T", write)
    assert log == ["write", ("exit", "T")]


# ---------------------------------------------------------------------------
# Task 3: the generic family (DisplayableItemMixin, Room, WallOpening)
# ---------------------------------------------------------------------------

SCALE = 0.02


def _floor_opening(s):
    from firepro3d.floor_opening import FloorOpening
    slab = _KINDS["floor_slab"](s)
    s._floor_slabs.append(slab)
    op = FloorOpening([QPointF(-300, -300), QPointF(300, -300),
                       QPointF(300, 300), QPointF(-300, 300)], slab)
    slab.add_opening(op)
    if op.scene() is not s:
        s.addItem(op)
    return op


_GENERIC = {"wall": _KINDS["wall"], "room": _room_tagged,
            "wall_opening": _KINDS["wall_opening"], "floor_slab": _KINDS["floor_slab"],
            "floor_opening": _floor_opening, "roof": _KINDS["roof"],
            "node": _KINDS["node"]}
_CATEGORY = {"wall": "Wall", "room": "Room", "wall_opening": "Door",
             "floor_slab": "Floor", "floor_opening": "Opening", "roof": "Roof",
             "node": "Node"}


def _generic(request, make):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    request.node._pp_keep = [ms]
    return ms, _GENERIC[make](ms)


def test_generic_family_is_migrated_by_exact_type():
    from firepro3d.floor_opening import FloorOpening
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.node import Node
    from firepro3d.roof import RoofItem
    from firepro3d.room import Room
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    assert set(pp._migrated()) == {WallSegment, WallOpening, FloorOpening,
                                   FloorSlab, RoofItem, Room, Node}


@pytest.mark.parametrize("make", list(_GENERIC))
def test_generic_paper_category_drives_the_ladder(qapp, request, paper_env,
                                                  real_system_library, make):
    """R5: the class declares its row, and ``_category_for_item`` reads it."""
    _ms, item = _generic(request, make)
    assert item.paper_category == _CATEGORY[make]
    assert pd._category_for_item(item) == _CATEGORY[make]


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
@pytest.mark.parametrize("make", list(_GENERIC))
def test_generic_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                       make, authored):
    set_rows(paper_env, authored)
    ms, item = _generic(request, make)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row(item.paper_category), item, item.paper_category)
    tok = item.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert item._paper_pen_width == pytest.approx(ctx.lw_mm(cat) / SCALE)
    assert item.__dict__.get("_paper_fill_opaque") is True
    assert snapshot(ms) != before, "the enter changed nothing"
    if not authored:
        assert item._display_color == cat["color"]
    if make == "room":
        assert item.__dict__.get("_paper_no_fill") is True
        assert item._tag._paper_scale == pytest.approx(SCALE)
    if make == "wall_opening":
        assert item._paper_gap_color.name() == "#ffffff"
    item.exit_paper_pass(tok)
    assert snapshot(ms) == before


@pytest.mark.parametrize("make", list(_GENERIC))
def test_generic_owner_enters_itself_through_the_driver(qapp, request, paper_env,
                                                        real_system_library, make):
    """A migrated owner's token is its own exit, never the legacy adapter."""
    set_rows(paper_env, False)
    ms, item = _generic(request, make)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(-1500, -1500, 3000, 3000),
                                     paper_scale=SCALE)
    exits = [fn for it, fn, _tok in saved if it is item]
    assert exits == [item.exit_paper_pass]
    pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_generic_enter_raise_mid_write_unwinds_the_item(qapp, request, paper_env,
                                                        real_system_library,
                                                        monkeypatch):
    """D2: a raise mid-write leaves the item as it was, then re-raises."""
    set_rows(paper_env, False)
    ms, item = _generic(request, "room")
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Room"), item, "Room")
    from firepro3d import paper_display

    def boom(*a, **k):
        raise RuntimeError("tag")

    with monkeypatch.context() as m:
        m.setattr(paper_display, "_apply_block", boom)   # after the room's own write
        with pytest.raises(RuntimeError, match="tag"):
            item.enter_paper_pass(ctx, cat)
    assert snapshot(ms) == before
