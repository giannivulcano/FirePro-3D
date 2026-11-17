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

    def boom(*a, **k):
        raise RuntimeError("tag")

    with monkeypatch.context() as m:
        # the tag's hook writes (Task 5: the shared helper), after the room's own
        m.setattr(pp, "_block_hook_writes", boom)
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
    """Every landed family, by exact type (subclasses take the legacy path):
    generic (Task 3), construction (Task 4), annotation blocks (Task 5, with
    the two section BlockInstance subclasses the base ladder reached), pipe
    (Task 6; no Pipe subclass exists)."""
    from firepro3d.block_instance import BlockInstance
    from firepro3d.floor_opening import FloorOpening
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.hydraulic_node_badge import HydraulicNodeBadge
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    from firepro3d.roof import RoofItem
    from firepro3d.room import Room
    from firepro3d.section_scene import _HostedBlockCopy, _SectionNoteCopy
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    assert set(pp._migrated()) == {WallSegment, WallOpening, FloorOpening,
                                   FloorSlab, RoofItem, Room, Node,
                                   *_construction_classes(),
                                   BlockInstance, HydraulicNodeBadge,
                                   _HostedBlockCopy, _SectionNoteCopy, Pipe}


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


# ---------------------------------------------------------------------------
# Task 5: the shared annotation-block helper (D7) + BlockInstance,
# BoundLabelItem (owner mapping, D5), HydraulicNodeBadge
# ---------------------------------------------------------------------------

def _scene(request):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    request.node._pp_keep = [*getattr(request.node, "_pp_keep", []), ms]
    return ms


def _hooks(inst):
    return (inst._paper_pen_width, inst._paper_pen_color, inst._paper_scale,
            getattr(inst, "_paper_blocks_colour", None),
            getattr(inst, "_paper_fill_colour", None))


@pytest.mark.parametrize("make", ["block_instance", "bound_label"])
def test_block_hooks_helper_round_trip(qapp, request, paper_env, real_system_library,
                                       make):
    """D7 / R3: the helper writes the hook triple and the given opacity, and
    its exit puts back the hooks AND the real prior opacity (0.4, not 1)."""
    from tests.test_paper_pass_characterization import _block_instance
    set_rows(paper_env, True)
    ms = _scene(request)
    inst = (_block_instance(ms) if make == "block_instance"
            else _room_tagged(ms)._tag)
    assert type(inst).__name__ == {"block_instance": "BlockInstance",
                                   "bound_label": "BoundLabelItem"}[make]
    inst.setOpacity(0.4)
    hooks0 = _hooks(inst)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = dict(ctx.row("Blocks"))
    tok = pp.enter_block_hooks(inst, ctx, cat, True, 0.18, opacity=1.0)
    assert inst._paper_scale == pytest.approx(SCALE)
    assert inst._paper_pen_width == pytest.approx(0.18 / SCALE)
    assert inst.opacity() == pytest.approx(1.0)
    pp.exit_block_hooks(tok)
    assert _hooks(inst) == hooks0
    assert inst.opacity() == pytest.approx(0.4)
    assert snapshot(ms) == before


def test_block_hooks_helper_defaults_to_the_row_opacity_and_blocks_slots(
        qapp, request, paper_env, real_system_library):
    """opacity None -> the row opacity; blocks_hook -> the Blocks colour slot."""
    from tests.test_paper_pass_characterization import _block_instance
    set_rows(paper_env, False)
    ms = _scene(request)
    inst = _block_instance(ms)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = dict(ctx.row("Blocks"))
    cat["opacity"] = 60
    tok = pp.enter_block_hooks(inst, ctx, cat, False, ctx.lw_mm(cat), blocks_hook=True)
    assert inst.opacity() == pytest.approx(0.6)
    assert inst._paper_blocks_colour is not None
    assert inst._paper_pen_color == pd._paper_qcolor(cat["color"], inst)
    pp.exit_block_hooks(tok)
    assert inst._paper_blocks_colour is None
    assert snapshot(ms) == before


def test_block_hooks_helper_raise_mid_write_unwinds(qapp, request, paper_env,
                                                     real_system_library):
    """D2: a raise after the hook writes leaves the instance as it was."""
    from tests.test_paper_pass_characterization import _block_instance
    set_rows(paper_env, False)
    ms = _scene(request)
    inst = _block_instance(ms)
    inst.setOpacity(0.4)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = dict(ctx.row("Blocks"))
    real_update, calls = inst.update, []

    def update_once(*a):
        calls.append(inst._paper_scale)
        if len(calls) == 1:
            raise RuntimeError("update")
        return real_update(*a)

    inst.update = update_once
    try:
        with pytest.raises(RuntimeError, match="update"):
            pp.enter_block_hooks(inst, ctx, cat, False, 0.18, blocks_hook=True)
    finally:
        del inst.update
    assert calls[0] == pytest.approx(SCALE), "the raise came after the hook writes"
    assert snapshot(ms) == before


_ANNOT = {"block_instance": "Blocks", "placed_tag": "Blocks",
          "hydraulic_badge": "Hydraulic Badge"}


def _annot(request, make):
    from tests.test_paper_pass_characterization import _EXTRA
    ms = _scene(request)
    maker = _KINDS.get(make) or _EXTRA[make]
    return ms, maker(ms)


@pytest.mark.parametrize("make", list(_ANNOT))
def test_annotation_paper_category_drives_the_ladder(qapp, request, paper_env,
                                                     real_system_library, make):
    _ms, item = _annot(request, make)
    assert item.paper_category == _ANNOT[make]
    assert pd._category_for_item(item) == _ANNOT[make]


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
@pytest.mark.parametrize("make", list(_ANNOT))
def test_annotation_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                          make, authored):
    set_rows(paper_env, authored)
    ms, item = _annot(request, make)
    item.setOpacity(0.7)
    before = snapshot(ms)
    pos0 = item.pos()
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row(item.paper_category), item, item.paper_category)
    cat["opacity"] = 60
    tok = item.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert item._paper_scale == pytest.approx(SCALE)
    assert item._paper_pen_width == pytest.approx(ctx.lw_mm(cat) / SCALE)
    assert item.opacity() == pytest.approx(0.6)            # the row opacity
    if make == "hydraulic_badge":
        assert item.pos() != pos0, "the badge was not re-placed at the paper k"
    else:
        assert item._paper_blocks_colour is not None        # blocks_hook (WM3 D3)
    assert snapshot(ms) != before, "the enter changed nothing"
    item.exit_paper_pass(tok)
    assert item.pos() == pos0
    assert snapshot(ms) == before


@pytest.mark.parametrize("make", list(_ANNOT))
def test_annotation_owner_enters_itself_through_the_driver(
        qapp, request, paper_env, real_system_library, make):
    """A migrated annotation owner's token is its own exit, not the adapter."""
    set_rows(paper_env, False)
    ms, item = _annot(request, make)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(-1500, -1500, 3000, 3000),
                                     paper_scale=SCALE)
    exits = [fn for it, fn, _tok in saved if it is item]
    assert exits == [item.exit_paper_pass]
    pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_badge_and_view_title_are_their_own_paper_owner(qapp, request, paper_env,
                                                        real_system_library):
    """D5: the badge keeps its own row (never its node's); a view title too."""
    from PyQt6.QtWidgets import QGraphicsRectItem
    from firepro3d.view_title_label import ViewTitleLabel
    _ms, badge = _annot(request, "hydraulic_badge")
    assert badge.host is not None
    assert badge.paper_owner is None
    assert pp._owner_of(badge) is badge
    host = QGraphicsRectItem(0, 0, 10, 10)
    title = ViewTitleLabel(host)
    assert title.parentItem() is host
    assert title.paper_owner is None


def test_bound_label_paper_owner_is_its_host_or_parent(qapp, request, paper_env,
                                                      real_system_library):
    """D5: a top-level label / tag -> its host; a Qt-child bubble -> its parent."""
    from tests.test_paper_pass_characterization import _gridline, _pipe_labelled
    ms = _scene(request)
    room = _room_tagged(ms)
    pipe = _pipe_labelled(ms)
    gl = _gridline(ms)
    assert room._tag.parentItem() is None and room._tag.paper_owner is room
    assert pipe.label.parentItem() is None and pipe.label.paper_owner is pipe
    assert gl.bubble1.paper_owner is gl


def test_bound_label_host_in_another_scene_is_not_its_owner(qapp, request, paper_env,
                                                           real_system_library):
    """A top-level label whose host lives in another scene (a section's pipe
    label, host = the model pipe) never maps the pass onto that host."""
    from firepro3d.bound_label import BoundLabelItem
    from tests.test_paper_pass_characterization import _pipe_labelled
    plan, other = _scene(request), _scene(request)
    pipe = _pipe_labelled(plan)
    lab = BoundLabelItem(pipe, child=False)
    other.addItem(lab)
    assert lab.paper_owner is None
    assert pp._owner_of(lab) is lab


def test_driver_maps_a_label_only_onto_a_migrated_owner(qapp, request, paper_env,
                                                        real_system_library):
    """Until each owner's family lands, a hit label whose owner is not yet
    migrated stays its own (base) entry: the room tag maps to the Room and
    the pipe label to the Pipe (Task 6); the gridline bubble (Task 9) does not."""
    from tests.test_paper_pass_characterization import _gridline, _pipe_labelled
    ms = _scene(request)
    room = _room_tagged(ms)
    pipe = _pipe_labelled(ms)
    gl = _gridline(ms)
    assert pp._owner_of(room._tag) is room
    assert pp._owner_of(pipe.label) is pipe
    assert pp._owner_of(gl.bubble1) is gl.bubble1


def test_room_enters_its_tag_through_the_shared_helper(qapp, request, paper_env,
                                                       real_system_library,
                                                       monkeypatch):
    """Task 5 step 4: the Room tag enters via ``paper_pass.enter_block_hooks``
    at the label opacity. Its exit runs after the room's own (the base restore
    order): the room's opacity drags the top-level tag along (itemChange), so
    the tag's real prior opacity (0.4, not the room's 1.0) is put back last."""
    from firepro3d import phase_display
    set_rows(paper_env, False)
    ms, room = _generic(request, "room")
    room._tag.setOpacity(0.4)
    assert room.opacity() == pytest.approx(1.0)
    before = snapshot(ms)
    seen, order = [], []
    real_enter, real_exit = pp.enter_block_hooks, pp.exit_block_hooks

    def spy_enter(inst, *a, **kw):
        seen.append((inst, kw.get("opacity")))
        return real_enter(inst, *a, **kw)

    def spy_exit(tok):
        order.append(("tag", room.opacity()))
        return real_exit(tok)

    monkeypatch.setattr(pp, "enter_block_hooks", spy_enter)
    monkeypatch.setattr(pp, "exit_block_hooks", spy_exit)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Room"), room, "Room")
    cat["opacity"] = 60
    tok = room.enter_paper_pass(ctx, cat)
    lab_cat = ctx.merge(ctx.row("Room"), room, keys=phase_display.LABEL_KEYS)
    assert seen == [(room._tag, phase_display.label_opacity(lab_cat))]
    assert room._tag._paper_scale == pytest.approx(SCALE)
    room.exit_paper_pass(tok)
    assert order == [("tag", pytest.approx(1.0))], "the tag exits after the room"
    assert room._tag.opacity() == pytest.approx(0.4)
    assert snapshot(ms) == before


def test_room_hidden_tag_keeps_its_own_opacity(qapp, request, paper_env,
                                               real_system_library):
    """A hidden tag is not entered, but the room's opacity still drags it
    along; the exit puts its own prior opacity back (as the base restore)."""
    set_rows(paper_env, False)
    ms, room = _generic(request, "room")
    room._tag.setOpacity(0.4)
    room._tag.setVisible(False)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Room"), room, "Room")
    cat["opacity"] = 60
    tok = room.enter_paper_pass(ctx, cat)
    assert "tag" not in tok and room._tag._paper_scale is None
    room.exit_paper_pass(tok)
    assert room._tag.opacity() == pytest.approx(0.4)
    assert snapshot(ms) == before


# ---------------------------------------------------------------------------
# Task 6: pipe (riser + label)
# ---------------------------------------------------------------------------

def _pipe_kind(request, make):
    """("labelled") a horizontal pipe with its top-level label in the scene;
    ("riser") a vertical pipe drawing its riser symbol."""
    if make == "riser":
        from tests._sb4g_helpers import riser_scene
        ms, _nodes, p = riser_scene()
        request.node._pp_keep = [*getattr(request.node, "_pp_keep", []), ms]
        return ms, p
    from tests.test_paper_pass_characterization import _pipe_labelled
    ms = _scene(request)
    return ms, _pipe_labelled(ms)


def test_pipe_paper_category_drives_the_ladder(qapp, request, paper_env,
                                               real_system_library):
    _ms, p = _pipe_kind(request, "labelled")
    assert p.paper_category == "Pipe"
    assert pd._category_for_item(p) == "Pipe"


def test_pipe_children_map_onto_the_pipe(qapp, request, paper_env,
                                         real_system_library):
    """D5: the top-level label and the riser symbol are entered by their pipe."""
    _ms, p = _pipe_kind(request, "riser")
    rs = p._riser_symbol
    assert rs is not None and rs.scene() is p.scene()
    assert rs.paper_owner is p
    assert p.label.paper_owner is p
    assert pp._owner_of(rs) is p
    assert pp._owner_of(p.label) is p


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
@pytest.mark.parametrize("make", ["labelled", "riser"])
def test_pipe_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                    make, authored):
    """The base Pipe branch: pipe colour / weight / opacity, the riser's
    named-weight hooks, the label's annotation hooks at the label opacity; the
    exit puts every one back, the label's real prior opacity (0.4) included."""
    from firepro3d import phase_display
    set_rows(paper_env, authored)
    ms, p = _pipe_kind(request, make)
    p.label.setOpacity(0.4)
    lab_vis = p.label.isVisible()
    rs = p._riser_symbol
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    row = ctx.row("Pipe")
    cat = ctx.merge(row, p, "Pipe")
    cat["opacity"] = 60
    tok = p.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert p._paper_pen_width == pytest.approx(ctx.lw_mm(cat) / SCALE)
    assert p.opacity() == pytest.approx(0.6)
    if not authored:
        assert p._display_color == cat["color"]
    if make == "riser":
        assert rs._paper_pen_width == pytest.approx(ctx.lw_mm(cat) / SCALE)
        assert rs._paper_scale == SCALE
    if lab_vis:
        lab_cat = ctx.merge(row, p, keys=phase_display.LABEL_KEYS)
        assert p.label._paper_scale == pytest.approx(SCALE)
        assert p.label._paper_pen_width == pytest.approx(ctx.lw_mm(row) / SCALE)
        assert p.label.opacity() == pytest.approx(phase_display.label_opacity(lab_cat))
    assert snapshot(ms) != before, "the enter changed nothing"
    p.exit_paper_pass(tok)
    assert p.label.opacity() == pytest.approx(0.4)
    if rs is not None:
        assert rs._paper_scale is None
    assert snapshot(ms) == before


@pytest.mark.parametrize("make", ["labelled", "riser"])
def test_pipe_owner_enters_itself_through_the_driver(qapp, request, paper_env,
                                                     real_system_library, make):
    """One token for the pipe (its own exit, never the adapter); the hit label
    and riser are entered by it, never as entries of their own."""
    set_rows(paper_env, False)
    ms, p = _pipe_kind(request, make)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(-1500, -1500, 3000, 3000),
                                     paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is p] == [p.exit_paper_pass]
        kids = [p.label, p._riser_symbol]
        assert not [it for it, _fn, _tok in saved if any(it is k for k in kids)]
        if p.label.isVisible():
            assert p.label._paper_scale == pytest.approx(SCALE)
        if p._riser_symbol is not None:
            assert p._riser_symbol._paper_scale == SCALE
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_pipe_enter_raise_mid_write_unwinds_the_pipe(qapp, request, paper_env,
                                                     real_system_library,
                                                     monkeypatch):
    """D2: a raise at the label (after the pipe and riser writes) leaves the
    pipe, its riser and its label as they were, then re-raises."""
    set_rows(paper_env, False)
    ms, p = _pipe_kind(request, "riser")
    p.update_label()
    p.label.setVisible(True)
    before = snapshot(ms)
    seen = []

    def boom(inst, *a, **kw):
        seen.append(p._riser_symbol._paper_scale)
        raise RuntimeError("label")

    monkeypatch.setattr(pp, "enter_block_hooks", boom)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Pipe"), p, "Pipe")
    with pytest.raises(RuntimeError, match="label"):
        p.enter_paper_pass(ctx, cat)
    assert seen == [SCALE], "the raise came after the riser write"
    assert snapshot(ms) == before


# ---------------------------------------------------------------------------
# Task 7: a label / tag inside the crop enters through its owner (D5, AC4)
# ---------------------------------------------------------------------------

def test_room_tag_inside_crop_enters_its_room_owner_outside(qapp, request, paper_env,
                                                           real_system_library):
    """User ruling 2026-11-17 (keep the Task 5 room-tag behaviour): a Room whose
    boundary lies outside the crop and whose tag lies inside it is entered
    once, through the hit tag -- the tag plots at paper size in the Room row
    colour -- and both come back to their snapshot."""
    from firepro3d.room import Room
    from tests.test_paper_pass_characterization import _ink_near, _render_white
    set_rows(paper_env, False)
    paper_env.cats["Room"]["color"] = "#ff0000"      # the OWNER's row colour
    paper_env.cats["Blocks"]["color"] = "#0000ff"    # another row: never the tag's
    ms = _scene(request)
    room = Room(boundary=[QPointF(3000, 3000), QPointF(5000, 3000),
                          QPointF(5000, 5000), QPointF(3000, 5000)])
    ms.addItem(room)
    room.set_property("Room Name", "R1")
    room._update_label()
    tag = room._tag
    room.apply_grip(0, QPointF(0.0, 0.0))     # the tag grip drags it into the crop
    assert tag.pos() == QPointF(0.0, 0.0)
    assert tag.scene() is ms and tag.isVisible()
    crop = QRectF(-1500, -1500, 3000, 3000)
    box = tag.mapRectToScene(tag.boundingRect())
    assert not crop.intersects(room.sceneBoundingRect()), "setup: room in the crop"
    assert crop.intersects(box), "setup: the tag box must lie in the crop"
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, crop, paper_scale=SCALE)
    try:
        assert tag._paper_scale == pytest.approx(SCALE), "the tag did not plot at paper size"
        assert tag._paper_pen_color is not None
        assert tag._paper_pen_color.name() == "#ff0000"
        assert [fn for it, fn, _t in saved if it is room] == [room.exit_paper_pass]
        assert not [it for it, _fn, _t in saved if it is tag]
        img = _render_white(ms, crop, 600, 600)
        assert tag.pos() == QPointF(0.0, 0.0), "setup: the tag moved during the render"
        assert _ink_near(img, box, crop, (255, 0, 0)) > 0, (
            "the tag did not plot in the Room row colour")
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_room_with_body_and_tag_in_crop_enters_once(qapp, request, paper_env,
                                                   real_system_library):
    """Both the room body and its tag are hit: the room is entered exactly
    once (first-hit dedupe), the tag never as an entry of its own."""
    set_rows(paper_env, False)
    ms = _scene(request)
    room = _room_tagged(ms)
    tag = room._tag
    crop = QRectF(-1500, -1500, 3000, 3000)
    hits = ms.items(crop)
    assert any(h is room for h in hits) and any(h is tag for h in hits), (
        "setup: both the room and its tag must be hit")
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, crop, paper_scale=SCALE)
    try:
        assert [fn for it, fn, _t in saved if it is room] == [room.exit_paper_pass]
        assert not [it for it, _fn, _t in saved if it is tag]
        assert tag._paper_scale == pytest.approx(SCALE)
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before
