"""D8 perf bench -- stroke corner joins: pan / zoom / single-drag frame time.

Run standalone, one process at a time:
    ./venv/Scripts/python.exe -m pytest tests/test_stroke_joins_perf.py -m perf -s
A/B: copy this file into a worktree at the branch base (it has no
``stroke_joints``; the file runs unchanged there) and run it first; pass that
run's printed medians as SJ_BASE_MS_PAN / SJ_BASE_MS_ZOOM / SJ_BASE_MS_DRAG
to the HEAD run. With no env var a shape reports only; with it, HEAD / base
must be <= 1.25 (design D8, bar ratified 2026-11-03 at the MW-13 precedent).

Scene: 2000 loose LineItems in a 40 x 50 grid, laid out as 1000 L-shaped
pairs (a horizontal line whose finish meets a vertical line's start at a
90-degree corner, same weight, same colour) -> 1000 joints at HEAD.
Raw per-frame lines are appended to SJ_RAW_DIR (default
D:/Custom Code/FPD/run-suite -- tests/_perf is not gitignored) as
stroke_joins_<label>.txt, label = SJ_LABEL or base/head by feature probe.
"""
import os
import statistics
import time

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View

pytestmark = pytest.mark.perf
_FRAMES = 30
_COLS, _ROWS = 40, 50               # grid cells; two cells = one L pair
_RAW_DIR = os.environ.get("SJ_RAW_DIR", "D:/Custom Code/FPD/run-suite")


def _label(sc):
    return os.environ.get("SJ_LABEL") or (
        "head" if hasattr(sc, "stroke_joints") else "base")


def _paint_ms(v):
    t0 = time.perf_counter()
    v.viewport().repaint()
    QApplication.processEvents()
    return (time.perf_counter() - t0) * 1000.0


def _build_scene():
    sc = Model_Space()
    lines = []
    for r in range(_ROWS):
        for c in range(0, _COLS, 2):
            x, y = (c // 2) * 1400.0, r * 700.0
            corner = QPointF(x + 400, y)
            a = LineItem(QPointF(x, y), corner)                       # horizontal
            b = LineItem(QPointF(corner), QPointF(x + 400, y + 400))  # vertical
            for ln in (a, b):
                ln.style["weight"] = "Heavy"
                sc.addItem(ln)
                sc._draw_lines.append(ln)
                lines.append(ln)
    return sc, lines


def _joint_pairs(sc, lines):
    """Count joint pairs through the index's public API: every registered
    end that has a partner, halved (each pair is seen from both ends)."""
    ix = sc.stroke_joints
    paired = 0
    for ln in lines:
        for e in ix.ends_of(ln):
            if ix.partner(e) is not None:
                paired += 1
    return paired // 2


def _view(sc):
    v = Model_View(sc)
    v.resize(1400, 900)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.fitInView(sc.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
    return v


def _record(sc, shape, frames):
    try:
        os.makedirs(_RAW_DIR, exist_ok=True)
        with open(os.path.join(_RAW_DIR, f"stroke_joins_{_label(sc)}.txt"),
                  "a", encoding="utf-8") as fh:
            fh.write(f"# {time.strftime('%H:%M:%S')} {shape}\n")
            for k, ms in enumerate(frames):
                fh.write(f"{shape} {k} {ms:.3f}\n")
    except OSError as exc:                        # raw log is best-effort
        print(f"SJ raw log skipped: {exc}")


def _check(sc, shape, env, frames):
    ms = statistics.median(frames)
    _record(sc, shape, frames)
    base = os.environ.get(env)
    print(f"\nSJ {_label(sc)} {shape}: median {ms:.2f} ms/frame"
          + (f" (base {float(base):.2f}, ratio {ms / float(base):.3f}, bar 1.25)"
             if base else " (no base given: report only)"))
    if base:
        assert ms <= 1.25 * float(base), (shape, ms, base)


@pytest.fixture
def scene_view(qapp):
    sc, lines = _build_scene()
    assert len(sc._draw_lines) == 2000 and len(lines) == 2000        # composition
    if hasattr(sc, "stroke_joints"):                                  # HEAD only
        assert _joint_pairs(sc, lines) == 1000
    v = _view(sc)
    _paint_ms(v)                                                      # warm-up
    yield sc, lines, v
    v.close()
    sc.cleanup()


def test_sj_pan(scene_view):
    sc, _lines, v = scene_view
    v.scale(2.0, 2.0)
    bar = v.horizontalScrollBar()
    assert bar.maximum() > bar.minimum() + 200       # pan has room to move
    mid = (bar.minimum() + bar.maximum()) // 2
    frames = []
    for k in range(_FRAMES):
        bar.setValue(mid + (60 if k % 2 else -60))
        frames.append(_paint_ms(v))
    _check(sc, "pan", "SJ_BASE_MS_PAN", frames)


def test_sj_zoom(scene_view):
    sc, _lines, v = scene_view
    frames = []
    for k in range(_FRAMES):
        f = 1.03 if k % 2 else 1 / 1.03
        v.scale(f, f)
        frames.append(_paint_ms(v))
    _check(sc, "zoom", "SJ_BASE_MS_ZOOM", frames)


def test_sj_single_drag(scene_view):
    """Drag one jointed line's finish grip 20+ times, alternating between the
    corner (keeps the joint) and 300 mm off it (breaks it): exercises the
    register / unregister / neighbour-repaint path each frame."""
    sc, lines, v = scene_view
    ln = lines[(len(lines) // 2) // 2 * 2]           # a horizontal of a pair
    corner = QPointF(ln.line().p2())
    away = QPointF(corner.x() + 300.0, corner.y())
    hot = hasattr(sc, "stroke_joints")
    frames = []
    for k in range(_FRAMES):
        broken = bool(k % 2)
        t0 = time.perf_counter()
        ln.apply_grip(2, away if broken else corner)
        QApplication.processEvents()
        v.viewport().repaint()
        QApplication.processEvents()
        frames.append((time.perf_counter() - t0) * 1000.0)
        if hot:                                       # the path really runs
            assert _joint_pairs(sc, lines) == (999 if broken else 1000)
    _check(sc, "drag", "SJ_BASE_MS_DRAG", frames)
