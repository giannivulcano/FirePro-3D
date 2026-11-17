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
    assert {WallSegment, WallOpening, FloorOpening,
            FloorSlab, RoofItem, Room, Node} <= set(pp._migrated())


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


# ---------------------------------------------------------------------------
# Task 4: the construction family (geometry_2d's 8 shapes + FilledRegionItem)
# ---------------------------------------------------------------------------

def _polyline(s):
    from firepro3d.geometry_2d import PolylineItem
    pl = PolylineItem(QPointF(-800, 0))
    pl.append_point(QPointF(0, 500))
    pl.append_point(QPointF(800, 0))
    s.addItem(pl)
    return pl


_CONSTRUCTION = {"line": _KINDS["line"], "polyline": _polyline,
                 "rectangle": _KINDS["rectangle"], "circle": _KINDS["circle"],
                 "arc": _KINDS["arc"], "ellipse": _KINDS["ellipse"],
                 "spline": _KINDS["spline"], "polygon": _KINDS["polygon"],
                 "filled_region": _KINDS["filled_region"]}
_CONSTRUCTION_CLS = {"line": "LineItem", "polyline": "PolylineItem",
                     "rectangle": "RectangleItem", "circle": "CircleItem",
                     "arc": "ArcItem", "ellipse": "EllipseItem",
                     "spline": "SplineItem", "polygon": "RegularPolygonItem",
                     "filled_region": "FilledRegionItem"}


def _construction_classes():
    import firepro3d.geometry_2d as g
    from firepro3d.filled_region import FilledRegionItem
    return [FilledRegionItem if n == "FilledRegionItem" else getattr(g, n)
            for n in _CONSTRUCTION_CLS.values()]


def _construction(request, make):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    request.node._pp_keep = [ms]
    item = _CONSTRUCTION[make](ms)
    assert type(item).__name__ == _CONSTRUCTION_CLS[make]
    return ms, item


def test_construction_family_is_migrated_by_exact_type():
    """Both landed families, by exact type (subclasses take the legacy path)."""
    from firepro3d.floor_opening import FloorOpening
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.node import Node
    from firepro3d.roof import RoofItem
    from firepro3d.room import Room
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    assert set(pp._migrated()) == {WallSegment, WallOpening, FloorOpening,
                                   FloorSlab, RoofItem, Room, Node,
                                   *_construction_classes()}


@pytest.mark.parametrize("cls_name", list(_CONSTRUCTION_CLS.values()))
def test_construction_mixin_wins_the_mro(cls_name):
    """``_ConstructionPaperMixin`` sits before ``DisplayableItemMixin``, so the
    class's paper_category / enter / exit are the construction ones."""
    from firepro3d.displayable_item import DisplayableItemMixin
    from firepro3d.geometry_2d import _ConstructionPaperMixin as M
    (cls,) = [c for c in _construction_classes() if c.__name__ == cls_name]
    mro = cls.__mro__
    assert mro.index(M) < mro.index(DisplayableItemMixin)
    assert cls.paper_category is M.__dict__["paper_category"]
    assert cls.enter_paper_pass is M.__dict__["enter_paper_pass"]
    assert cls.exit_paper_pass is M.__dict__["exit_paper_pass"]


@pytest.mark.parametrize("make", list(_CONSTRUCTION))
def test_construction_paper_category(qapp, request, paper_env, real_system_library,
                                     make):
    """R5: Construction, or Reference Geometry while flagged; the ladder agrees."""
    _ms, item = _construction(request, make)
    assert item.paper_category == "Construction"
    assert pd._category_for_item(item) == "Construction"
    item.reference = True
    assert item.paper_category == "Reference Geometry"
    assert pd._category_for_item(item) == "Reference Geometry"


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
@pytest.mark.parametrize("make", list(_CONSTRUCTION))
def test_construction_enter_exit_round_trip(qapp, request, paper_env,
                                            real_system_library, make, authored):
    set_rows(paper_env, authored)
    ms, item = _construction(request, make)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row(item.paper_category), item, item.paper_category)
    cat["opacity"] = 60
    tok = item.enter_paper_pass(ctx, cat)
    assert tok is not None
    pen = item.pen()
    assert not pen.isCosmetic()
    assert pen.widthF() == pytest.approx(ctx.lw_mm(cat) / SCALE)
    assert item.opacity() == pytest.approx(0.6)
    if not authored:
        assert pen.color() == pd._paper_qcolor(cat["color"], item)
    assert snapshot(ms) != before, "the enter changed nothing"
    item.exit_paper_pass(tok)
    assert snapshot(ms) == before


def test_construction_named_weight_plots_its_own_mm(qapp, request, paper_env,
                                                    real_system_library):
    """LT2-5: a named authored weight replaces the row weight on paper."""
    set_rows(paper_env, True)
    ms, item = _construction(request, "line")
    item.style["weight"] = "Wide"
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Construction"), item, "Construction")
    tok = item.enter_paper_pass(ctx, cat)
    want = pd.resolve_line_weight_mm("Wide") / SCALE
    assert want != pytest.approx(ctx.lw_mm(cat) / SCALE)
    assert item.pen().widthF() == pytest.approx(want)
    item.exit_paper_pass(tok)
    assert snapshot(ms) == before


@pytest.mark.parametrize("make", list(_CONSTRUCTION))
def test_construction_owner_enters_itself_through_the_driver(
        qapp, request, paper_env, real_system_library, make):
    """A migrated construction item's token is its own exit, not the adapter."""
    set_rows(paper_env, False)
    ms, item = _construction(request, make)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(-1500, -1500, 3000, 3000),
                                     paper_scale=SCALE)
    exits = [fn for it, fn, _tok in saved if it is item]
    assert exits == [item.exit_paper_pass]
    pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_construction_enter_raise_mid_write_unwinds_the_item(
        qapp, request, paper_env, real_system_library):
    """D2: a raise after the pen and opacity writes leaves the item as it was."""
    set_rows(paper_env, False)
    ms, item = _construction(request, "line")
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Construction"), item, "Construction")
    cat["opacity"] = 60
    real_update, calls = item.update, []

    def update_once(*a):
        calls.append((item.opacity(), item.pen().widthF()))
        if len(calls) == 1:
            raise RuntimeError("update")
        return real_update(*a)

    item.update = update_once
    try:
        with pytest.raises(RuntimeError, match="update"):
            item.enter_paper_pass(ctx, cat)
    finally:
        del item.update
    assert calls[0] == pytest.approx((0.6, ctx.lw_mm(cat) / SCALE)), (
        "the raise came after the pen and opacity writes")
    assert snapshot(ms) == before
