"""WM2 H8 perf -- placement overrides, both shapes, A/B vs base.
Run standalone: ./venv/Scripts/python.exe -m pytest tests/test_wm2_perf.py -m perf -s
A/B: run the As Authored cases at base 7f97f687 (copy this file into a base
worktree; the override cases skip there) and pass the medians as
WM2_BASE_SMALL / WM2_BASE_LARGE.

Bars (Phase-2 Q11): As Authored <= 1.05x base, Weight override <= 1.1x the
same scene As Authored, Linetype override report-only."""
import os
import random

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.test_mw_perf import _frames_ms, _view

pytestmark = pytest.mark.perf
_HAS_WM2 = "overrides" in Model_Space.place_block_instance.__code__.co_varnames
_SHAPES = [("small", 2000, 3), ("large", 20, 300)]


def _def(n_lines):
    prims = []
    for i in range(n_lines):
        ln = LineItem(QPointF(0, i * 10.0), QPointF(300, i * 10.0))
        ln.style["weight"] = ["Thinnest", "Thin", "Thickest"][i % 3]
        prims.append(ln.to_dict())
    return BlockDefinition.new(name=f"B{n_lines}", library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


def _scene(n_inst, n_lines, ov, extra=()):
    random.seed(11)
    sc = Model_Space()
    for e in extra:
        sc.register_block_definition(e)
    d = _def(n_lines)
    sc.register_block_definition(d)
    for _ in range(n_inst):
        kw = {"overrides": ov} if ov else {}
        sc.place_block_instance(d.id, (random.uniform(-5000, 5000),
                                       random.uniform(-5000, 5000)),
                                level=sc.active_level, **kw)
    assert len(sc._block_instances) == n_inst            # composition
    assert len(d.render_ops()) == n_lines
    if ov:
        from firepro3d.stroke_style import normalize_overrides
        inst = sc._block_instances[0]
        assert inst.overrides == normalize_overrides(ov)
        strokes = [op for op in inst.render_ops() if op.kind == "stroke"]
        assert len(strokes) == n_lines
        if "weight" in ov:
            assert {op.weight for op in strokes} == {ov["weight"]}
        if "linetype" in ov:
            assert {op.linetype for op in strokes} == {ov["linetype"]}
    return sc


def _bench(label, sc, env=None, bar=None, ref=None):
    ms = _frames_ms(_view(sc))
    base = float(os.environ[env]) if env and os.environ.get(env) else ref
    print(f"\nWM2 {label}: {ms:.2f} ms/frame"
          + (f" (ref {base:.2f}, ratio {ms / base:.2f}, bar {bar})" if base else ""))
    if base and bar:
        assert ms <= bar * base, (label, ms, base)
    return ms


@pytest.mark.parametrize("shape,n_inst,n_lines,env",
                         [("small", 2000, 3, "WM2_BASE_SMALL"),
                          ("large", 20, 300, "WM2_BASE_LARGE")])
def test_as_authored_vs_base(qapp, shape, n_inst, n_lines, env):
    _bench(f"{shape} as-authored", _scene(n_inst, n_lines, None), env, 1.05)


@pytest.mark.skipif(not _HAS_WM2, reason="base tree: no overrides")
@pytest.mark.parametrize("shape,n_inst,n_lines", _SHAPES)
def test_weight_override_vs_as_authored(qapp, shape, n_inst, n_lines):
    ref = _bench(f"{shape} as-authored(ref)", _scene(n_inst, n_lines, None))
    _bench(f"{shape} weight", _scene(n_inst, n_lines, {"weight": "Thick"}),
           bar=1.1, ref=ref)


@pytest.mark.skipif(not _HAS_WM2, reason="base tree: no overrides")
@pytest.mark.parametrize("shape,n_inst,n_lines", _SHAPES)
def test_linetype_override_report_only(qapp, shape, n_inst, n_lines):
    from tests.lt3_support import make_linetype
    lt = make_linetype()
    ref = _bench(f"{shape} as-authored(ref)", _scene(n_inst, n_lines, None))
    _bench(f"{shape} linetype", _scene(n_inst, n_lines, {"linetype": lt.id},
                                       extra=[lt]), ref=ref)
