"""LT5 bench (Q15) -- end types on 2,000 lines, pan / zoom paint.

REPORT-ONLY (the LTS / WM2 ruling: this host varies 2-4x run to run): it
prints the ratios and asserts only its own composition -- 2,000 lines, 400
of them really carrying Arrow (start) + Dot (finish) ends that really draw,
and the end-less scenes really on the LT5 fast path. Frames alternate
between the compared scenes (best of 15 zoom + 15 pan frames).

Ratios printed (Q15 targets):
  ends      = scene with 400 end-carrying lines / the same lines end-less   (<= 1.3x)
  end-less  = the end-less scene / "base"                                    (<= 1.1x)

"base" is IN-PROCESS: the same end-less scene with the LT5 hooks replaced
by constant no-end returns (Geometry2DMixin._item_ends / _ends_rect,
BlockInstance._end_ref_ops / _op_ends), frame by frame. It therefore
measures the LT5 gate checks themselves -- NOT incidental cost of the
refactored paint code around them. The true pre-LT5 base is cbe41a15: copy
this file into a base worktree and run it there (the LT5 cases skip; the
end-less absolute ms print) and pass those as LT5_BASE_RAW / LT5_BASE_BLOCK
here for an A/B line. "raw-wr" repeats the raw shape with a weight-relative
trimmed arrow -- its trims change with zoom (flagged perf risk).

Run standalone: ./venv/Scripts/python.exe -m pytest tests/test_lt5_perf.py -m perf -s
"""
import contextlib
import importlib.util
import os

import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.test_lts_perf import _frame, _paired, _zoomed

pytestmark = pytest.mark.perf
_HAS_LT5 = importlib.util.find_spec("firepro3d.end_render") is not None
_N, _EVERY = 2000, 5                       # 400 lines with ends


def _end_defs(ms, size="fixed"):
    from tests.lt5_support import arrow, dot
    a, d = arrow(size=size), dot()
    ms.register_block_definition(a)
    ms.register_block_definition(d)
    return a.id, d.id


def _raw(ends, size="fixed"):
    """Plan: 2,000 raw 400 mm lines (40 rows x 50), every 5th with ends."""
    ms = Model_Space()
    ids = _end_defs(ms, size) if ends else None
    lines = []
    for i in range(_N):
        r, c = divmod(i, 50)
        ln = LineItem(QPointF(c * 500.0, r * 300.0), QPointF(c * 500.0 + 400.0, r * 300.0))
        if ends and i % _EVERY == 0:
            from tests.lt5_support import set_ends
            set_ends(ln, start=ids[0], finish=ids[1])
        ms.addItem(ln)
        lines.append(ln)
    return ms, QRectF(-500.0, -500.0, 26000.0, 13000.0), lines


def _block(ends, size="fixed"):
    """Plan: 200 placements of a 10-line block, lines 0 and 5 with ends."""
    ms = Model_Space()
    ids = _end_defs(ms, size) if ends else None
    prims = []
    for k in range(10):
        ln = LineItem(QPointF(0.0, k * 30.0), QPointF(400.0, k * 30.0))
        if ends and k in (0, 5):
            from tests.lt5_support import set_ends
            set_ends(ln, start=ids[0], finish=ids[1])
        prims.append(ln.to_dict())
    bd = BlockDefinition.new(name="E10", library="L", series="S",
                             primitives=prims, origin=(0.0, 0.0))
    ms.register_block_definition(bd)
    for i in range(200):
        r, c = divmod(i, 20)
        ms.place_block_instance(bd.id, (c * 500.0, r * 400.0), level=ms.active_level)
    return ms, QRectF(-500.0, -500.0, 11000.0, 5000.0), None


_SHAPES = {"raw": _raw, "block": _block,
           "raw-wr": lambda ends: _raw(ends, size="weight_relative")}


def _crops(crop):
    return ([_zoomed(crop, 1.03 ** k) for k in range(1, 16)]
            + [crop.translated(crop.width() * 0.03 * k, 0) for k in range(1, 16)])


def _assert_composition(shape, with_e, without, crop, lines_e, lines_n):
    from firepro3d.stroke_style import NO_ENDS, has_ends
    if shape == "block":
        insts = with_e._block_instances
        assert len(insts) == 200
        assert all(i._end_ref_ops(i.render_ops()) == frozenset({0, 5}) for i in insts)
        assert sum(1 for op in insts[0].render_ops() if op.kind == "stroke") == 10
        plain = without._block_instances
        assert all(i._end_ref_ops(i.render_ops()) == frozenset() for i in plain)
    else:
        assert len(lines_e) == _N and len(lines_n) == _N
        assert sum(1 for ln in lines_e if has_ends(ln._item_ends())) == _N // _EVERY
        assert all(ln._item_ends() is NO_ENDS for ln in lines_n)   # fast path
    assert _frame(with_e, crop)[1] != _frame(without, crop)[1]     # the ends really draw


@contextlib.contextmanager
def _bypassed():
    """The LT5 hooks replaced by constant no-end returns (the in-process base)."""
    from firepro3d.block_instance import BlockInstance
    from firepro3d.geometry_2d import Geometry2DMixin
    from firepro3d.stroke_style import NO_ENDS
    hooks = {(Geometry2DMixin, "_item_ends"): lambda self, rs=None: NO_ENDS,
             (Geometry2DMixin, "_ends_rect"): lambda self, ends=None: None,
             (BlockInstance, "_end_ref_ops"): lambda self, ops: frozenset(),
             (BlockInstance, "_op_ends"): lambda self, op, lt, registry: NO_ENDS}
    saved = [(c, n, c.__dict__[n]) for c, n in hooks]
    for (c, n), f in hooks.items():
        setattr(c, n, f)
    try:
        yield
    finally:
        for c, n, f in saved:
            setattr(c, n, f)


@pytest.mark.skip(reason="ET1: Line weight retired (arrow(size=) / EndDef.size); rewritten in Task 8")
@pytest.mark.skipif(not _HAS_LT5, reason="base tree: no end_render")
@pytest.mark.parametrize("shape", ["raw", "block", "raw-wr"])
def test_ends_vs_end_less(qapp, shape):
    with_e, crop, lines_e = _SHAPES[shape](True)
    without, _, lines_n = _SHAPES[shape](False)
    _assert_composition("block" if shape == "block" else "raw",
                        with_e, without, crop, lines_e, lines_n)
    if shape != "block":                     # VC2: every drawn end, its size mode
        from firepro3d.end_render import FIXED, WEIGHT_RELATIVE, EndDef
        want = WEIGHT_RELATIVE if shape == "raw-wr" else FIXED
        arrows = [EndDef.from_block(ln._item_ends()[0].defn) for ln in lines_e
                  if ln._item_ends()[0].defn is not None]
        assert len(arrows) == _N // _EVERY
        assert {ed.size for ed in arrows} == {want}
    t_e, t_n = _paired(with_e, without, _crops(crop))
    print(f"\nLT5 {shape}: ends {t_e:.1f} / end-less {t_n:.1f} ms "
          f"({t_e / t_n:.2f}x, target 1.3x)")


@pytest.mark.skipif(not _HAS_LT5, reason="base tree: no end_render")
@pytest.mark.parametrize("shape", ["raw", "block"])
def test_end_less_vs_bypassed_base(qapp, shape):
    sc, crop, _ = _SHAPES[shape](False)
    with _bypassed():
        from firepro3d.stroke_style import NO_ENDS
        from firepro3d.geometry_2d import Geometry2DMixin
        assert Geometry2DMixin._item_ends(None) is NO_ENDS        # the bypass is live
    live, base = [], []
    for c in _crops(crop):
        live.append(_frame(sc, c)[0])
        with _bypassed():
            base.append(_frame(sc, c)[0])
    print(f"\nLT5 {shape}: end-less {min(live):.1f} / bypassed base {min(base):.1f} ms "
          f"({min(live) / min(base):.2f}x, target 1.1x; in-process base, see module doc)")


@pytest.mark.parametrize("shape", ["raw", "block"])
def test_end_less_absolute(qapp, shape):
    """Runs at base too: its ms is the A/B reference (LT5_BASE_<SHAPE>)."""
    sc, crop, _ = _SHAPES[shape](False)
    ms = min(_frame(sc, c)[0] for c in _crops(crop))
    env = os.environ.get(f"LT5_BASE_{shape.upper()}")
    print(f"\nLT5 {shape} end-less: {ms:.1f} ms/frame"
          + (f" (base {float(env):.1f}, ratio {ms / float(env):.2f}, target 1.1x)"
             if env else ""))
