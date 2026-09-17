"""R4 reference-graphic render/interaction perf spike.

Governing spec: ``docs/specs/reference-graphic-model.md`` §R4 + Performance.
Answers the BLOCKING prerequisite: does the target unified model (native
primitives, batched render, snap over an index) hold zoom/pan/SNAP/ALIGN
parity with today's hand-batched underlay path, on a real large DXF?

WHY the interaction loop (not raw repaint): the model scene runs
``NoIndex`` (``model_space.py`` — cosmetic-pen items are culled wrong by the
BSP index), so ``snap.find`` -> ``scene.items(search_rect)`` degrades to an
O(n) linear scan over EVERY scene item. The representation's scene-item count
is therefore what dominates interactivity when SNAP/ALIGN are live. This probe
drives the REAL hot path: ``scene._snap_engine.find(cursor, scene, xf,
align_paths=rays)`` then a viewport repaint, swept across the viewport at each
zoom and during a pan.

Three representations of the SAME extracted geometry:

  (1) baseline    — ``_build_batched_underlay_group`` (one cosmetic path item
                    per layer) + ``UnderlaySnapIndex`` at ``data(4)``. Today.
  (2) native-ind  — ``geom_dicts_to_primitives``; EACH primitive added as its
                    own scene item. Snap hits them via the O(n) scene scan.
                    The known-loser the spec predicts; measured to prove it.
  (3) native-btch — native primitives built + HELD (the target data model,
                    memory/build cost) + batched cosmetic paths for render +
                    ``UnderlaySnapIndex`` for snap. The R4 target (Z).

Modelling note for (3): render paths are batched from the same extracted geoms
(identical polyline content to the held PolylineItems), so render+snap cost is
apples-to-apples with (1); the MEASURED extra cost of (3) is the primitive
build + hold (time + RSS). Caveat recorded in the spec: an import that
*preserves curves* (native arcs/splines) would add curve-tessellation cost at
batch time — out of scope for this Go/No-Go bench, which runs on the flattened
underlay-extraction geoms (the real Sleeman density).

Run each rep in its OWN process so a 161 MB dataset's memory can't skew a
later rep:

    ./venv/Scripts/python.exe tools/perf_probe_reference_render.py <dxf> --scan
    ./venv/Scripts/python.exe tools/perf_probe_reference_render.py <dxf> --rep 1
    ./venv/Scripts/python.exe tools/perf_probe_reference_render.py <dxf> --rep 2
    ./venv/Scripts/python.exe tools/perf_probe_reference_render.py <dxf> --rep 3

Options: ``--cap N`` limits the geom count fed to a rep (logged truncation, no
silent caps); ``--sanitize`` forces the (risky, see project memory) DXF
sanitize pass instead of the default ``skip_sanitize=True``.

NOT a pytest test — timing asserts are banned from the suite. Run manually and
record the numbers in the spec + PR message.
"""
import argparse
import ctypes
import os
import sys
import time
from collections import Counter

# Script lives in tools/ — put the repo root on sys.path so `firepro3d` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # Windows consoles default to cp1252 — avoid encode crashes on any glyph.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication


# ── memory ────────────────────────────────────────────────────────────────
def peak_rss_mb() -> float:
    """Peak working set (MB) via the Win32 PSAPI — no psutil dependency.

    Counts C++ QGraphicsItem allocations (the whole point of rep 2/3), which
    tracemalloc would miss. Returns 0.0 off Windows / on any failure.
    """
    try:
        import psutil  # type: ignore
        return psutil.Process().memory_info().peak_wset / (1024 * 1024)
    except Exception:
        pass
    try:
        class _PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32),
                        ("PageFaultCount", ctypes.c_uint32),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p  # else -1 truncates to 32-bit
        h = k32.GetCurrentProcess()
        # Prefer the modern kernel32 forwarder; fall back to psapi.dll.
        fn = getattr(k32, "K32GetProcessMemoryInfo", None)
        if fn is None:
            fn = ctypes.windll.psapi.GetProcessMemoryInfo
        fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        fn.restype = ctypes.c_int
        if fn(h, ctypes.byref(pmc), pmc.cb):
            return pmc.PeakWorkingSetSize / (1024 * 1024)
    except Exception as e:
        print(f"  (rss probe failed: {e!r})")
    return 0.0


# ── extraction ──────────────────────────────────────────────────────────────
def _cache_path(dxf_path: str) -> str:
    import hashlib
    import tempfile
    st = os.stat(dxf_path)
    key = hashlib.md5(
        f"{os.path.abspath(dxf_path)}|{st.st_size}|{st.st_mtime}".encode()
    ).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), f"fp3d_bench_{key}.pkl")


def extract_geoms(dxf_path: str, force_sanitize: bool, use_cache: bool = True):
    import pickle
    cp = _cache_path(dxf_path)
    if use_cache and os.path.exists(cp):
        t = time.perf_counter()
        with open(cp, "rb") as f:
            geoms = pickle.load(f)
        print(f"  (geoms loaded from cache {cp})")
        return geoms, time.perf_counter() - t
    from firepro3d.dxf_import_worker import DxfImportWorker
    t = time.perf_counter()
    if force_sanitize:
        geoms = DxfImportWorker.extract_file_sync(dxf_path, skip_sanitize=False)
    else:
        try:
            geoms = DxfImportWorker.extract_file_sync(dxf_path, skip_sanitize=True)
        except Exception as e:
            print(f"  skip_sanitize=True failed ({e!r}); retrying with sanitize")
            geoms = DxfImportWorker.extract_file_sync(dxf_path, skip_sanitize=False)
    dt = time.perf_counter() - t
    if use_cache:
        try:
            with open(cp, "wb") as f:
                pickle.dump(geoms, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"  (geoms cached to {cp})")
        except Exception as e:
            print(f"  (cache write failed: {e!r})")
    return geoms, dt


def print_histogram(geoms):
    kinds = Counter(g.get("kind", "?") for g in geoms)
    layers = {g.get("layer", "0") for g in geoms}
    pts = sum(len(g.get("points", ())) for g in geoms if g.get("kind") == "path_points")
    print(f"  geoms      : {len(geoms):,}")
    print(f"  layers     : {len(layers):,}")
    print(f"  poly points: {pts:,}  (flattened path_points vertices)")
    print("  kinds      : " + ", ".join(f"{k}={n:,}" for k, n in kinds.most_common()))
    return kinds


# ── rep builders ─────────────────────────────────────────────────────────────
def _record():
    from firepro3d.underlay import Underlay
    return Underlay(type="dxf", path="bench.dxf", colour="#8a8a8a")


def build_rep1(scene, geoms):
    record = _record()
    t = time.perf_counter()
    result = scene._build_batched_underlay_group(geoms, record)
    if result is None:
        raise SystemExit("rep1: no items built")
    group, _layers = result
    scene._attach_snap_index(group, geoms, record)
    scene._apply_underlay_display(group, record)
    scene.underlays.append((record, group))
    dt = time.perf_counter() - t
    # Post-unification: rep1 IS the shipped definition-backed path — the record
    # now owns a reference BlockDefinition and snap runs off its geoms. Log it so
    # the re-bench output proves the definition-backed path was measured.
    d = record.definition
    idx = group.data(4)
    print(f"  definition : {'set' if d is not None else 'MISSING'}"
          f"  render_mode={getattr(d, 'render_mode', '?')}"
          f"  geoms={len(getattr(d, 'geoms', [])):,}"
          f"  snap_over_def_geoms={idx is not None and idx._geom_list is d.geoms}")
    return dt


def build_rep2(scene, geoms):
    from firepro3d.geometry_import import geom_dicts_to_primitives
    from firepro3d.constants import Z_UNDERLAY
    t = time.perf_counter()
    items, skipped = geom_dicts_to_primitives(geoms)
    for it in items:
        it.setZValue(Z_UNDERLAY)
        scene.addItem(it)
    dt = time.perf_counter() - t
    print(f"  primitives : {len(items):,} added as INDIVIDUAL scene items"
          f"  (skipped {skipped:,} unsupported: text/unknown)")
    return dt


def build_rep3(scene, geoms):
    from firepro3d.geometry_import import geom_dicts_to_primitives
    record = _record()
    t = time.perf_counter()
    # Target data model: create + HOLD native primitives (NOT added to scene).
    items, skipped = geom_dicts_to_primitives(geoms)
    scene._bench_primitives = items          # hold the ref (RSS of the data model)
    # Render: batched cosmetic paths (identical content to the held polylines).
    result = scene._build_batched_underlay_group(geoms, record)
    if result is None:
        raise SystemExit("rep3: no items built")
    group, _layers = result
    scene._attach_snap_index(group, geoms, record)   # snap over the same geometry
    scene._apply_underlay_display(group, record)
    scene.underlays.append((record, group))
    dt = time.perf_counter() - t
    print(f"  primitives : {len(items):,} built + HELD (skipped {skipped:,})"
          f"  + batched render paths")
    return dt


# ── interaction loop ─────────────────────────────────────────────────────────
def _cursor_sweep(view, n=24):
    """N scene-coord points on a diagonal across the current viewport."""
    vp = view.viewport().rect()
    pts = []
    for i in range(n):
        f = (i + 0.5) / n
        p = view.mapToScene(int(vp.width() * f), int(vp.height() * f))
        pts.append(p)
    return pts


def _rays(scene, center):
    from firepro3d.align_engine import Ray
    # Two orthogonal ALIGN tracking rays through the geometry centre — exercises
    # the align_paths pass (path×underlay crossings reuse the snap index).
    # Ray.origin is a (x, y) tuple, not a QPointF (align_engine.path_x_path).
    c = (center.x(), center.y())
    return [Ray(c, (1.0, 0.0), "hv", -1),
            Ray(c, (0.0, 1.0), "hv", -1)]


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def measure_interaction(view, scene, app, center):
    """Median snap-ms and paint-ms per interaction step at each zoom + a pan.

    Each step = one ``snap_engine.find`` (SNAP + ALIGN active) then one viewport
    repaint — the real per-frame cost the user feels while moving the cursor.
    """
    eng = scene._snap_engine
    eng.enabled = True
    rays = _rays(scene, center)
    base_t = view.transform()

    def set_zoom(m):
        view.setTransform(base_t)
        view.scale(m, m)
        app.processEvents()

    print(f"  {'zoom':>6} | {'snap ms':>9} | {'paint ms':>9} | {'step ms':>9}")
    results = {}
    for m in (0.5, 1.0, 2.0, 4.0, 8.0):
        set_zoom(m)
        xf = view.transform()
        snaps, paints, steps = [], [], []
        for p in _cursor_sweep(view):
            t0 = time.perf_counter()
            eng.find(p, scene, xf, align_paths=rays)
            t1 = time.perf_counter()
            view.viewport().repaint()
            t2 = time.perf_counter()
            snaps.append((t1 - t0) * 1000)
            paints.append((t2 - t1) * 1000)
            steps.append((t2 - t0) * 1000)
        sm, pm, tm = _median(snaps), _median(paints), _median(steps)
        results[m] = (sm, pm, tm)
        flag = "" if tm <= 16.0 else "  ** >16ms **"
        print(f"  x{m:<5} | {sm:>7.2f} | {pm:>7.2f} | {tm:>7.2f}{flag}")

    # Pan sweep at x2: translate horizontally across the geometry.
    set_zoom(2.0)
    xf = view.transform()
    pan_steps = []
    for i in range(30):
        view.horizontalScrollBar().setValue(
            view.horizontalScrollBar().value()
            + (30 if i < 15 else -30))
        app.processEvents()
        p = view.mapToScene(view.viewport().rect().center())
        t0 = time.perf_counter()
        eng.find(p, scene, xf, align_paths=rays)
        t1 = time.perf_counter()
        view.viewport().repaint()
        t2 = time.perf_counter()
        pan_steps.append((t2 - t0) * 1000)
    pan_med = _median(pan_steps)
    flag = "" if pan_med <= 16.0 else "  ** >16ms **"
    print(f"  {'pan x2':>6} | {'':>9} | {'':>9} | {pan_med:>7.2f}{flag}")
    return results, pan_med


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf")
    ap.add_argument("--scan", action="store_true",
                    help="extract + histogram only (de-risk import); no build")
    ap.add_argument("--rep", type=int, choices=(1, 2, 3), default=None)
    ap.add_argument("--cap", type=int, default=0,
                    help="limit geoms fed to the rep (0 = no cap)")
    ap.add_argument("--sanitize", action="store_true",
                    help="force the DXF sanitize pass (default skips it)")
    args = ap.parse_args()

    if not os.path.exists(args.dxf):
        raise SystemExit(f"not found: {args.dxf}")
    print(f"file: {args.dxf}  ({os.path.getsize(args.dxf) / 1e6:.1f} MB)")

    app = QApplication([])  # noqa: F841 — Qt objects need a running app

    geoms, ext_dt = extract_geoms(args.dxf, args.sanitize)
    print(f"extract: {ext_dt:.1f}s")
    print_histogram(geoms)

    if args.scan or args.rep is None:
        print("\n[scan only] import OK, no corruption/crash. "
              "Re-run with --rep 1|2|3 to bench.")
        return

    if args.cap and len(geoms) > args.cap:
        print(f"  ** CAP: feeding {args.cap:,} of {len(geoms):,} geoms "
              f"({len(geoms) - args.cap:,} dropped) **")
        geoms = geoms[:args.cap]

    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View
    scene = Model_Space()

    builder = {1: build_rep1, 2: build_rep2, 3: build_rep3}[args.rep]
    print(f"\n== REP {args.rep} ==")
    build_dt = builder(scene, geoms)
    n_items = len(scene.items())
    print(f"  build      : {build_dt:.2f}s")
    print(f"  scene items: {n_items:,}")

    view = Model_View(scene)
    view.resize(1600, 900)
    view.show()
    for _ in range(20):
        app.processEvents(); time.sleep(0.02)
    view.fit_to_screen()
    app.processEvents()
    center = view.mapToScene(view.viewport().rect().center())

    print(f"  interaction (snap.find + repaint, SNAP+ALIGN active):")
    measure_interaction(view, scene, app, center)

    print(f"\n  peak RSS   : {peak_rss_mb():,.0f} MB")
    print(f"  SUMMARY rep{args.rep}: extract {ext_dt:.1f}s | build {build_dt:.2f}s"
          f" | items {n_items:,} | peakRSS {peak_rss_mb():,.0f}MB")
    scene._modified = False
    view.close()


if __name__ == "__main__":
    main()
