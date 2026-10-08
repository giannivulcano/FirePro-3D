"""LT5 C3 -- ends on placed blocks: both op paths (plain + linetyped) on
paper, E7 placement Weight override, E6 cascade render half, end-def edit,
missing badge, bounds, end-less fast path."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor

from firepro3d import paper_display as pd
from firepro3d import theme
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.lt3_support import make_linetype
from tests.lt5_support import arrow, dot, round_end, set_ends
from tests.test_lt1_block_paper import _export, _render_model
from tests.test_lt3_pdf import _viewport_hlines
from tests.test_lt3_primitive_paint import _render
from tests.test_lt5_render_raw import _S, _close, _fills, _line_span
from tests.wm2_support import scene_with, sprinkler_def

_PLAN = QRectF(-2000.0, -2000.0, 4000.0, 4000.0)      # 0.1 px/mm onto 400 x 400


def _line_block(start=None, finish=None, linetype="continuous",
                weight="Thickest", name="E"):
    ln = LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 0.0))
    ln.style["weight"] = weight
    ln.style["linetype"] = linetype
    set_ends(ln, start=start, finish=finish)
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[ln.to_dict()], origin=(0.0, 0.0))


def _blob(img, cx=350, cy=200, r=14, band=3):
    """Lit pixels around the finish end (model x = 1500), the line's own
    rows (+-band) excluded."""
    return sum(1 for x in range(cx - r, cx + r + 1) for y in range(cy - r, cy + r + 1)
               if abs(y - cy) > band and QColor(img.pixel(x, y)).lightness() > 128)


@pytest.mark.parametrize("linetyped", [False, True])
def test_both_op_paths_trim_the_stroke_and_draw_the_end_on_paper(qapp, tmp_path, linetyped):
    save_paper_color_mode(PaperColorMode.BW)
    a = arrow()
    defs, ref = [a], "continuous"
    if linetyped:
        lt = make_linetype(length=9.0, dashes=((0.0, 6.0),))
        defs.append(lt)
        ref = lt.id
    d = _line_block(finish=a.id, linetype=ref)
    ms, inst = scene_with([*defs, d], d.id)
    assert bool(inst._linetype_ids(inst.render_ops())) == linetyped   # the path under test
    pdf = _export(tmp_path, ms, _S, f"both_{linetyped}.pdf")
    end = _line_span(tmp_path)[1]                 # measured end-less finish (export ground truth)
    fills = _fills(pdf)
    assert len(fills) == 1, fills
    assert abs(fills[0][2] - end) <= 0.05 and abs((fills[0][2] - fills[0][0]) - 3.0) <= 0.05
    xs = [x1 for _x0, x1, _w in _viewport_hlines(pdf)]
    assert xs and max(xs) <= end - 3.0 + 0.05                         # dashes / stroke stop at the trim
    if not linetyped:
        assert abs(max(xs) - (end - 3.0)) <= 0.05


@pytest.mark.parametrize("weight", ["Thinner", "Thin"])   # Medium 0.25 / Heavy 0.35 (MW-6)
def test_e7_placement_weight_override_scales_weight_relative_ends(qapp, tmp_path, weight):
    save_paper_color_mode(PaperColorMode.BW)
    r = round_end()
    d = _line_block(finish=r.id)                     # authored Thickest (0.70)
    ms, _inst = scene_with([r, d], d.id, {"weight": weight})
    pdf = _export(tmp_path, ms, _S, f"e7_{weight}.pdf")
    mm = pd.resolve_line_weight_mm(weight)
    lines = [l for l in _viewport_hlines(pdf) if l[1] - l[0] > 30.0]
    assert lines and {round(w, 3) for *_, w in lines} == {round(mm, 3)}   # override plotted
    fills = _fills(pdf)
    assert len(fills) == 1, fills
    x0, _y0, x1, _y1 = fills[0]
    assert abs((x1 - x0) / 2.0 - mm / 2.0) <= 0.01                 # radius = half the override
    assert abs((x0 + x1) / 2.0 - _line_span(tmp_path)[1]) <= 0.05  # still on the finish end


def test_e6_linetype_default_end_draws_follows_edits_and_yields_to_explicit(qapp):
    dt = dot(radius=1.0)                             # Fixed 1 mm -> 100 mm on 1:100 -> r 10 px
    lt = make_linetype(length=9.0, dashes=((0.0, 6.0),))
    rep = lt.repeat
    rep["ends"] = {"finish": dt.id}
    lt.set_repeat(rep)
    d = _line_block(linetype=lt.id, weight="Thinnest")          # By Linetype ends
    ms, _ = scene_with([dt, lt, d], d.id)
    assert _blob(_render(ms, _PLAN, 400, 400)) > 100            # the default end draws
    d2 = _line_block(linetype=lt.id, weight="Thinnest", finish="none", name="X")
    ms2, _ = scene_with([dt, lt, d2], d2.id)
    assert _blob(_render(ms2, _PLAN, 400, 400)) == 0            # explicit None overrides it
    rep = lt.repeat
    rep.pop("ends")
    lt.set_repeat(rep)                                           # edit the default away
    ms.block_registry.invalidate(lt.id)
    assert _blob(_render(ms, _PLAN, 400, 400)) == 0             # By Linetype lines follow


def test_end_definition_edit_reaches_the_next_paint(qapp):
    dt = dot(radius=0.5)                                         # r 5 px on the plan
    d = _line_block(finish=dt.id, weight="Thinnest")
    ms, _ = scene_with([dt, d], d.id)
    small = _blob(_render(ms, _PLAN, 400, 400))
    c = CircleItem(QPointF(0.0, 0.0), 1.2)
    c.fill_type = "solid"
    dt.set_primitives([c.to_dict()])                             # version bump
    ms.block_registry.invalidate(dt.id)
    big = _blob(_render(ms, _PLAN, 400, 400))
    assert small > 0 and big > 2 * small


def test_missing_end_in_a_block_badges_that_end_on_canvas(qapp):
    d = _line_block(finish="deadbeef", weight="Thinnest")
    ms, inst = scene_with([d], d.id)
    img = _render(ms, _PLAN, 400, 400)
    warn = QColor(theme.detect().warn)
    assert sum(1 for x in range(338, 363) for y in range(188, 213)
               if _close(QColor(img.pixel(x, y)), warn)) > 10
    assert "Missing end type: deadbeef" in inst.toolTip()


def test_block_bounds_cover_a_fixed_end(qapp):
    a = arrow()                                     # 3 mm x 1:100 -> 300 x 150 mm on the plan
    d = _line_block(finish=a.id, weight="Thinnest")
    _ms, inst = scene_with([a, d], d.id)
    assert inst.boundingRect().contains(QRectF(1200.0, -75.0, 300.0, 150.0))
    plain = _line_block(weight="Thinnest", name="P")
    _ms2, inst2 = scene_with([plain], plain.id)
    assert inst2.boundingRect().height() < 10.0       # end-less: today's 2 mm margin


def test_block_bounds_follow_end_edits_registration_and_linetype_defaults(qapp):
    """The bounds memo (``_end_pad_rows``) re-resolves whenever what it read
    changes. (1) / (2) keep the host's op list object (only the memo's
    registry dependency check sees them); (3) recompiles the host."""
    from tests.lt5_support import _poly
    big = QRectF(1500.0, -500.0, 500.0, 1000.0)   # 5 x 10 mm past the tip at 1:100
    # (1) an end definition edited in place
    a = arrow()
    d = _line_block(finish=a.id, weight="Thinnest")
    ms, inst = scene_with([a, d], d.id)
    ops = inst.render_ops()
    assert not inst.boundingRect().contains(big)
    a.set_primitives([_poly([(0.0, 0.0), (5.0, -5.0), (5.0, 5.0)])])   # forward-pointing
    ms.block_registry.invalidate(a.id)
    assert inst.boundingRect().contains(big)
    # (2) a missing end registered later (badge pad -> the arrow's reach)
    b = arrow(name="B")
    d2 = _line_block(finish=b.id, weight="Thinnest", name="D2")
    ms2, inst2 = scene_with([d2], d2.id)
    ops2 = inst2.render_ops()
    tip = QRectF(1200.0, -75.0, 300.0, 150.0)
    assert not inst2.boundingRect().contains(tip)
    ms2.register_block_definition(b)
    assert inst2.boundingRect().contains(tip)
    assert inst2.render_ops() is ops2              # same host ops: the dep check saw it
    # (3) a linetype default end edited away
    dt = dot(radius=4.0)                          # 400 mm reach at 1:100
    lt = make_linetype(length=9.0, dashes=((0.0, 6.0),))
    rep = lt.repeat
    rep["ends"] = {"finish": dt.id}
    lt.set_repeat(rep)
    d3 = _line_block(linetype=lt.id, weight="Thinnest", name="D3")
    ms3, inst3 = scene_with([dt, lt, d3], d3.id)
    ring = QRectF(1500.0, -350.0, 350.0, 700.0)
    assert inst3.boundingRect().contains(ring)
    rep = lt.repeat
    rep.pop("ends")
    lt.set_repeat(rep)
    ms3.block_registry.invalidate(lt.id)
    assert not inst3.boundingRect().contains(ring)
    assert inst.render_ops() is ops                # (1) never recompiled the host


def test_end_less_block_keeps_the_plain_fast_path(qapp, monkeypatch):
    d = sprinkler_def()                               # legacy: Continuous, By Linetype ends
    ms, inst = scene_with([d], d.id)
    plain, seen = [], []
    real = BlockInstance._paint_plain_ops

    def spy(self, *a, **k):
        plain.append(a[6] if len(a) > 6 else k.get("end_ops", frozenset()))
        return real(self, *a, **k)

    monkeypatch.setattr(BlockInstance, "_paint_plain_ops", spy)
    for name in ("_op_ends", "_draw_op_ends", "_trimmed_op_path", "_ends_pad"):
        monkeypatch.setattr(BlockInstance, name,
                            lambda *a, _n=name, **k: seen.append(_n))
    _render_model(ms)
    inst.boundingRect()
    assert plain and all(eo == frozenset() for eo in plain)
    assert seen == []


def test_e9_explode_keeps_ends_and_look(qapp):
    """R8 / E9: Explode (the real ``block_explode`` path, in the Block Editor
    scene it runs in -- the WM2 G8 setup) keeps each end record exactly,
    ``mirrored`` included, and the look pixel-identical."""
    from firepro3d.block_explode import explode_instances
    from tests.lt5_support import half_arrow
    from tests.test_wm2_nested_explode import _diff_pixels, _editor_scene
    h = half_arrow(length=60.0, h=30.0)       # asymmetric: a lost mirror shows
    start = {"end": "none", "visible": True}
    finish = {"end": h.id, "visible": True, "mirrored": True}
    ln = LineItem(QPointF(-300.0, 0.0), QPointF(300.0, 0.0))
    ln.style["weight"] = "Thinnest"
    ln.style["start"] = dict(start)
    ln.style["finish"] = dict(finish)
    d = BlockDefinition.new(name="X9", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    _w, ms = _editor_scene([h, d])
    # D39 state tint off: a lone exploded line's constraint tint differs from
    # its placement's with or without ends (an end-less probe shows the same
    # line-pixel diff) -- orthogonal to E9, so it must not mask the look.
    ms.constraint_ctl.enabled = False
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    before = _render_model(ms)
    # composition: the end really draws on the placement (else (b) is vacuous)
    assert _blob(before, cx=335, cy=200, r=20, band=1) > 100   # 30 x 15 px barb
    created = explode_instances(ms, [inst], flatten=False)
    (item,) = created
    assert isinstance(item, LineItem)
    assert item.style["start"] == {"end": "none", "visible": True}
    assert item.style["finish"] == {"end": h.id, "visible": True, "mirrored": True}
    assert _diff_pixels(before, _render_model(ms)) == 0


def test_op_ends_gate_is_only_ever_a_shortcut(qapp):
    """Block twin of ``test_item_ends_fast_path_is_only_ever_a_shortcut``:
    over slot x visible x mirrored x linetype, ``BlockInstance._op_ends`` on
    the COMPILED op returns NO_ENDS only where the real cascade (on the
    authored style) draws nothing, else exactly its answer; and every op
    that draws is reachable by the paint gate (an explicit-end op in
    ``_end_ref_ops`` or a linetype with a default end)."""
    from firepro3d.stroke_style import NO_ENDS, has_ends, resolve_ends, resolve_stroke
    a = arrow()
    plain_lt = make_linetype()
    lt = make_linetype(name="WithEnd")
    lt.set_repeat({**lt.repeat, "ends": {"start": a.id, "finish": a.id}})
    slots = [None]
    for end in ("by_linetype", "none", a.id, "deadbeef"):
        for vis in (True, False):
            for mir in (False, True):
                rec = {"end": end, "visible": vis}
                if mir:
                    rec["mirrored"] = True
                slots.append(rec)
    n_short = n_draw = 0
    for ref in ("continuous", plain_lt.id, lt.id):
        lines = []
        for r0 in slots:
            for r1 in slots:
                ln = LineItem(QPointF(0.0, 0.0), QPointF(10.0, 0.0))
                ln.style["weight"] = "Thinnest"
                ln.style["linetype"] = ref
                for k, r in (("start", r0), ("finish", r1)):
                    if r is not None:
                        ln.style[k] = dict(r)
                lines.append(ln)
        d = BlockDefinition.new(name=f"T{ref}", library="L", series="S",
                                primitives=[ln.to_dict() for ln in lines],
                                origin=(0.0, 0.0))
        ms, inst = scene_with([a, plain_lt, lt, d], d.id)
        reg = ms.block_registry
        ops = [op for op in inst.render_ops() if op.kind == "stroke"]
        assert len(ops) == len(lines)
        eo = inst._end_ref_ops(inst.render_ops())
        idx = [i for i, op in enumerate(inst.render_ops()) if op.kind == "stroke"]
        for i, op, ln in zip(idx, ops, lines):
            rs = resolve_stroke({"linetype": op.linetype,
                                 "weight": op.weight or "by_linetype"}, reg)
            truth = resolve_ends(ln.style, resolve_stroke(ln.style, reg).lt, reg)
            got = inst._op_ends(op, rs.lt, reg)
            if got is NO_ENDS:
                n_short += 1
                assert not has_ends(truth), (ref, ln.style["start"], ln.style["finish"])
            else:
                n_draw += 1
                assert got == truth, (ref, ln.style["start"], ln.style["finish"])
            if has_ends(truth):              # the paint gate reaches it
                assert i in eo or (rs.lt is not None
                                   and (rs.lt.start_end or rs.lt.finish_end)), (
                    ref, ln.style["start"], ln.style["finish"])
    assert n_short > 100 and n_draw > 100                # both branches exercised


def test_linetype_paint_and_bounds_stay_copy_free(qapp, monkeypatch):
    """I2: after warm-up, painting + bounding a linetyped placed block and a
    linetyped raw line never reads ``BlockDefinition.repeat`` (a deep copy);
    ``is_linetype`` agrees with ``bool(repeat)``."""
    from firepro3d.block_definition import BlockDefinition as BD
    from tests.test_lt5_render_raw import _add
    lt = make_linetype(length=9.0, dashes=((0.0, 6.0),))
    d = _line_block(linetype=lt.id, weight="Thinnest")
    ms, inst = scene_with([lt, d], d.id)
    ln = _add(ms, LineItem(QPointF(-1500.0, 500.0), QPointF(1500.0, 500.0)))
    ln.style["linetype"] = lt.id
    ln._sync_stroke_pen()
    plain = BlockDefinition.new(name="P", library="L", series="S",
                                primitives=[], origin=(0.0, 0.0))
    bad = make_linetype(name="Bad")
    bad._repeat = {"length": -1.0, "size": "drafting"}       # malformed, still a record
    for x in (lt, plain, bad):
        assert x.is_linetype == bool(x.repeat)
    assert (lt.is_linetype, plain.is_linetype, bad.is_linetype) == (True, False, True)
    _render(ms, _PLAN, 400, 400)                      # warm-up (cache misses read it)
    inst.boundingRect(), ln.boundingRect()
    reads = []
    real = BD.repeat
    monkeypatch.setattr(BD, "repeat", property(
        lambda self: (reads.append(self.id), real.fget(self))[1]))
    img = _render(ms, _PLAN, 400, 400)
    inst.boundingRect(), ln.boundingRect()
    lit = lambda y: sum(QColor(img.pixel(x, y)).lightness() > 128 for x in range(400))
    assert lit(200) > 50 and lit(250) > 50            # block + raw line really drew
    assert reads == []
