"""Live repaint-cost probe for underlay zoom/pan performance (spec §18).

Usage (from the repo root):
    ./venv/Scripts/python.exe tools/perf_probe_underlay.py "d:/path/to/project.FPD"
    ./venv/Scripts/python.exe tools/perf_probe_underlay.py    # synthetic dense underlay

Prints median repaint ms at zoom x0.5/x1/x2/x4/x8 with the freeze OFF
(vector path, today's cost) and ON (gesture path), plus a simulated
30-repaint zoom gesture total. Acceptance (2026-08-29 grill): gesture-path
frames <= 16 ms at every zoom on the reference file.

NOT a pytest test — timing asserts are banned from the suite; run this
manually and record the numbers in the commit/PR message.
"""
import os
import random
import sys
import time

# Script lives in tools/ — put the repo root on sys.path so `firepro3d` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication


def build_synthetic(scene):
    from firepro3d.underlay import Underlay
    record = Underlay(type="pdf", path="synthetic.pdf", colour="#8a8a8a")
    rng = random.Random(42)
    geoms = []
    for _ in range(20000):
        x, y = rng.uniform(0, 800), rng.uniform(0, 1000)
        pts = [[x, y]]
        for _ in range(3):
            x += rng.uniform(-15, 15); y += rng.uniform(-15, 15)
            pts.append([x, y])
        geoms.append({"kind": "path_points", "layer": "SYN", "width": 0.0,
                      "closed": False, "points": pts})
    group, _layers = scene._build_batched_underlay_group(geoms, record)
    scene._apply_underlay_display(group, record)
    scene.underlays.append((record, group))


def median_repaint_ms(view, n=8):
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        view.viewport().repaint()
        ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    return ts[len(ts) // 2]


def main():
    app = QApplication([])
    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View

    scene = Model_Space()
    if len(sys.argv) > 1:
        scene.load_from_file(sys.argv[1])
        print(f"loaded: {sys.argv[1]} ({len(scene.underlays)} underlays)")
    else:
        build_synthetic(scene)
        print("synthetic dense underlay (20k primitives)")

    view = Model_View(scene)
    view.resize(1600, 900)
    view.show()
    for _ in range(20):
        app.processEvents(); time.sleep(0.02)
    view.fit_to_screen()
    app.processEvents()
    base_t = view.transform()

    def set_zoom(m):
        view.setTransform(base_t)
        view.scale(m, m)
        app.processEvents()

    print(f"{'zoom':>6} | {'vector (today)':>15} | {'frozen (gesture)':>17}")
    for m in (0.5, 1.0, 2.0, 4.0, 8.0):
        set_zoom(m)
        scene._underlay_freeze.end()
        vec = median_repaint_ms(view)
        scene._underlay_freeze.begin(view)
        frz = median_repaint_ms(view)
        scene._underlay_freeze.end()
        flag = "  OK" if frz <= 16.0 else "  ** OVER 16ms **"
        print(f"x{m:<5} | {vec:>12.1f} ms | {frz:>14.1f} ms{flag}")

    # Simulated gesture: freeze at x1, 15 zoom-in + 15 zoom-out repaints
    set_zoom(1.0)
    scene._underlay_freeze.begin(view)
    t0 = time.perf_counter()
    for _ in range(15):
        view.scale(1.15, 1.15); view.viewport().repaint()
    for _ in range(15):
        view.scale(1 / 1.15, 1 / 1.15); view.viewport().repaint()
    total = (time.perf_counter() - t0) * 1000
    scene._underlay_freeze.end()
    print(f"gesture (30 repaints, frozen): {total:.0f} ms total, "
          f"{total / 30:.1f} ms/frame  (was ~3600 ms unfrozen on Sleeman)")

    scene._modified = False
    view.close()


if __name__ == "__main__":
    main()
