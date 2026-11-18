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


def test_generic_family_has_enter_and_exit():
    """Every generic owner is on the protocol (no legacy adapter remains)."""
    from firepro3d.floor_opening import FloorOpening
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.node import Node
    from firepro3d.roof import RoofItem
    from firepro3d.room import Room
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    for cls in (WallSegment, WallOpening, FloorOpening, FloorSlab, RoofItem, Room, Node):
        assert callable(getattr(cls, "enter_paper_pass", None)), cls
        assert callable(getattr(cls, "exit_paper_pass", None)), cls


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


def test_every_category_owner_class_has_enter_and_exit():
    """AC1: every owner class the base ladders named (generic, construction,
    annotation blocks incl. the two section BlockInstance subclasses, pipe,
    sprinkler / water supply, plan gridline, view markers, elevation
    gridline / level datum, every section proxy) enters and leaves the pass
    itself -- the driver has no adapter to fall back on; printed text has
    its print-pass pair."""
    from firepro3d.block_instance import BlockInstance
    from firepro3d.detail_view import DetailMarker
    from firepro3d.section_marker import SectionMarker
    from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem
    from firepro3d.floor_opening import FloorOpening
    from firepro3d.floor_slab import FloorSlab
    from firepro3d.gridline import GridlineItem
    from firepro3d.hydraulic_node_badge import HydraulicNodeBadge
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    from firepro3d.roof import RoofItem
    from firepro3d.room import Room
    from firepro3d.section_scene import _HostedBlockCopy, _SectionNoteCopy
    import firepro3d.section_scene as ss
    from firepro3d.sprinkler import Sprinkler
    from firepro3d.text_item import TextItem
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from firepro3d.water_supply import WaterSupply
    owners = {WallSegment, WallOpening, FloorOpening, FloorSlab, RoofItem, Room,
              Node, *_construction_classes(), BlockInstance, HydraulicNodeBadge,
              _HostedBlockCopy, _SectionNoteCopy, Pipe, Sprinkler, WaterSupply,
              GridlineItem, SectionMarker, DetailMarker, ElevGridlineItem,
              ElevDatumItem, *_proxy_classes(ss)}
    for cls in owners:
        assert callable(getattr(cls, "enter_paper_pass", None)), cls
        assert callable(getattr(cls, "exit_paper_pass", None)), cls
    assert callable(TextItem.enter_print_pass) and callable(TextItem.exit_print_pass)


def _proxy_classes(ss):
    """Every _ColourSrcMixin subclass in section_scene, read from the module
    (so a new proxy class fails here until it is named)."""
    found = {c for c in vars(ss).values()
             if isinstance(c, type) and issubclass(c, ss._ColourSrcMixin)
             and c is not ss._ColourSrcMixin}
    assert {c.__name__ for c in found} == {
        "_SrcRect", "_SrcLine", "_SrcEllipse", "_ElevProxyRect", "_ElevProxyLine",
        "_ElevProxyEllipse", "_ElevCutRect", "_ElevPipeSymbol", "_ElevCutEllipse",
        "_ElevEndOnSymbol"}
    return found


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


def test_driver_maps_each_child_onto_its_paper_owner(qapp, request, paper_env,
                                                     real_system_library):
    """D5: a hit child maps onto its ``paper_owner``: the room tag to the
    Room, the pipe label to the Pipe, the gridline bubble to the plan
    gridline, a view marker's head to its marker, an elevation gridline's
    bubble to its gridline, a section pipe label to its line proxy; a level
    datum's head is never mapped (``LevelDatumHead.paper_owner`` None, base
    picking: the datum enters it). The mapping is ``paper_owner`` alone -- a
    bubble under any parent maps onto that parent."""
    from firepro3d.gridline import GridlineBubble
    from tests.test_paper_pass_characterization import (_gridline, _marker_placed,
                                                        _pipe_labelled)
    sec, eg, dt = _elev_items(request)
    assert pp._owner_of(eg.bubble1) is eg and pp._owner_of(dt.head) is dt.head
    _psec, line, lab = _proxy_scene(request)
    assert pp._owner_of(lab) is line
    ms = _scene(request)
    room = _room_tagged(ms)
    pipe = _pipe_labelled(ms)
    gl = _gridline(ms)
    sec = _marker_placed(ms)
    det = _KINDS["detail_marker"](ms)
    assert pp._owner_of(room._tag) is room
    assert pp._owner_of(pipe.label) is pipe
    assert pp._owner_of(gl.bubble1) is gl
    assert pp._owner_of(sec.head_a) is sec and pp._owner_of(det.bubble) is det
    from PyQt6.QtWidgets import QGraphicsLineItem
    host = QGraphicsLineItem(0, 0, 10, 0)        # any Qt parent
    ms.addItem(host)
    elev_bubble = GridlineBubble(gl, parent=host)
    assert elev_bubble.paper_owner is host
    assert pp._owner_of(elev_bubble) is host


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


# ---------------------------------------------------------------------------
# Task 8: sprinkler / water supply (symbol path)
# ---------------------------------------------------------------------------

_SYMBOL_KEY = {"sprinkler": "Sprinkler", "water_supply": "Water Supply"}
_CANVAS_TINT = ("#123456", "#abcdef")


def _symbol(request, make):
    """A sprinkler (a child of its node) or a water supply, canvas-tinted so a
    missed tint restore shows."""
    from tests.test_paper_pass_characterization import _sprinkler
    ms = _scene(request)
    item = _sprinkler(ms) if make == "sprinkler" else _KINDS["water_supply"](ms)
    item.set_tint(*_CANVAS_TINT)
    return ms, item


@pytest.mark.parametrize("make", list(_SYMBOL_KEY))
def test_symbol_paper_category_drives_the_ladder(qapp, request, paper_env,
                                                 real_system_library, make):
    _ms, item = _symbol(request, make)
    assert item.paper_category == _SYMBOL_KEY[make]
    assert pd._category_for_item(item) == _SYMBOL_KEY[make]


@pytest.mark.parametrize("cls_name", ["Sprinkler", "WaterSupply"])
def test_symbol_mixin_wins_the_mro(cls_name):
    """``_SymbolPaperMixin`` sits first in both base lists (before
    ``DisplayableItemMixin`` on Sprinkler), so enter / exit are the symbol ones."""
    from firepro3d.displayable_item import DisplayableItemMixin
    from firepro3d.sprinkler import Sprinkler
    from firepro3d.symbol_block import SymbolBlockItem
    from firepro3d.symbol_block import _SymbolPaperMixin as M
    from firepro3d.water_supply import WaterSupply
    cls = {"Sprinkler": Sprinkler, "WaterSupply": WaterSupply}[cls_name]
    mro = cls.__mro__
    assert cls.__bases__[0] is M
    assert mro.index(M) < mro.index(SymbolBlockItem)
    if DisplayableItemMixin in mro:
        assert mro.index(M) < mro.index(DisplayableItemMixin)
    assert cls.enter_paper_pass is M.__dict__["enter_paper_pass"]
    assert cls.exit_paper_pass is M.__dict__["exit_paper_pass"]


@pytest.mark.parametrize("mode", ["row_off", "authored", "phase_color"])
@pytest.mark.parametrize("make", list(_SYMBOL_KEY))
def test_symbol_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                      make, mode):
    """The base (Sprinkler, WaterSupply) branch: the two width hooks, the SVG
    tint (row colour + fill off; phase colour + authored fill when the status
    forces the colour), the row opacity; the exit puts the canvas tint, the
    hooks and the opacity back."""
    from firepro3d import phase_display
    set_rows(paper_env, mode != "row_off")
    ms, item = _symbol(request, make)
    key = _SYMBOL_KEY[make]
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row(key), item, key)
    cat["opacity"] = 60
    if mode == "phase_color":
        cat["color"] = "#00ff00"
        cat[phase_display.FORCED] = frozenset({"color"})
    tok = item.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert item._paper_pen_width == pytest.approx(ctx.lw_mm(cat) / SCALE)
    assert item._paper_scale == SCALE
    assert item.opacity() == pytest.approx(0.6)
    if mode == "row_off":
        assert (item._display_color, item._display_fill_color) == (
            cat["color"], cat.get("fill"))
    elif mode == "phase_color":
        f = pd._model_colour_token(item, key, None, "fill")
        assert (item._display_color, item._display_fill_color) == (
            "#00ff00", f if f is not None else _CANVAS_TINT[1])
    assert snapshot(ms) != before, "the enter changed nothing"
    item.exit_paper_pass(tok)
    assert (item._display_color, item._display_fill_color) == _CANVAS_TINT
    assert (item._paper_pen_width, item._paper_scale) == (None, None)
    assert snapshot(ms) == before


@pytest.mark.parametrize("make", list(_SYMBOL_KEY))
def test_symbol_owner_enters_itself_through_the_driver(qapp, request, paper_env,
                                                       real_system_library, make):
    """One token for the symbol, its own exit (never the adapter)."""
    set_rows(paper_env, False)
    ms, item = _symbol(request, make)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(-1500, -1500, 3000, 3000),
                                     paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is item] == [item.exit_paper_pass]
        assert item._paper_scale == SCALE
        assert item._display_color == pd.load_paper_categories()[
            _SYMBOL_KEY[make]]["color"]
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before


@pytest.mark.parametrize("make", list(_SYMBOL_KEY))
def test_symbol_enter_raise_mid_write_unwinds_the_item(qapp, request, paper_env,
                                                       real_system_library, make):
    """D2: a raise at the opacity write (after the hooks and the tint) leaves
    the symbol as it was, then re-raises."""
    set_rows(paper_env, False)
    ms, item = _symbol(request, make)
    before = snapshot(ms)
    seen = []
    real = item.setOpacity

    def boom(v):
        if not seen:
            seen.append((item._paper_scale, item._display_color))
            raise RuntimeError("opacity")
        real(v)

    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    key = _SYMBOL_KEY[make]
    cat = ctx.merge(ctx.row(key), item, key)
    item.setOpacity = boom
    try:
        with pytest.raises(RuntimeError, match="opacity"):
            item.enter_paper_pass(ctx, cat)
    finally:
        del item.setOpacity
    assert seen == [(SCALE, cat["color"])], "the raise came after the hook and tint writes"
    assert snapshot(ms) == before


@pytest.mark.parametrize("make", list(_SYMBOL_KEY))
def test_nothing_maps_onto_a_symbol_owner(qapp, request, paper_env,
                                          real_system_library, make):
    """D5: a sprinkler / water supply owns no paper children -- no scene item
    maps onto it, and the sprinkler itself maps onto nothing (its node's pass
    never takes it)."""
    ms, item = _symbol(request, make)
    assert pp._owner_of(item) is item
    assert not [it for it in ms.items() if it is not item and pp._owner_of(it) is item]


# ---------------------------------------------------------------------------
# Task 9: plan gridline (bubbles, lock indicator) + AC6 gridline bubble
# ---------------------------------------------------------------------------

def _plan_gridline(request):
    """A plan gridline with both bubbles shown (their real prior opacity 0.4,
    AC6) and its lock indicator shown (as when selected)."""
    from tests.test_paper_pass_characterization import _gridline
    ms = _scene(request)
    gl = _gridline(ms)
    for b in (gl.bubble1, gl.bubble2):
        b.setOpacity(0.4)
    gl._lock_indicator.setVisible(True)
    return ms, gl


def test_gridline_paper_category_drives_the_ladder(qapp, request, paper_env,
                                                   real_system_library):
    _ms, gl = _plan_gridline(request)
    assert gl.paper_category == "Grid Line"
    assert pd._category_for_item(gl) == "Grid Line"


def test_gridline_bubbles_map_onto_the_gridline(qapp, request, paper_env,
                                                real_system_library):
    """D5: the two bubbles (Qt children; BoundLabelItem's parent rule, no
    override) are entered by their gridline; nothing else maps onto it (the
    lock indicator stays its own item)."""
    ms, gl = _plan_gridline(request)
    assert gl.bubble1.paper_owner is gl and gl.bubble2.paper_owner is gl
    assert "paper_owner" not in type(gl.bubble1).__dict__
    mapped = [it for it in ms.items() if it is not gl and pp._owner_of(it) is gl]
    assert len(mapped) == 2
    assert {id(it) for it in mapped} == {id(gl.bubble1), id(gl.bubble2)}
    assert pp._owner_of(gl._lock_indicator) is gl._lock_indicator


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
def test_gridline_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                        authored):
    """The base GridlineItem branch: line colour, the ``_paper_render`` /
    ``_paper_line_w`` / ``_paper_line_w_mm`` unit, the lock indicator hidden,
    each bubble's annotation hooks at opacity 1; the exit puts every one back,
    the bubbles' real prior opacity (0.4, AC6) included."""
    set_rows(paper_env, authored)
    ms, gl = _plan_gridline(request)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Grid Line"), gl, "Grid Line")
    cat["opacity"] = 60
    lw = ctx.lw_mm(cat)
    tok = gl.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert gl._paper_render is True
    assert gl._paper_line_w == pytest.approx(lw / SCALE)
    assert gl._paper_line_w_mm == pytest.approx(lw)
    assert gl.opacity() == pytest.approx(0.6)
    assert not gl._lock_indicator.isVisible()
    if not authored:
        assert gl._grid_color.name() == pd._paper_qcolor(cat["color"], gl).name()
    for b in (gl.bubble1, gl.bubble2):
        assert b._paper_scale == pytest.approx(SCALE)
        assert b._paper_pen_width == pytest.approx(lw / SCALE)
        assert b.opacity() == pytest.approx(1.0)
    assert snapshot(ms) != before, "the enter changed nothing"
    gl.exit_paper_pass(tok)
    assert gl._lock_indicator.isVisible()
    assert [b.opacity() for b in (gl.bubble1, gl.bubble2)] == [
        pytest.approx(0.4), pytest.approx(0.4)]
    assert snapshot(ms) == before


def test_gridline_hidden_bubble_is_not_entered(qapp, request, paper_env,
                                               real_system_library):
    """A hidden bubble is skipped (base: ``if b.isVisible()``) and keeps its
    hooks and its own opacity."""
    set_rows(paper_env, False)
    ms, gl = _plan_gridline(request)
    gl.bubble2.setVisible(False)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Grid Line"), gl, "Grid Line")
    tok = gl.enter_paper_pass(ctx, cat)
    assert gl.bubble1._paper_scale == pytest.approx(SCALE)
    assert gl.bubble2._paper_scale is None
    assert gl.bubble2.opacity() == pytest.approx(0.4)
    gl.exit_paper_pass(tok)
    assert snapshot(ms) == before


def test_gridline_owner_enters_itself_through_the_driver(qapp, request, paper_env,
                                                         real_system_library):
    """One token for the gridline (its own exit, never the adapter); the hit
    bubbles are entered by it, never as entries of their own."""
    set_rows(paper_env, False)
    ms, gl = _plan_gridline(request)
    crop = QRectF(-1500, -1500, 3000, 3000)
    hits = ms.items(crop)
    assert any(h is gl.bubble1 for h in hits), "setup: the bubble must be hit"
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, crop, paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is gl] == [gl.exit_paper_pass]
        kids = (gl.bubble1, gl.bubble2)
        assert not [it for it, _fn, _tok in saved if any(it is k for k in kids)]
        assert gl.bubble1._paper_scale == pytest.approx(SCALE)
        assert gl.bubble1.opacity() == pytest.approx(1.0)
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_gridline_enter_raise_mid_write_unwinds_the_gridline(qapp, request, paper_env,
                                                             real_system_library,
                                                             monkeypatch):
    """D2: a raise at bubble2 (after the line, the lock indicator and bubble1
    are entered) leaves the gridline, its lock indicator and both bubbles as
    they were, then re-raises."""
    set_rows(paper_env, False)
    ms, gl = _plan_gridline(request)
    before = snapshot(ms)
    real = pp.enter_block_hooks
    seen = []

    def boom_at_bubble2(inst, *a, **kw):
        if inst is gl.bubble2:
            seen.append((gl._paper_render, gl._lock_indicator.isVisible(),
                         gl.bubble1._paper_scale, gl.bubble1.opacity()))
            raise RuntimeError("bubble2")
        return real(inst, *a, **kw)

    monkeypatch.setattr(pp, "enter_block_hooks", boom_at_bubble2)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = ctx.merge(ctx.row("Grid Line"), gl, "Grid Line")
    with pytest.raises(RuntimeError, match="bubble2"):
        gl.enter_paper_pass(ctx, cat)
    assert seen == [(True, False, SCALE, pytest.approx(1.0))], (
        "the raise came after the line, lock and bubble1 writes")
    assert snapshot(ms) == before
    assert gl.bubble1.opacity() == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Task 10: section / detail markers (heads) + AC6 marker head
# ---------------------------------------------------------------------------

# kind -> (builder name, paper row, colour attr, head attrs)
_MARKER = {"cardinal": ("_marker_cardinal", "Elevation Marker", "_marker_color", ("head",)),
           "placed": ("_marker_placed", "Section Marker", "_marker_color",
                      ("head_a", "head_b")),
           "detail": ("detail_marker", "Detail Marker", "_tag_color", ("bubble",))}


def _marker(request, kind):
    """A view marker whose heads all carry a real prior opacity 0.4 (AC6)."""
    import tests.test_paper_pass_characterization as ch
    builder, _row, _attr, head_attrs = _MARKER[kind]
    ms = _scene(request)
    m = _KINDS[builder](ms) if builder in _KINDS else getattr(ch, builder)(ms)
    heads = [getattr(m, a) for a in head_attrs]
    assert all(h is not None and h.isVisible() for h in heads), "setup: heads shown"
    for h in heads:
        h.setOpacity(0.4)
    return ms, m, heads


@pytest.mark.parametrize("kind", list(_MARKER))
def test_marker_paper_category_drives_the_ladder(qapp, request, paper_env,
                                                 real_system_library, kind):
    """SB4d D7: a cardinal is the Elevation Marker row, a placed section the
    Section Marker row, a detail the Detail Marker row (per instance)."""
    _ms, m, _heads = _marker(request, kind)
    assert m.paper_category == _MARKER[kind][1]
    assert pd._category_for_item(m) == _MARKER[kind][1]


@pytest.mark.parametrize("kind", list(_MARKER))
def test_marker_heads_map_onto_the_marker(qapp, request, paper_env,
                                          real_system_library, kind):
    """D5: each head (a ViewMarkerHead Qt child; BoundLabelItem's parent
    rule, no override) is entered by its marker; nothing else maps onto it."""
    ms, m, heads = _marker(request, kind)
    for h in heads:
        assert h.paper_owner is m
        assert "paper_owner" not in type(h).__dict__
    mapped = [it for it in ms.items() if it is not m and pp._owner_of(it) is m]
    assert {id(it) for it in mapped} == {id(h) for h in heads}


def _marker_cat(ctx, m, kind):
    key = _MARKER[kind][1]
    return ctx.merge(ctx.row(key), m, key)


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
@pytest.mark.parametrize("kind", list(_MARKER))
def test_marker_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                      kind, authored):
    """The base marker branch: the line colour (+ the pen where the marker
    has one), the row opacity, each head's annotation hooks at opacity 1; the
    exit puts every one back, the heads' real prior opacity (0.4, AC6)
    included."""
    set_rows(paper_env, authored)
    ms, m, heads = _marker(request, kind)
    attr = _MARKER[kind][2]
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = _marker_cat(ctx, m, kind)
    cat["opacity"] = 60
    lw = ctx.lw_mm(cat)
    tok = m.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert m.opacity() == pytest.approx(0.6)
    if not authored:
        want = pd._paper_qcolor(cat["color"], m).name()
        assert getattr(m, attr).name() == want
        if hasattr(m, "pen"):
            assert m.pen().color().name() == want
    for h in heads:
        assert h._paper_scale == pytest.approx(SCALE)
        assert h._paper_pen_width == pytest.approx(lw / SCALE)
        assert h.opacity() == pytest.approx(1.0)
    assert snapshot(ms) != before, "the enter changed nothing"
    m.exit_paper_pass(tok)
    assert [h.opacity() for h in heads] == [pytest.approx(0.4)] * len(heads)
    assert snapshot(ms) == before


def test_marker_hidden_head_is_not_entered(qapp, request, paper_env,
                                           real_system_library):
    """A hidden head is skipped (base: ``if h.isVisible()``) and keeps its
    hooks and its own opacity."""
    set_rows(paper_env, False)
    ms, m, (ha, hb) = _marker(request, "placed")
    hb.setVisible(False)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    tok = m.enter_paper_pass(ctx, _marker_cat(ctx, m, "placed"))
    assert ha._paper_scale == pytest.approx(SCALE)
    assert hb._paper_scale is None
    assert hb.opacity() == pytest.approx(0.4)
    m.exit_paper_pass(tok)
    assert snapshot(ms) == before


@pytest.mark.parametrize("kind", ["placed", "detail"])
def test_marker_owner_enters_itself_through_the_driver(qapp, request, paper_env,
                                                       real_system_library, kind):
    """One token for the marker (its own exit, never the adapter); the hit
    heads are entered by it, never as entries of their own. (A cardinal is
    PAPER_EXCLUDED: the pick rule hides it.)"""
    set_rows(paper_env, False)
    ms, m, heads = _marker(request, kind)
    crop = QRectF(-3000, -3000, 6000, 6000)   # the detail bubble sits ~2 m below its crop
    hits = ms.items(crop)
    assert any(h is heads[0] for h in hits), "setup: a head must be hit"
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, crop, paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is m] == [m.exit_paper_pass]
        assert not [it for it, _fn, _tok in saved if any(it is h for h in heads)]
        for h in heads:
            assert h._paper_scale == pytest.approx(SCALE)
            assert h.opacity() == pytest.approx(1.0)
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before
    assert [h.opacity() for h in heads] == [pytest.approx(0.4)] * len(heads)


@pytest.mark.parametrize("kind", ["placed", "detail"])
def test_marker_enter_raise_mid_write_unwinds_the_marker(qapp, request, paper_env,
                                                         real_system_library,
                                                         monkeypatch, kind):
    """D2: a raise at the last head (after the marker line and every earlier
    head are entered) leaves the marker and its heads as they were, then
    re-raises."""
    set_rows(paper_env, False)
    ms, m, heads = _marker(request, kind)
    attr = _MARKER[kind][2]
    before = snapshot(ms)
    real = pp.enter_block_hooks
    seen = []

    def boom_at_last(inst, *a, **kw):
        if inst is heads[-1]:
            seen.append((getattr(m, attr).name(), m.opacity(),
                         [h._paper_scale for h in heads[:-1]]))
            raise RuntimeError("last head")
        return real(inst, *a, **kw)

    monkeypatch.setattr(pp, "enter_block_hooks", boom_at_last)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    cat = _marker_cat(ctx, m, kind)
    cat["opacity"] = 60
    with pytest.raises(RuntimeError, match="last head"):
        m.enter_paper_pass(ctx, cat)
    want = pd._paper_qcolor(cat["color"], m).name()
    assert seen == [(want, pytest.approx(0.6), [SCALE] * (len(heads) - 1))], (
        "the raise came after the line and the earlier heads were entered")
    assert snapshot(ms) == before
    assert [h.opacity() for h in heads] == [pytest.approx(0.4)] * len(heads)


# ---------------------------------------------------------------------------
# Task 11: elevation gridline / level datum (bubbles, head) + AC6 elevation head
# ---------------------------------------------------------------------------

def _elev_items(request):
    """The characterization elevation (``_sec_elevation``): its gridline and
    the Level 1 datum inside the crop, every bubble / head shown and carrying
    a real prior opacity 0.4 (AC6). Returns ``(scene, gridline, datum)``."""
    from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem
    from tests.test_paper_pass_characterization import _sec_elevation
    sec, _crop = _sec_elevation(request.getfixturevalue("section_scene_for"))
    (eg,) = [i for i in sec.items() if type(i) is ElevGridlineItem]
    (dt,) = [i for i in sec.items() if type(i) is ElevDatumItem and abs(i._v) < 1e-6]
    for h in (eg.bubble1, eg.bubble2, dt.head):
        assert h.isVisible(), "setup: bubbles / head shown"
        h.setOpacity(0.4)
    return sec, eg, dt


# kind -> (paper row, stored colour-source attr, head attrs)
_ELEV = {"gridline": ("Grid Line", "_grid_src", ("bubble1", "bubble2")),
         "datum": ("Level Datum", "_color_src", ("head",))}
_ELEV_CROP = QRectF(-7000.0, -4000.0, 10500.0, 5000.0)   # _sec_elevation's crop


def _elev(request, kind):
    sec, eg, dt = _elev_items(request)
    item = eg if kind == "gridline" else dt
    return sec, item, [getattr(item, a) for a in _ELEV[kind][2]]


def _elev_cat(ctx, item, kind):
    key = _ELEV[kind][0]
    return ctx.merge(ctx.row(key), item, key)


@pytest.mark.parametrize("kind", list(_ELEV))
def test_elev_paper_category_drives_the_ladder(qapp, request, paper_env,
                                               real_system_library, kind):
    """SB4c D4: the elevation gridline is the Grid Line row, the level datum
    the Level Datum row -- the ladder's existing answers."""
    _sec, item, _heads = _elev(request, kind)
    assert item.paper_category == _ELEV[kind][0]
    assert pd._category_for_item(item) == _ELEV[kind][0]


def test_elev_bubbles_map_onto_the_gridline(qapp, request, paper_env,
                                            real_system_library):
    """D5: each bubble (a Qt child; BoundLabelItem's parent rule, no
    override) is entered by its gridline; nothing else maps onto it."""
    sec, eg, heads = _elev(request, "gridline")
    for h in heads:
        assert h.paper_owner is eg
        assert "paper_owner" not in type(h).__dict__
    mapped = [it for it in sec.items() if it is not eg and pp._owner_of(it) is eg]
    assert {id(it) for it in mapped} == {id(h) for h in heads}


def test_level_datum_head_is_its_own_paper_owner(qapp, request, paper_env,
                                                 real_system_library):
    """The head is never mapped onto its datum (``paper_owner`` None): the
    datum enters it when the datum itself is hit; nothing maps onto the
    datum."""
    sec, dt, (head,) = _elev(request, "datum")
    assert head.paper_owner is None
    assert pp._owner_of(head) is head
    assert not [it for it in sec.items() if it is not dt and pp._owner_of(it) is dt]


def test_level_datum_head_hit_alone_leaves_the_datum_out(qapp, request, paper_env,
                                                         real_system_library):
    """Base picking (AC3): the head's hit shape is its bounds rect, the
    datum's only its block outline, so a crop can hit the head and miss the
    datum (the characterization ``sec_walls`` view). The datum -- and the
    line ``drawForeground`` paints from it -- then stays out of the pass."""
    from firepro3d.section_scene import ElevDatumItem
    from tests.test_paper_pass_characterization import _sec_walls
    set_rows(paper_env, False)
    sec, crop = _sec_walls(request.getfixturevalue("section_scene_for"))
    hits = sec.items(crop)
    alone = [i for i in sec.items() if type(i) is ElevDatumItem
             and any(h is i.head for h in hits) and not any(h is i for h in hits)]
    assert alone, "setup: a datum head hit without its datum"
    dt = alone[0]
    before = snapshot(sec)
    saved = pd.apply_paper_overrides(sec, crop, paper_scale=SCALE)
    try:
        assert not [it for it, _fn, _tok in saved if it is dt or it is dt.head]
        assert dt._paper_render is False and dt.head._paper_scale is None
    finally:
        pd.restore_model_display(saved)
    assert snapshot(sec) == before


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
@pytest.mark.parametrize("kind", list(_ELEV))
def test_elev_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                    kind, authored):
    """The base elevation branch: the LINE (``_paper_render`` /
    ``_paper_line_w`` / ``_paper_line_w_mm``, the row colour source when the
    row is off), the row opacity, each bubble / the head's annotation hooks
    at opacity 1; the exit puts every one back, the heads' real prior opacity
    (0.4, AC6) included."""
    set_rows(paper_env, authored)
    sec, item, heads = _elev(request, kind)
    attr = _ELEV[kind][1]
    src_before = getattr(item, attr)
    before = snapshot(sec)
    ctx = pp.PaperPassContext(sec, QRectF(), SCALE)
    cat = _elev_cat(ctx, item, kind)
    cat["opacity"] = 60
    lw = ctx.lw_mm(cat)
    tok = item.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert item._paper_render is True
    assert item._paper_line_w_mm == pytest.approx(lw)
    assert item._paper_line_w == pytest.approx(lw / SCALE)
    assert item.opacity() == pytest.approx(0.6)
    assert getattr(item, attr) == (src_before if authored else cat["color"])
    for h in heads:
        assert h._paper_scale == pytest.approx(SCALE)
        assert h._paper_pen_width == pytest.approx(lw / SCALE)
        assert h.opacity() == pytest.approx(1.0)
    assert snapshot(sec) != before, "the enter changed nothing"
    item.exit_paper_pass(tok)
    assert [h.opacity() for h in heads] == [pytest.approx(0.4)] * len(heads)
    assert snapshot(sec) == before


def test_elev_hidden_bubble_is_not_entered(qapp, request, paper_env,
                                           real_system_library):
    """A hidden bubble is skipped (base: ``if h.isVisible()``) and keeps its
    hooks and its own opacity."""
    set_rows(paper_env, False)
    sec, eg, (b1, b2) = _elev(request, "gridline")
    b2.setVisible(False)
    before = snapshot(sec)
    ctx = pp.PaperPassContext(sec, QRectF(), SCALE)
    tok = eg.enter_paper_pass(ctx, _elev_cat(ctx, eg, "gridline"))
    assert b1._paper_scale == pytest.approx(SCALE)
    assert b2._paper_scale is None
    assert b2.opacity() == pytest.approx(0.4)
    eg.exit_paper_pass(tok)
    assert snapshot(sec) == before


@pytest.mark.parametrize("kind", list(_ELEV))
def test_elev_owner_enters_itself_through_the_driver(qapp, request, paper_env,
                                                     real_system_library, kind):
    """One token for the owner (its own exit, never the adapter); the hit
    bubbles / head are entered by it, never as entries of their own."""
    set_rows(paper_env, False)
    sec, item, heads = _elev(request, kind)
    hits = sec.items(_ELEV_CROP)
    assert any(h is heads[0] for h in hits), "setup: a bubble / head must be hit"
    before = snapshot(sec)
    saved = pd.apply_paper_overrides(sec, _ELEV_CROP, paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is item] == [item.exit_paper_pass]
        assert not [it for it, _fn, _tok in saved if any(it is h for h in heads)]
        for h in heads:
            assert h._paper_scale == pytest.approx(SCALE)
            assert h.opacity() == pytest.approx(1.0)
    finally:
        pd.restore_model_display(saved)
    assert snapshot(sec) == before
    assert [h.opacity() for h in heads] == [pytest.approx(0.4)] * len(heads)


@pytest.mark.parametrize("kind", list(_ELEV))
def test_elev_enter_raise_mid_write_unwinds_the_owner(qapp, request, paper_env,
                                                      real_system_library,
                                                      monkeypatch, kind):
    """D2: a raise at the last bubble / the head (after the line, the
    opacity and every earlier bubble are entered) leaves the owner and its
    bubbles / head as they were, then re-raises."""
    set_rows(paper_env, False)
    sec, item, heads = _elev(request, kind)
    before = snapshot(sec)
    real = pp.enter_block_hooks
    seen = []

    def boom_at_last(inst, *a, **kw):
        if inst is heads[-1]:
            seen.append((item._paper_render, item.opacity(),
                         [h._paper_scale for h in heads[:-1]]))
            raise RuntimeError("last head")
        return real(inst, *a, **kw)

    monkeypatch.setattr(pp, "enter_block_hooks", boom_at_last)
    ctx = pp.PaperPassContext(sec, QRectF(), SCALE)
    cat = _elev_cat(ctx, item, kind)
    cat["opacity"] = 60
    with pytest.raises(RuntimeError, match="last head"):
        item.enter_paper_pass(ctx, cat)
    assert seen == [(True, pytest.approx(0.6), [SCALE] * (len(heads) - 1))], (
        "the raise came after the line, the opacity and the earlier bubbles")
    assert snapshot(sec) == before
    assert [h.opacity() for h in heads] == [pytest.approx(0.4)] * len(heads)


# ---------------------------------------------------------------------------
# Task 12: section proxies (_ColourSrcMixin) + the section pipe label
# ---------------------------------------------------------------------------

def _proxy_scene(request):
    """One placed section holding every live proxy class: a cut wall
    (``_ElevCutRect``), a wall beyond with a window (void ``_ElevProxyRect``,
    frame ``_SrcRect``, sill ``_SrcLine``), a labelled line pipe
    (``_ElevProxyLine`` + ``_ElevPipeLabel``), a cut pipe
    (``_ElevCutEllipse``), an end-on pipe (``_ElevEndOnSymbol``) and a
    sprinkler (``_ElevProxyEllipse``). Every proxy and the label carry a real
    prior opacity 0.4. Returns ``(scene, line, label)``."""
    import os

    import firepro3d
    from firepro3d import block_library
    from firepro3d.section_scene import _ROLE_SOURCE, _ColourSrcMixin, _ElevProxyLine
    from firepro3d.wall_opening import WallOpening
    from tests.test_section_classification import _placed_scene, _wall
    from tests.test_section_pipe_symbols import _pipe
    ms, sec = _placed_scene(request.getfixturevalue("section_scene_for"),
                            (0.0, 0.0), (10000.0, 0.0), 4000.0)
    ms.register_block_definition(block_library.load_block_file(os.path.join(
        os.path.dirname(firepro3d.__file__), "system_blocks", "Tags", "PipeLabel.fpdb")))
    _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))              # crosses the cut
    beyond = _wall(ms, (500.0, -2000.0), (6000.0, -2000.0))
    beyond.openings.append(WallOpening(wall=beyond, feature_id="window_900",
                                       offset_along=1000.0))
    pipe = _pipe(ms, (2000.0, -1000.0, 2500.0), (6000.0, -1000.0, 2500.0))   # line + label
    n1 = ms.add_node(8000.0, -1000.0); n2 = ms.add_node(8000.0, 1000.0)
    ms.add_pipe(n1, n2)                                        # cut pipe
    n1.z_pos = 2000.0; n2.z_pos = 3000.0
    _pipe(ms, (9000.0, -1000.0, 2500.0), (9000.0, -3000.0, 2500.0))   # end-on "C"
    ms.add_sprinkler(ms.add_node(5000.0, -1500.0))
    sec.rebuild()
    request.node._pp_keep = [*getattr(request.node, "_pp_keep", []), ms, sec]
    (line,) = [i for i in sec.items()
               if type(i) is _ElevProxyLine and i.data(_ROLE_SOURCE) is pipe]
    lab = line.pipe_label
    assert lab is not None and lab.isVisible(), "setup: the line owns a shown label"
    for it in sec.items():
        if isinstance(it, _ColourSrcMixin) or it is lab:
            it.setOpacity(0.4)
    return sec, line, lab


_PROXY_CROP = QRectF(-1000.0, -6000.0, 12000.0, 12000.0)   # the whole section


# The live _ColourSrcMixin classes (exact type) -> the row the scene gives them.
# _SrcEllipse and _ElevPipeSymbol are never instantiated bare (bases only).
_PROXY_CLS = {"_ElevCutRect": "Wall", "_ElevProxyRect": "Wall", "_SrcRect": "Window",
              "_SrcLine": "Window", "_ElevProxyLine": "Pipe", "_ElevCutEllipse": "Pipe",
              "_ElevEndOnSymbol": "Pipe", "_ElevProxyEllipse": "Sprinkler"}


def _proxy_of(sec, cls_name):
    """The first proxy of exact type *cls_name* that carries a paper row."""
    return next(i for i in sec.items() if type(i).__name__ == cls_name
                and i._paper_cat == _PROXY_CLS[cls_name])


def _proxy_cat(ctx, item):
    key = item.paper_category
    return ctx.merge(ctx.row(key), item, key)


def test_proxy_paper_category_is_its_paper_cat(qapp, request, paper_env,
                                               real_system_library):
    """R5: a proxy's row is the ``_paper_cat`` the section gave it -- the
    ladder's existing answer; a proxy with none (the opening void) is None."""
    from firepro3d.section_scene import _ColourSrcMixin
    sec, _line, _lab = _proxy_scene(request)
    proxies = [i for i in sec.items() if isinstance(i, _ColourSrcMixin)]
    assert any(i._paper_cat is None for i in proxies), "setup: a proxy without a row"
    for it in proxies:
        assert it.paper_category == it._paper_cat
        assert pd._category_for_item(it) == it._paper_cat


def test_section_pipe_label_maps_onto_its_line(qapp, request, paper_env,
                                               real_system_library):
    """D5 / AC4: the section pipe label (host = the MODEL pipe, another
    scene) is entered by the line proxy that owns it; nothing else maps
    onto the line, and the line's hidden-children list is its label."""
    sec, line, lab = _proxy_scene(request)
    assert lab.paper_owner is line
    assert pp._owner_of(lab) is line
    assert [it for it in sec.items() if it is not line and pp._owner_of(it) is line] == [lab]
    assert line.paper_hidden_children() == (lab,)
    assert _proxy_of(sec, "_ElevCutRect").paper_hidden_children() == ()


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
def test_proxy_line_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                          authored):
    """The base proxy branch: the row colour source (row off), ``_src_alpha``
    None, the paper pen width, the row opacity; the label through the shared
    helper at its label opacity. The exit puts every one back, the paper
    pen width ABSENT again and the label's real prior opacity (0.4)."""
    from firepro3d import phase_display
    set_rows(paper_env, authored)
    sec, line, lab = _proxy_scene(request)
    line._src_alpha = 0.5                      # a real prior alpha to restore
    assert "_paper_pen_width" not in vars(line)
    srcs = (line._pen_src, line._brush_src, line._src_alpha)
    before = snapshot(sec)
    ctx = pp.PaperPassContext(sec, QRectF(), SCALE)
    cat = _proxy_cat(ctx, line)
    cat["opacity"] = 60
    row = ctx.row("Pipe")
    lab_cat = ctx.merge(row, line, keys=phase_display.LABEL_KEYS)
    tok = line.enter_paper_pass(ctx, cat)
    assert tok is not None
    assert line._pen_src == (srcs[0] if authored else cat["color"])
    assert line._src_alpha is None
    assert line._paper_pen_width == pytest.approx(ctx.lw_mm(cat) / SCALE)
    assert line.opacity() == pytest.approx(0.6)
    assert lab._paper_scale == pytest.approx(SCALE)
    assert lab._paper_pen_width == pytest.approx(ctx.lw_mm(row) / SCALE)
    assert lab.opacity() == pytest.approx(phase_display.label_opacity(lab_cat))
    assert snapshot(sec) != before, "the enter changed nothing"
    line.exit_paper_pass(tok)
    assert "_paper_pen_width" not in vars(line)
    assert (line._pen_src, line._brush_src, line._src_alpha) == srcs
    assert line.opacity() == pytest.approx(0.4) and lab.opacity() == pytest.approx(0.4)
    assert snapshot(sec) == before


@pytest.mark.parametrize("cls_name", list(_PROXY_CLS))
def test_proxy_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                     cls_name):
    """Each live proxy class: pen / brush / section sources, alpha, the paper
    pen width (absent after) and opacity come back (row off: every write)."""
    set_rows(paper_env, False)
    sec, _line, _lab = _proxy_scene(request)
    it = _proxy_of(sec, cls_name)
    before = snapshot(sec)
    ctx = pp.PaperPassContext(sec, QRectF(), SCALE)
    tok = it.enter_paper_pass(ctx, _proxy_cat(ctx, it))
    assert it._paper_pen_width is not None
    assert snapshot(sec) != before, "the enter changed nothing"
    it.exit_paper_pass(tok)
    assert "_paper_pen_width" not in vars(it)
    assert it.opacity() == pytest.approx(0.4)
    assert snapshot(sec) == before


def test_proxy_owner_enters_itself_through_the_driver(qapp, request, paper_env,
                                                      real_system_library):
    """One token per proxy (its own exit, never the adapter); the label is
    entered by its line, never as an entry of its own."""
    from firepro3d.section_scene import _ColourSrcMixin
    set_rows(paper_env, False)
    sec, line, lab = _proxy_scene(request)
    hits = sec.items(_PROXY_CROP)
    assert any(h is lab for h in hits), "setup: the label must be hit"
    before = snapshot(sec)
    saved = pd.apply_paper_overrides(sec, _PROXY_CROP, paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is line] == [line.exit_paper_pass]
        assert not [it for it, _fn, _tok in saved if it is lab]
        assert not [it for it, fn, _tok in saved if isinstance(it, _ColourSrcMixin)
                    and fn not in (it.exit_paper_pass, pp._vis_exit)]
        assert lab._paper_scale == pytest.approx(SCALE)
    finally:
        pd.restore_model_display(saved)
    assert snapshot(sec) == before
    assert lab.opacity() == pytest.approx(0.4)


def test_proxy_row_visible_off_hides_proxy_and_label(qapp, request, paper_env,
                                                     real_system_library):
    """A Pipe row with Visible off hides the line proxy AND its label for the
    pass (the driver, through ``paper_hidden_children``) and shows both
    again after; nothing else of the row is written."""
    set_rows(paper_env, False)
    paper_env.cats["Pipe"]["visible"] = False
    sec, line, lab = _proxy_scene(request)
    before = snapshot(sec)
    saved = pd.apply_paper_overrides(sec, _PROXY_CROP, paper_scale=SCALE)
    try:
        assert not line.isVisible() and not lab.isVisible()
        assert [fn for it, fn, _tok in saved if it is line] == [pp._vis_exit]
        assert [fn for it, fn, _tok in saved if it is lab] == [pp._vis_exit]
        assert "_paper_pen_width" not in vars(line) and lab._paper_scale is None
    finally:
        pd.restore_model_display(saved)
    assert line.isVisible() and lab.isVisible()
    assert snapshot(sec) == before


def test_proxy_enter_raise_mid_write_unwinds_the_proxy(qapp, request, paper_env,
                                                       real_system_library, monkeypatch):
    """D2: a raise at the label (after the proxy's own writes) leaves the
    line and its label as they were, then re-raises."""
    set_rows(paper_env, False)
    sec, line, lab = _proxy_scene(request)
    before = snapshot(sec)
    seen = []

    def boom(inst, *a, **kw):
        seen.append((inst is lab, line._paper_pen_width is not None))
        raise RuntimeError("label")

    monkeypatch.setattr(pp, "enter_block_hooks", boom)
    ctx = pp.PaperPassContext(sec, QRectF(), SCALE)
    with pytest.raises(RuntimeError, match="label"):
        line.enter_paper_pass(ctx, _proxy_cat(ctx, line))
    assert seen == [(True, True)], "the raise came after the proxy's own writes"
    assert "_paper_pen_width" not in vars(line)
    assert snapshot(sec) == before


# ---------------------------------------------------------------------------
# Task 13: the node enters its fitting (D9)
# ---------------------------------------------------------------------------

_FIT_TINT = ("#123456", "#abcdef")


def _fitting_node(request):
    """A plain node whose fitting draws a symbol, canvas-tinted (the Display
    Manager path: the wrapper's colours, re-applied to the symbol) so a missed
    tint restore shows."""
    from tests.test_paper_pass_characterization import _fitting_node as make
    ms = _scene(request)
    n = make(ms)
    f = n.fitting
    f._display_color, f._display_fill_color = _FIT_TINT
    f._reapply_display_effects()
    return ms, n


def _svg(item):
    from tests.test_paper_pass_characterization import _svg_identity
    return _svg_identity(item)


def test_fitting_symbol_maps_onto_its_node(qapp, request, paper_env, real_system_library):
    """D5: the fitting symbol (a Qt child of the node) is entered by its node."""
    _ms, n = _fitting_node(request)
    sym = n.fitting.symbol
    assert sym.paper_owner is n
    assert pp._owner_of(sym) is n


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
def test_node_enter_exit_round_trip_with_fitting(qapp, request, paper_env,
                                                 real_system_library, authored):
    """The node's generic look plus its fitting under the Fitting row: row
    off re-tints the symbol in the row colour and writes the wrapper colours;
    the row opacity lands on the symbol; the exit re-latches the canvas tint
    and puts the wrapper colours and the opacity back."""
    set_rows(paper_env, authored)
    paper_env.cats["Fitting"]["opacity"] = 60
    ms, n = _fitting_node(request)
    f, sym = n.fitting, n.fitting.symbol
    svg0, op0 = _svg(sym), sym.opacity()
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    tok = n.enter_paper_pass(ctx, ctx.merge(ctx.row("Node"), n, "Node"))
    assert tok is not None
    assert n._paper_pen_width is not None          # the node's own generic look
    assert sym.opacity() == pytest.approx(0.6)
    if authored:
        assert (f._display_color, f._display_fill_color) == _FIT_TINT
        assert _svg(sym) == svg0, "an As Authored hex tint is left alone"
    else:
        row = paper_env.cats["Fitting"]
        assert (f._display_color, f._display_fill_color) == (row["color"], row.get("fill"))
        assert _svg(sym) != svg0, "the symbol was not re-tinted in the row colour"
    n.exit_paper_pass(tok)
    assert (f._display_color, f._display_fill_color) == _FIT_TINT
    assert _svg(sym) == svg0, "the canvas tint was not re-latched"
    assert sym.opacity() == pytest.approx(op0)
    assert snapshot(ms) == before


def test_fitting_row_visible_off_hides_then_restores_the_symbol(
        qapp, request, paper_env, real_system_library):
    """A Fitting row with Visible off hides the symbol (only) for the pass;
    the node keeps its own look, and the exit shows the symbol again."""
    set_rows(paper_env, False)
    paper_env.cats["Fitting"]["visible"] = False
    ms, n = _fitting_node(request)
    f, sym = n.fitting, n.fitting.symbol
    svg0 = _svg(sym)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(-1500, -1500, 3000, 3000),
                                     paper_scale=SCALE)
    try:
        assert n.isVisible() and not sym.isVisible()
        assert n._paper_pen_width is not None
        assert (f._display_color, f._display_fill_color) == _FIT_TINT
        assert _svg(sym) == svg0
    finally:
        pd.restore_model_display(saved)
    assert sym.isVisible()
    assert snapshot(ms) == before


def test_node_owner_enters_its_fitting_through_the_driver(qapp, request, paper_env,
                                                          real_system_library):
    """One token for the node (its own exit); the fitting is never an entry
    of its own (no legacy tail entry, no symbol token)."""
    set_rows(paper_env, False)
    ms, n = _fitting_node(request)
    sym = n.fitting.symbol
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(-1500, -1500, 3000, 3000),
                                     paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is n] == [n.exit_paper_pass]
        assert not [it for it, _fn, _tok in saved if it is sym]
        assert n.fitting._display_color == paper_env.cats["Fitting"]["color"]
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_node_enter_raise_in_the_fitting_unwinds_node_and_fitting(
        qapp, request, paper_env, real_system_library):
    """D2 / D6: a raise at the symbol's opacity write (after the node's own
    writes and the fitting's tint) leaves node and fitting as they were."""
    set_rows(paper_env, False)
    ms, n = _fitting_node(request)
    f, sym = n.fitting, n.fitting.symbol
    svg0 = _svg(sym)
    before = snapshot(ms)
    seen = []
    real = sym.setOpacity

    def boom(v):
        if not seen:
            seen.append((n._paper_pen_width is not None, f._display_color))
            raise RuntimeError("opacity")
        real(v)

    ctx = pp.PaperPassContext(ms, QRectF(), SCALE)
    sym.setOpacity = boom
    try:
        with pytest.raises(RuntimeError, match="opacity"):
            n.enter_paper_pass(ctx, ctx.merge(ctx.row("Node"), n, "Node"))
    finally:
        del sym.setOpacity
    assert seen == [(True, paper_env.cats["Fitting"]["color"])], \
        "the raise came after the node's writes and the fitting's tint"
    assert (f._display_color, f._display_fill_color) == _FIT_TINT
    assert _svg(sym) == svg0
    assert snapshot(ms) == before


# ---------------------------------------------------------------------------
# Task 14: underlay groups and printed text enter / exit themselves
# ---------------------------------------------------------------------------

_UND_CROP = QRectF(-1500, -1500, 3000, 3000)


def _underlay_scene(request):
    """A registered vector underlay: layer "A" carries a token colour and a
    named weight (one stroke path + one NoPen text batch), layer "B" has no
    override (one raw-width cosmetic stroke path, ``data(7)``)."""
    from firepro3d.constants import TOKEN_AUTO
    from firepro3d.underlay import Underlay
    ms = _scene(request)
    rec = Underlay(type="dxf", path="x.dxf")
    rec.layer_overrides["A"] = {"colour": TOKEN_AUTO, "line_weight": "Thick"}
    geoms = [{"kind": "line", "x1": -800, "y1": 0, "x2": 800, "y2": 0, "layer": "A"},
             {"kind": "text", "text": "U", "x": 0.0, "y": 0.0, "size": 100.0,
              "valign": 3, "halign": 0, "twidth": 80.0, "layer": "A"},
             {"kind": "line", "x1": 0, "y1": -800, "x2": 0, "y2": 800, "layer": "B"}]
    group, _layers = ms._build_batched_underlay_group(geoms, rec)
    ms.underlays.append((rec, group))
    return ms, rec, group


def _und_children(group):
    """``{(layer, "stroke" | "text"): child}`` for the layer path children."""
    from PyQt6.QtCore import Qt
    out = {}
    for c in group.childItems():
        if c.data(1) is None:
            continue
        kind = "text" if c.pen().style() == Qt.PenStyle.NoPen else "stroke"
        out[(c.data(1), kind)] = c
    assert set(out) == {("A", "stroke"), ("A", "text"), ("B", "stroke")}, set(out)
    return out


def _und_state(group):
    from tests.test_paper_pass_characterization import _norm
    return {k: (_norm(c.pen()), _norm(c.brush()), c._colour_src)
            for k, c in _und_children(group).items()} | {
        "group": (group.isVisible(), round(group.opacity(), 6))}


@pytest.mark.parametrize("authored", [True, False], ids=["authored", "row_off"])
def test_underlay_enter_exit_round_trip(qapp, request, paper_env, real_system_library,
                                        authored):
    """s16.5: row off plots every layer in the Underlay row colour and drops a
    token ``_colour_src`` for the pass; row on keeps each layer's effective
    colour (a token resolves on paper: black). A named layer weight plots
    true mm (non-cosmetic); a raw width plots at the frozen pre-MW mapping.
    The exit puts every pen, brush and ``_colour_src`` back."""
    from firepro3d import underlay
    from firepro3d.constants import TOKEN_AUTO
    set_rows(paper_env, authored)
    ms, rec, group = _underlay_scene(request)
    ch = _und_children(group)
    b_width = float(ch[("B", "stroke")].data(7))
    st0 = _und_state(group)
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(_UND_CROP), SCALE)
    tok = underlay.enter_underlay_paper_pass(ctx, rec, group)
    assert tok is not None
    row_col = pd._paper_qcolor(paper_env.cats["Underlay"]["color"]).name()
    a_col = row_col if not authored else pd._paper_qcolor(TOKEN_AUTO).name()
    b_col = row_col if not authored else pd._paper_qcolor(
        rec.effective_layer_colour("B")).name()
    a, a_txt, b = ch[("A", "stroke")], ch[("A", "text")], ch[("B", "stroke")]
    assert a.pen().color().name() == a_col
    assert not a.pen().isCosmetic()
    assert a.pen().widthF() == pytest.approx(pd.resolve_line_weight_mm("Thick") / SCALE)
    assert a_txt.brush().color().name() == a_col
    assert b.pen().color().name() == b_col
    assert b.pen().isCosmetic()
    assert b.pen().widthF() == pytest.approx(pd.paper_legacy_pdf_px(b_width))
    assert a._colour_src == (TOKEN_AUTO if authored else None)
    assert _und_state(group) != st0
    underlay.exit_underlay_paper_pass(tok)
    assert a._colour_src == TOKEN_AUTO
    assert _und_state(group) == st0
    assert snapshot(ms) == before


@pytest.mark.parametrize("case", ["hidden", "opacity"])
def test_underlay_phase_status_hides_or_fades_the_group(qapp, request, paper_env,
                                                        real_system_library, case):
    """PH3 R5: a hidden status hides the group for the pass (children left
    alone); a status opacity sets the group opacity. The exit puts the
    group's visibility and opacity back."""
    from types import SimpleNamespace

    from firepro3d import phase_display, phase_registry, underlay
    from firepro3d.constants import PHASE_EXISTING
    set_rows(paper_env, False)
    ms, rec, group = _underlay_scene(request)
    rec.phase = PHASE_EXISTING
    group.setOpacity(0.8)
    st0 = _und_state(group)
    before = snapshot(ms)
    table = phase_registry.project_table()
    prior = table.graphics_of(PHASE_EXISTING).get("opacity")
    hidden = {PHASE_EXISTING} if case == "hidden" else set()
    phase_display.begin_pass(SimpleNamespace(
        phase_display=phase_display.PhaseDisplay(True, frozenset(hidden)),
        source_view_type="plan"))
    try:
        assert table.set_graphic(PHASE_EXISTING, "opacity", 40)
        ctx = pp.PaperPassContext(ms, QRectF(_UND_CROP), SCALE)
        tok = underlay.enter_underlay_paper_pass(ctx, rec, group)
        if case == "hidden":
            assert not group.isVisible()
            assert {k: v for k, v in _und_state(group).items() if k != "group"} \
                == {k: v for k, v in st0.items() if k != "group"}
        else:
            assert group.isVisible()
            assert group.opacity() == pytest.approx(0.4)
        underlay.exit_underlay_paper_pass(tok)
    finally:
        phase_display.end_pass()
        table.set_graphic(PHASE_EXISTING, "opacity", prior)
    assert group.isVisible() and group.opacity() == pytest.approx(0.8)
    assert _und_state(group) == st0
    assert snapshot(ms) == before


def test_underlay_enter_returns_none_for_a_missing_outside_or_deleted_group(
        qapp, request, paper_env, real_system_library):
    """No token (and no write) for a None group, a group outside the crop, or
    a group whose C++ object is gone (RuntimeError, e.g. a cache rebuild)."""
    from PyQt6 import sip

    from firepro3d import underlay
    set_rows(paper_env, False)
    ms, rec, group = _underlay_scene(request)
    st0 = _und_state(group)
    ctx = pp.PaperPassContext(ms, QRectF(50000, 50000, 100, 100), SCALE)
    assert underlay.enter_underlay_paper_pass(ctx, rec, None) is None
    assert underlay.enter_underlay_paper_pass(ctx, rec, group) is None
    assert _und_state(group) == st0
    ms.removeItem(group)
    sip.delete(group)
    ctx = pp.PaperPassContext(ms, QRectF(_UND_CROP), SCALE)
    assert underlay.enter_underlay_paper_pass(ctx, rec, group) is None


def test_underlay_enters_after_the_owners_through_the_driver(qapp, request, paper_env,
                                                             real_system_library):
    """One token per group, its own exit, pushed after every owner token
    (the base order: underlays after the item loop); no legacy token."""
    from firepro3d import underlay
    set_rows(paper_env, False)
    ms, rec, group = _underlay_scene(request)
    _KINDS["wall"](ms)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(_UND_CROP), paper_scale=SCALE)
    try:
        fns = [fn for _it, fn, _tok in saved]
        assert [it for it, fn, _tok in saved
                if fn is underlay.exit_underlay_paper_pass] == [group]
        i = fns.index(underlay.exit_underlay_paper_pass)
        assert i == len(saved) - 2                       # last but the context's own
        assert any(type(it).__name__ == "WallSegment" for it, _fn, _tok in saved[:i])
        assert _und_children(group)[("B", "stroke")].pen().color().name() \
            == pd._paper_qcolor(paper_env.cats["Underlay"]["color"]).name()
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before


def test_underlay_enter_raise_mid_write_unwinds_the_group(qapp, request, paper_env,
                                                         real_system_library):
    """D2 / D6: a raise at the second layer child's pen write (after the first
    was re-pened) leaves the group and every child as they were."""
    from firepro3d import underlay
    set_rows(paper_env, False)
    ms, rec, group = _underlay_scene(request)
    st0 = _und_state(group)
    before = snapshot(ms)
    stroke = [c for c in group.childItems() if c.data(1) is not None
              and c.pen().style().value != 0]
    first, second = stroke[0], stroke[1]
    seen = []
    real = second.setPen

    def boom(pen):
        if not seen:
            seen.append(_und_state(group) != st0)
            raise RuntimeError("pen")
        real(pen)

    ctx = pp.PaperPassContext(ms, QRectF(_UND_CROP), SCALE)
    second.setPen = boom
    try:
        with pytest.raises(RuntimeError, match="pen"):
            underlay.enter_underlay_paper_pass(ctx, rec, group)
    finally:
        del second.setPen
    assert seen == [True], "the raise came after an earlier child's write"
    assert first is not second
    assert _und_state(group) == st0
    assert snapshot(ms) == before


def _printed_text(request):
    from tests.test_paper_pass_characterization import _text_printed
    ms = _scene(request)
    return ms, _text_printed(ms)


def test_text_item_has_the_print_pass_pair():
    """N15: printed text enters / leaves the pass through its own print-pass
    pair (the driver calls it whenever the pass carries a print scale)."""
    from firepro3d.text_item import TextItem
    assert callable(TextItem.enter_print_pass) and callable(TextItem.exit_print_pass)


@pytest.mark.parametrize("prior", [None, (0.5, 0.1)], ids=["none", "set"])
def test_text_print_pass_round_trip(qapp, request, paper_env, prior):
    """N15: the printed factor ``(k, paper_scale)`` is set for the pass (the
    painted bounds follow); the exit puts back the prior value."""
    from firepro3d.annotative import printed_text_k
    ms, t = _printed_text(request)
    t.set_print_pass(prior)
    rect0 = t.boundingRect()
    before = snapshot(ms)
    ctx = pp.PaperPassContext(ms, QRectF(_UND_CROP), SCALE)
    tok = t.enter_print_pass(ctx)
    assert t._print_pass == (printed_text_k(20.0, SCALE), SCALE)
    assert t.boundingRect() != rect0
    t.exit_print_pass(tok)
    assert t._print_pass == prior
    assert t.boundingRect() == rect0
    assert snapshot(ms) == before


def test_printed_text_enters_itself_through_the_driver(qapp, request, paper_env):
    """A Printed schematic: one print token, the text's own exit, no legacy
    token. Without a print scale the text takes the category path, which
    (no paper row) leaves it alone -- as at base."""
    from firepro3d.annotative import printed_text_k
    ms, t = _printed_text(request)
    before = snapshot(ms)
    saved = pd.apply_paper_overrides(ms, QRectF(_UND_CROP), paper_scale=SCALE)
    try:
        assert [fn for it, fn, _tok in saved if it is t] == [t.exit_print_pass]
        assert t._print_pass == (printed_text_k(20.0, SCALE), SCALE)
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before
    ms.text_print_scale = None
    assert pd._category_for_item(t) is None
    saved = pd.apply_paper_overrides(ms, QRectF(_UND_CROP), paper_scale=SCALE)
    try:
        assert not [it for it, _fn, _tok in saved if it is t]
        assert t._print_pass is None
    finally:
        pd.restore_model_display(saved)
    assert snapshot(ms) == before
