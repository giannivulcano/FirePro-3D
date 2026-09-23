---
status: current
applies-to: tests/, tests/conftest.py
last-verified: 2026-09-23
verified-commit: 72412e2
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
- **`tmp_settings`** — an explicit INI-backed `QSettings(path, IniFormat)` for
  ALIGN-settings round-trips. Predates the autouse isolation; still valid (explicit
  INI-file constructions are honored, not rerouted).
- **`model_space` / `make_model_space` / `model_scene` / `shown_model_view` /
  `elevation_scene_for`** — scene/view factories. `make_model_space` and
  `shown_model_view` call `scene.cleanup()` on teardown (worker drain, Invariant 2).
  `shown_model_view` `show()`s + exposes + focuses the view (Invariant 4).
- **`tiny_png_b64`** — shared title-block image fixture.
- **`stub_view3d`** (opt-in) — windowless `_StubView3D` injected into `main.View3D`
  (#367). See Invariant 3.

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
   viable (VTK native-crashes without a GL surface). Real-View3D coverage lives only
   in `test_view_3d.py` (`pv.OFF_SCREEN=True`).

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
  (Invariant 3) and `view_3d.cleanup()` on close.
