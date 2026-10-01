---
status: current
applies-to: tests/, tests/conftest.py
last-verified: 2026-09-30  # closable 3D tab: stub_view3d surface, real-View3D test files, MainWindow-teardown selection family; prior 2026-09-29
verified-commit: f1d8151   # closable 3D tab; prior ae6ff19 (Invariant 8 perf marker), d34aeb0
---

# Test Harness — Governing Spec

**Purpose & scope.** Governs `tests/` conventions and the shared `tests/conftest.py`
fixtures. Closes the `tests/` SPEC-INDEX orphan. The recurring native-crash loci
(QPrinter-SEH, underlay-worker queued-dispatch, VTK-MainWindow) live here because
they are properties of the harness, not of any one subsystem under test.

Forged 2026-09-09 on first touch (the #312/#367/#373/#375 test-infra cluster; the
underlay-worker crash is repo bug **#373** — some cluster commits/design-doc call it
"#371" as a line-number shorthand, which collides with the already-fixed QPrinter
SEH bug #371).

## Fixture catalog (`tests/conftest.py`)

- **`qapp`** (session) — the single process `QApplication`. Never `app.quit()` (Qt
  dislikes repeated `QApplication` creation within a process).
- **`_preserve_snap_globals`** (autouse) — snapshot/restore
  `snap_engine.SNAP_TOLERANCE_PX` / `SNAP_HYSTERESIS_PX` around every test.
- **`_isolate_qsettings`** (autouse) + **`_IsolatedQSettings`** (module-level class
  install) — QSettings isolation (#312). See Invariant 1.
- **`_isolate_block_library`** (autouse, layered on `_isolate_qsettings`) — points
  `paths/block_dir` at a fresh per-test temp dir. See Invariant 7.
- **`real_qsettings`** — yields the unpatched `QSettings` class so a test can read
  the REAL registry (only the isolation guard test needs this).
- *(retired 2026-09-26: `tmp_settings` and the per-file `isolated_settings` /
  `patched_qsettings` / monkeypatch-`QSettings` redirects — tests read the pane's
  own `QSettings(org, app)`, which the autouse store already isolates per test.
  Explicit INI-file constructions are still honored, not rerouted.)*
- **`model_space` / `make_model_space` / `model_scene` / `shown_model_view` /
  `elevation_scene_for`** — scene/view factories. `make_model_space` and
  `shown_model_view` call `scene.cleanup()` on teardown (worker drain, Invariant 2).
  `shown_model_view` `show()`s + exposes + focuses the view (Invariant 4).
- **`tiny_png_b64`** — shared title-block image fixture.
- **`stub_view3d`** (opt-in) — windowless `_StubView3D` injected into `main.View3D`
  (#367). Mirrors the MainWindow→View3D surface owned by `view-3d.md §4`
  (2026-09-30: `cancel_interaction`, `request_rebuild`, `clear_pick`,
  `reset_for_project` added; `_on_escape` retired). See Invariant 3.

## Invariants

1. **QSettings isolation (#312).** Tests never read/write the real Windows
   registry. Windows `NativeFormat` ignores `setPath()`/`setDefaultFormat()` for the
   2-arg `QSettings("GV","FirePro3D")` form (verified: `format()` stays
   `NativeFormat`, `fileName()` is the HKCU path), so isolation is done by a
   class-level `_IsolatedQSettings` subclass installed at conftest import: it
   reroutes registry-scope constructions to a **fresh per-test temp INI**, keyed by
   the string args, while honoring explicit `QSettings(path, IniFormat)`
   constructions unchanged. The `real_qsettings` fixture is the only sanctioned way
   to touch the real registry (guard test). Redundant per-test monkeypatch/INI
   fixtures still work (explicit forms take precedence) and are a filed follow-up to
   retire.

2. **Async-worker lifetime (#373).** A scene that starts an async worker must be
   drainable via `Model_Space.cleanup()` (joins + disconnects the DXF worker), AND
   worker signals must be routed through a **scene-parented `QObject` sink**
   (`_DxfWorkerSink`) so a *leaked* worker's queued `finished_data` meta-call is
   purged by `~QObject.removePostedEvents` when the scene is destroyed — instead of
   dispatching into a dangling receiver after the worker's C++ object is GC'd
   (native access violation). Receiver-side `sip.isdeleted` guards
   (`_drop_late_signal`) are defense-in-depth, NOT the primary safety.
   - **Test hygiene:** a fixture that constructs a `Model_Space`/`MainWindow` which
     may import a DXF should `cleanup()` on teardown. Known un-draining module
     fixtures (candidates, harmless now that the source fix purges leaks):
     `test_underlay_display.py` and `test_underlay_manager_launch.py`
     (`_main_window_singleton`).
   - **Repro rule:** a native-abort regression must use a REAL `QThread` + REAL
     queued emit in a **child process** (assert exit code 0). A direct main-thread
     `signal.emit()` is a direct call that hits the Python guard → false green.

3. **View3D stub (#367).** MainWindow-heavy tests may use the opt-in `stub_view3d`
   fixture to run windowless with no VTK plotter. `QT_QPA_PLATFORM=offscreen` is NOT
   viable (VTK native-crashes without a GL surface). Real-View3D unit coverage uses
   `pv.OFF_SCREEN=True` (`test_view_3d.py` over a fake scene,
   `test_view3d_lifecycle.py` over a real `Model_Space`);
   `test_view3d_tab_mainwindow.py` drives a real MainWindow + real View3D in a
   shown, exposed window (visibility-gated behaviour needs `isVisible()`). The
   file list is owned by `view-3d.md §8`. Any new MainWindow→View3D call must be
   added to the stub in the same commit (`view-3d.md §4` owns the surface).

4. **Posted events need shown views.** Tests exercising focus / event-dispatch /
   render must `show()` + expose the view (see `shown_model_view`) and post real
   `QMouseEvent`/`QKeyEvent`. Calling handlers directly, or `QTest.mouseMove`, is a
   false green (drives zero handlers).

5. **Never construct a real `QPrinter` in the suite — use `QPdfWriter`.** A real
   `QPrinter` PDF export in-suite raises first-chance SEH. Known latent instance:
   `thermal_radiation_report._export_pdf` (`QPrinter(HighResolution)` + `PdfFormat`),
   the twin of the hydraulic report fixed 2026-09-09. Mirror that fix (→ `QPdfWriter`,
   A4 + res 1200, `doc.print()`) when the thermal-radiation subsystem is next touched.

6. **No `self`-lambda slots on signals of objects that can outlive their
   receiver.** PyQt auto-disconnects a **bound-method** slot when its receiver
   `QObject` is destroyed; a `self`-capturing **lambda** has no receiver and stays
   connected forever. `PaperSpaceWidget.paper_scene` is parentless (Python-owned),
   so it outlives a deleted `MainWindow` in a reference cycle; when a later GC
   destroys it, `~QUndoStack` → `clear()` emits `indexChanged(0)` (only if the stack
   is non-empty) into whatever is still connected. Rule: connect such signals to
   bound methods (PyQt drops surplus signal args for a no-arg slot). Regression:
   `tests/test_mainwindow_teardown_gc.py` (child process, exit 0).
   - **Fixture note:** module-singleton `close()` + `deleteLater()` +
     `processEvents()` does **not** delete the window — DeferredDelete isn't
     dispatched at that loop level. The window lingers until a later test's pump
     flushes it, so its destruction-time signals fire mid-way through an unrelated
     module (why the crash *moves* with test selection).
7. **No test reads or writes the user's real block library.** A blank
   `paths/block_dir` resolves to the REAL `%APPDATA%/FirePro3D/blocks`; the Blocks
   browser reads it at construction and Save flows write it, so a test using the
   default root was coupled to whatever the developer had saved (2026-09-23: a
   smoke-test "Test" folder broke `test_block_browser.py`). `_isolate_block_library`
   sets the override to a per-test temp dir. Tests that need a specific tree still
   pass an explicit `root=`; a test of the override itself sets/resets the key.
8. **Wall-clock timing guards are `perf`-marked and run in their own process.**
   A guard that asserts an absolute latency (e.g. the offset ghost's ≤ 30 ms real
   mouse move, the handle-snap ≤ 16 ms move) carries `@pytest.mark.perf`
   (registered in `pytest.ini`). Its threshold is the contract and is never
   loosened; host load is excluded instead: the full suite runs as alphabetical
   chunks (`[a-d] [e-l] [m-r] [s-t] u [v-z]`, one process each — a single process
   is memory-killed) with `-m "not perf"`, plus one standalone `-m perf` process.
   Every process's exit code is read on its own (VC6). A generous sanity bound
   that is "not a benchmark" (seconds, orders of magnitude of slack) stays
   unmarked. Why: 2026-09-26 the offset guard measured 31.7 ms in-batch vs
   22.8 ms standalone — load, not a regression.

## Known native-crash families

- **Orphaned-lambda destruction emit** — a parentless `PaperScene` (non-empty undo
  stack) outlives its `MainWindow`; its GC-time `indexChanged` ran `main.py`
  `self`-lambdas against the dead window (`0xC0000005` "Garbage-collecting →
  main.py <lambda>", or silent `0xC0000409`/exit 127 at shutdown). Fixed
  2026-09-23 by bound-method connects (Invariant 6).

- **QPrinter-SEH** — a real `QPrinter` PDF export in-suite raises first-chance SEH
  (e.g. `0xe0000001`). Hydraulic report fixed 2026-09-09; thermal twin latent
  (Invariant 5).
- **Underlay-worker queued-dispatch** — a leaked `DxfImportWorker` dispatching a
  queued meta-call into a dangling receiver after its C++ object is GC'd (native
  access violation `0xC0000005`/`0xC0000409`). Fixed by the scene-parented sink
  (Invariant 2).
- **VTK-MainWindow native-child-window** — View3D forces native sibling windows;
  MainWindow suites can `qFatal` / abort on teardown. Mitigated by `stub_view3d`
  (Invariant 3) and `view_3d.cleanup()` on close (which, since 2026-09-30, also
  stops the rebuild timer and disconnects View3D's scene slots — `view-3d.md` I11).
- **MainWindow-teardown selection emit** (found 2026-09-30, closable-3D-tab
  build; pre-existing — filed as a bug, not fixed). If a plan item is still
  selected when a real MainWindow `close()`s, the scene's destruction emits
  `selectionChanged` into `MainWindow._on_selection_changed_contextual`, which
  reads the half-destroyed scene → `RuntimeError` from a Qt slot → process exit
  127. The same race was first noted in the Stage-One chrome spike
  (`mainwindow-chrome-revamp.md`). **Fixture workaround:** call
  `scene.clearSelection()` before `close()` (as in
  `tests/test_view3d_tab_mainwindow.py`'s window fixture). Remove the
  workaround when the bug is fixed (disconnect selection slots in
  `closeEvent`, or guard the slot).
