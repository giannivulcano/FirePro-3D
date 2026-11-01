"""SB4a G8 -- labelled pipes stay responsive: "no slower than today" (bar ratified by the
user 2026-11-01, measured at base f20268e1). Full-view headless render, best of 5:
(a) 2,000 short 1,000 mm pipes, unsolved (2-line labels): <= 0.80 ms per labelled pipe
    (<= 1600 ms); (b) 400 long 10,000 mm pipes, solved (4-line labels): <= 0.30 ms per
    labelled pipe (<= 120 ms); (c) zoomed to 20 of the (b) pipes: <= 25 ms.
Runs under -m perf only, interleaved base / HEAD (suite runner PerfMarker): the same file
runs on both trees, branching on hasattr(bound_label, "TagBlockHost"); each run appends raw
lines "<shape>,<pipes>,<ms>,<tree>" to the file named by SB4A_BENCH_OUT. HEAD draws the label
through an explicitly registered Pipe label block (Diameter, Length, Flow, FrictionLoss; Flow
and FrictionLoss hide_empty) mapped as the project default -- the shipped System PipeLabel
does not resolve in a headless Model_Space. SB4A_BENCH_SMOKE=1 shrinks the scenes and skips
the bars (sanity run only)."""
import os
import time

import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

import firepro3d
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.hydraulic_solver import HydraulicResult
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space

SHORT_PER_PIPE_MS = 0.80       # (a) ratified bar, ms per labelled pipe
LONG_PER_PIPE_MS = 0.30        # (b) ratified bar, ms per labelled pipe
ZOOM_MS = 25.0                 # (c) ratified bar, 20 pipes in view
PX_W, PX_H = 1200, 900
SMOKE = bool(os.environ.get("SB4A_BENCH_SMOKE"))
N_SHORT, N_LONG = (40, 40) if SMOKE else (2000, 400)
ROW_MM = 2000.0


def _is_head(ms):
    # SB3 already shipped Model_Space.annotation_defaults at base f20268e1;
    # TagBlockHost is SB4a's (D4), so it marks the HEAD tree.
    from firepro3d import bound_label
    return hasattr(bound_label, "TagBlockHost")


def _register_label(ms):
    prims, keys = [], set()
    for text, y, hide in (("@[Diameter]", -4.0, False), ("@[Length]", 1.0, False),
                          ("@[Flow]", 6.0, True), ("@[FrictionLoss]", 11.0, True)):
        rec = {"type": "text", "text": text, "x": -10.0, "y": y, "height_mm": 3.0,
               "wrap_width_mm": 20.0, "box_height_mm": 3.0, "align": "C", "valign": "M"}
        if hide:
            rec["hide_empty"] = True
        prims.append(rec)
        keys.add(text[2:-1])
    d = BlockDefinition.new(name="BenchPipeLabel", library="", series="",
                            origin=(0.0, 0.0), primitives=prims)
    d.scale_mode = "annotative"
    d.host_category = "Pipe"
    d.attributes = [normalise_attr({"key": k, "source": "host", "host_key": k})
                    for k in sorted(keys)]
    ms.register_block_definition(d)
    ms.annotation_defaults["Pipe"] = d.id


def _fake_result(pipes):
    r = HydraulicResult.__new__(HydraulicResult)
    r.pipe_flows = {p: 50.0 + i * 0.1 for i, p in enumerate(pipes)}
    r.pipe_friction_loss = {p: 1.0 + i * 0.001 for i, p in enumerate(pipes)}
    r.pipe_velocity = {p: 1.0 for p in pipes}
    nodes = [n for p in pipes for n in (p.node1, p.node2)]
    r.node_numbers = {n: i + 1 for i, n in enumerate(nodes)}
    r.node_labels = {n: str(i + 1) for i, n in enumerate(nodes)}
    r.node_pressures = {n: 10.0 for n in nodes}
    r.node_parent_pipe = {}
    r.required_node_pressures, r.messages = {}, []
    return r


def _scene(n, length, cols, solved):
    ms = Model_Space()
    ms._level_manager = LevelManager()
    if _is_head(ms):
        _register_label(ms)
    gap = length * 0.5
    pipes = []
    for i in range(n):
        x0 = (i % cols) * (length + gap)
        y0 = (i // cols) * ROW_MM
        pipes.append(ms.add_pipe(ms.add_node(x0, y0), ms.add_node(x0 + length, y0)))
    if solved:
        ms.hydraulic_result = _fake_result(pipes)
    for p in pipes:
        p.update_label()
    return ms, pipes, gap


def _composition(ms, pipes, expect_lines):
    assert len(pipes) == len([i for i in ms.items() if type(i).__name__ == "Pipe"])
    assert all(p._properties["Show Label"]["value"] == "True" and not p._is_vertical()
               and p.label.isVisible() and p.label.scene() is ms for p in pipes)
    if _is_head(ms):
        assert type(pipes[0].label).__name__ == "BoundLabelItem"
        assert ms.annotation_block("Pipe").name == "BenchPipeLabel"
        assert all(p.label.paints() for p in pipes)
    else:
        txt = pipes[0].label.toPlainText()
        assert len([l for l in txt.split("\n") if l.strip()]) == expect_lines, txt


def _render_ms(ms, rect, reps=5):
    img = QImage(PX_W, PX_H, QImage.Format.Format_RGB32)
    best = None
    for _ in range(reps):
        img.fill(0xFF101010)
        p = QPainter(img)
        t0 = time.perf_counter()
        ms.render(p, QRectF(0, 0, PX_W, PX_H), rect, Qt.AspectRatioMode.KeepAspectRatio)
        dt = (time.perf_counter() - t0) * 1000.0
        p.end()
        best = dt if best is None else min(best, dt)
    return best


def _record(shape, n, ms_best):
    out = os.environ.get("SB4A_BENCH_OUT")
    if out:
        tree = os.path.dirname(os.path.dirname(os.path.abspath(firepro3d.__file__)))
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{shape},{n},{ms_best:.3f},{tree}\n")


def _full_rect(n, length, cols, gap):
    rows = (n + cols - 1) // cols
    return QRectF(-500, -1000, cols * (length + gap), rows * ROW_MM + 1000)


@pytest.mark.perf
def test_g8_short_pipes_full_view_bar(qapp):
    cols, length = 50, 1000.0
    ms, pipes, gap = _scene(N_SHORT, length, cols, solved=False)
    _composition(ms, pipes, 2)
    rect = _full_rect(N_SHORT, length, cols, gap)
    _render_ms(ms, rect, reps=1)                       # warm the caches
    best = _render_ms(ms, rect)
    _record("short", N_SHORT, best)
    if not SMOKE:
        bar = SHORT_PER_PIPE_MS * N_SHORT
        assert best <= bar, f"{best:.1f} ms for {N_SHORT} short pipes (bar {bar:.0f})"


@pytest.mark.perf
def test_g8_long_pipes_full_view_bar(qapp):
    cols, length = 20, 10000.0
    ms, pipes, gap = _scene(N_LONG, length, cols, solved=True)
    _composition(ms, pipes, 4)
    rect = _full_rect(N_LONG, length, cols, gap)
    _render_ms(ms, rect, reps=1)
    best = _render_ms(ms, rect)
    _record("long", N_LONG, best)
    if not SMOKE:
        bar = LONG_PER_PIPE_MS * N_LONG
        assert best <= bar, f"{best:.1f} ms for {N_LONG} long pipes (bar {bar:.0f})"


@pytest.mark.perf
def test_g8_zoomed_twenty_pipes_bar(qapp):
    cols, length = 20, 10000.0
    ms, pipes, gap = _scene(N_LONG, length, cols, solved=True)
    _composition(ms, pipes, 4)
    # 5 columns x 4 rows = 20 pipes
    rect = QRectF(5 * (length + gap) - 500, 4 * ROW_MM - 1000, 5 * (length + gap), 4 * ROW_MM)
    inview = [p for p in pipes if rect.contains(p.scenePos() + p.line().p1())
              and rect.contains(p.line().p2())]
    if not SMOKE:
        assert len(inview) == 20
    _render_ms(ms, rect, reps=1)
    best = _render_ms(ms, rect)
    _record("zoom", len(inview), best)
    if not SMOKE:
        assert best <= ZOOM_MS, f"{best:.1f} ms zoomed to 20 pipes (bar {ZOOM_MS:.0f})"
