"""D18 perf parity guard (maint "nothing moved").

Scripted grip / D35 body / incremental resize / hold-last-good / Esc drag
sequences on the rect-heavy component and on a mixed-primitive sketch must
reproduce the geometry recorded at the pre-perf base commit (8128f6a) within
TOL (the tighter of the adapters' write tolerances -- below it the app itself
treats a value as unmoved).

Regenerate ONLY for a ratified behaviour change:
    FP3D_REGEN_D18_GOLDEN=1 python -m pytest tests/test_d18_parity.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import (ArcItem, CircleItem, LineItem, PolylineItem,
                                   RectangleItem, RegularPolygonItem)
from firepro3d.model_space import Model_Space
from firepro3d.selection_manipulator import bake_translate
from firepro3d.sketch_adapters import adapter_for

GOLDEN = Path(__file__).parent / "data" / "d18_parity_golden.json"
TOL = 1e-8


def _add(sc, it, attr):
    sc.addItem(it)
    getattr(sc, attr).append(it)
    return it


def _state(named) -> dict:
    return {k: [float(v) for v in adapter_for(it).read(it)] for k, it in named.items()}


def _rect_heavy():
    sc = Model_Space(scene_role="block_editor")
    n, recs = {}, []
    for i in range(100):
        n[f"r{i}"] = _add(sc, RectangleItem(QPointF(i * 300, 0), QPointF(i * 300 + 200, 100)),
                          "_draw_rects")
        n[f"l{i}"] = _add(sc, LineItem(QPointF(i * 300 - 50, 0), QPointF(i * 300 - 80, 30)),
                          "_draw_lines")
    for i in range(100):
        r, ln = n[f"r{i}"]._uid, n[f"l{i}"]._uid
        recs.append({"id": f"b{i}", "type": "horizontal",
                     "refs": [{"uid": r, "h": "br"}, {"uid": ln, "h": "p1"}]})
        recs.append({"id": f"t{i}", "type": "horizontal",
                     "refs": [{"uid": r, "h": "tl"}, {"uid": ln, "h": "p2"}]})
        if i < 99:
            recs.append({"id": f"c{i}", "type": "horizontal",
                         "refs": [{"uid": r, "h": "tr"}, {"uid": n[f"r{i + 1}"]._uid, "h": "tl"}]})
    sc.constraint_ctl.load(recs)
    assert len(sc.constraint_ctl.active()) == 299
    return sc, n


def _seq_rect_heavy() -> dict:
    sc, n = _rect_heavy()
    ctl, it, out = sc.constraint_ctl, n["r50"], {}
    try:
        out["load"] = _state(n)
        ctl.begin_drag(it)
        for _ in range(21):
            r = it.rect()
            it.setRect(r.x(), r.y(), r.width() + 0.3, r.height() + 0.2)
            ctl.drag(it, 4)
        ctl.end_drag()
        out["grip"] = _state(n)
        ctl.begin_drag([it])
        for k in range(1, 22):
            d = 0.5 * k
            assert ctl.drag_frame([it], lambda: bake_translate(it, d, d), reset=True)
        ctl.end_drag()
        out["body"] = _state(n)
    finally:
        sc.cleanup()
    return out


def _mixed():
    sc = Model_Space(scene_role="block_editor")
    n = {"arc": _add(sc, ArcItem(QPointF(0, 0), 100.0, 10.0, 50.0), "_draw_arcs"),
         "poly": _add(sc, RegularPolygonItem(QPointF(400, 0), radius_mm=80.0), "_draw_polygons"),
         "rect": _add(sc, RectangleItem(QPointF(600, 0), QPointF(800, 100)), "_draw_rects"),
         "circ": _add(sc, CircleItem(QPointF(0, 300), 50.0), "_draw_circles"),
         "l1": _add(sc, LineItem(QPointF(150, 40), QPointF(300, 90)), "_draw_lines"),
         "l2": _add(sc, LineItem(QPointF(500, 60), QPointF(560, 120)), "_draw_lines")}
    pl = PolylineItem(QPointF(0, -200))
    for q in (QPointF(100, -170), QPointF(200, -260)):
        pl.append_point(q)
    n["pl"] = _add(sc, pl, "_polylines")

    def ref(k, h):
        return {"uid": n[k]._uid, "h": h}
    recs = [
        {"id": "a", "type": "horizontal", "refs": [ref("arc", "start"), ref("l1", "p1")]},
        {"id": "b", "type": "vertical", "refs": [ref("poly", "v0"), ref("l1", "p2")]},
        {"id": "c", "type": "horizontal", "refs": [ref("l1", "p2"), ref("l2", "p1")]},
        {"id": "d", "type": "horizontal", "refs": [ref("rect", "tl"), ref("l2", "p2")]},
        {"id": "e", "type": "horizontal", "refs": [ref("rect", "bl"), {"ref": "origin"}]},
        {"id": "f", "type": "horizontal", "refs": [ref("circ", "center"), ref("l2", "p2")]},
        {"id": "g", "type": "vertical", "refs": [ref("pl", "s0")]},
        {"id": "h", "type": "vertical", "refs": [ref("arc", "end"), ref("pl", "v2")]},
    ]
    sc.constraint_ctl.load(recs)
    assert not sc.constraint_ctl.red
    return sc, n


def _seq_mixed() -> dict:
    sc, n = _mixed()
    ctl, r, out = sc.constraint_ctl, n["rect"], {}
    try:
        out["load"] = _state(n)
        ctl.begin_drag(r)                                   # grip: tr corner
        for _ in range(15):
            q = r.rect()
            r.setRect(q.x(), q.y() - 0.4, q.width() + 0.7, q.height() + 0.4)
            ctl.drag(r, 2)
        ctl.end_drag()
        out["grip"] = _state(n)
        sel = [r, n["circ"]]                                # D35 body, reset frames
        ctl.begin_drag(sel)
        for k in range(1, 16):
            d = 0.8 * k
            assert ctl.drag_frame(sel, lambda: [bake_translate(i, d, -0.5 * d) for i in sel],
                                  reset=True)
        ctl.end_drag()
        out["body"] = _state(n)

        def grow():
            q = r.rect()
            r.setRect(q.x(), q.y(), q.width() * 1.01, q.height())
        ctl.begin_drag([r])                                 # incremental (resize) frames
        for _ in range(10):
            assert ctl.drag_frame([r], grow, reset=False)
        out["resize"] = _state(n)
        grow()                                              # applied, never solved ...
        ctl.hold_last_good()                                # ... D10 puts it back
        out["hold"] = _state(n)
        ctl.end_drag()
        ln = n["l1"]                                        # Esc restores the session start
        ctl.begin_drag(ln)
        for _ in range(5):
            ln._pt2 = QPointF(ln._pt2.x() + 3.0, ln._pt2.y() + 2.0)
            ln.setLine(ln._pt1.x(), ln._pt1.y(), ln._pt2.x(), ln._pt2.y())
            ctl.drag(ln, 2)
        ctl.cancel_drag()
        out["cancel"] = _state(n)
    finally:
        sc.cleanup()
    return out


def _worst(a: dict, b: dict) -> float:
    w = 0.0
    for name, vals in a.items():
        g = b[name]
        assert len(g) == len(vals), name
        w = max(w, max(abs(x - y) for x, y in zip(g, vals)))
    return w


def test_d18_drag_sequences_match_the_pre_perf_golden(qapp):
    got = {"rect_heavy": _seq_rect_heavy(), "mixed": _seq_mixed()}
    if os.environ.get("FP3D_REGEN_D18_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1), encoding="utf-8")
        pytest.skip("golden regenerated")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # VC2: the sequences really moved geometry -- the body drag ripples
    # through most of the chain (the grip growth keeps tl, so only r50/l50)
    rh = want["rect_heavy"]
    moved = [k for k in rh["load"] if _worst({k: rh["load"][k]}, {k: rh["body"][k]}) > 1e-3]
    assert len(moved) >= 100
    assert _worst({"l50": rh["load"]["l50"]}, {"l50": rh["grip"]["l50"]}) > 1.0
    assert _worst(want["mixed"]["hold"], want["mixed"]["resize"]) <= TOL      # D10 hold
    assert want.keys() == got.keys()
    worst = 0.0
    for sk, phases in want.items():
        assert phases.keys() == got[sk].keys(), sk
        for ph, st in phases.items():
            worst = max(worst, _worst(st, got[sk][ph]))
    assert worst <= TOL, f"geometry drifted {worst:.3e} from the pre-perf golden"
