"""SB3 G6 / AC6 (Q7) -- labelled rooms stay responsive: <= 0.25 ms per labelled room on a
full-view headless render at 200 and 1000 rooms (<= 50 / 250 ms), <= 25 ms zoomed to 9
rooms. Runs under -m perf only, interleaved base / HEAD (plan Task 14); each run appends
raw lines "<shape>,<rooms>,<ms>,<tree>" to the file named by SB3_BENCH_OUT."""
import os
import time

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

import firepro3d
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.room import Room

W, H = 6000.0, 4000.0          # room size, mm
COLS = 40
PER_ROOM_MS = 0.25             # Q7 bar
ZOOM_MS = 25.0                 # Q7 bar, 9 rooms in view
PX_W, PX_H = 1200, 900


def _scene(n):
    ms = Model_Space()
    ms._level_manager = LevelManager()
    if hasattr(ms, "annotation_defaults"):          # HEAD: the block tag; base: the HTML label
        d = BlockDefinition.new(name="BenchTag", library="L", series="S", origin=(0.0, 0.0),
                                primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                             "y": 0.0, "height_mm": 3.0}])
        d.scale_mode = "annotative"
        d.host_category = "Room"
        d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
        ms.register_block_definition(d)
        ms.annotation_defaults["Room"] = d.id
    for i in range(n):
        x0, y0 = (i % COLS) * W, (i // COLS) * H
        r = Room(boundary=[QPointF(x0, y0), QPointF(x0 + W, y0),
                           QPointF(x0 + W, y0 + H), QPointF(x0, y0 + H)])
        r.name = f"R{i + 1}"
        r.level = "Level 1"
        r._scale_manager_ref = ms.scale_manager
        r._update_label()
        ms.addItem(r)
        ms._rooms.append(r)
    return ms


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
    out = os.environ.get("SB3_BENCH_OUT")
    if out:
        tree = os.path.dirname(os.path.dirname(os.path.abspath(firepro3d.__file__)))
        with open(out, "a", encoding="ascii") as fh:
            fh.write(f"{shape},{n},{ms_best:.3f},{tree}\n")


def _composition(ms, n):
    assert len(ms._rooms) == n and all(r._show_label and r.name for r in ms._rooms)
    if hasattr(ms, "annotation_defaults"):
        d = ms.annotation_block("Room")
        assert d is not None and d.name == "BenchTag"
        assert all(r._tag.paints() for r in ms._rooms)


@pytest.mark.perf
@pytest.mark.parametrize("n", [200, 1000])
def test_g6_full_view_per_room_bar(qapp, n):
    ms = _scene(n)
    _composition(ms, n)
    rows = (n + COLS - 1) // COLS
    full = QRectF(0, 0, COLS * W, rows * H)
    _render_ms(ms, full, reps=1)                       # warm the caches
    best = _render_ms(ms, full)
    _record("full", n, best)
    assert best <= PER_ROOM_MS * n, f"{best:.1f} ms for {n} rooms (bar {PER_ROOM_MS * n:.0f})"


@pytest.mark.perf
def test_g6_zoomed_nine_rooms_bar(qapp):
    ms = _scene(1000)
    _composition(ms, 1000)
    nine = QRectF(10 * W, 10 * H, 3 * W, 3 * H)        # columns 10..12 x rows 10..12 = 9 rooms
    _render_ms(ms, nine, reps=1)
    best = _render_ms(ms, nine)
    _record("zoom9", 1000, best)
    assert best <= ZOOM_MS, f"{best:.1f} ms zoomed to 9 rooms (bar {ZOOM_MS:.0f})"
