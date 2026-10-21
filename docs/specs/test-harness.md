---
status: current
applies-to: tests/, tests/conftest.py
last-verified: 2026-10-15  # OS-mouse make_view Account: Invariant 9 -- make_view installs ignore_os_mouse, guard test_snap_polish_os_mouse, same-point window-move caveat; prior suite-stability Account: dispose_main_window (Invariant 6 rule), autosave redirect (Invariant 11 as-built gap closed), chunk layout -> tests/run-suite.psd1 (Invariant 8), leaked-MainWindow crash family; prior 2026-10-14 clipboard-fake Account: `_fake_clipboard` + Invariant 12; prior 2026-10-09 SV3 Account: `_isolate_block_library` also isolates `paths/schematic_dir`; prior 2026-10-01 scene-tools P1 batch: Invariants 9-11 (OS-mouse isolation, stub-scene deterministic teardown, autosave home leak), GC-in-queued-slot crash family; prior 2026-09-30
verified-commit: 1a474a6d   # OS-mouse make_view (main); prior 22c9444c suite-stability (maint/suite-stability tip, fast-forwarded to main); prior 9a9b2d9d clipboard-fake (fixture catalog + Invariant 12); prior 3f31e0af SV3 Account (conftest isolation line only); prior c8ff4f4 scene-tools P1 Account; prior f1d8151 (closable 3D tab), ae6ff19 (Invariant 8 perf marker), d34aeb0
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
  `paths/block_dir` (and, since SV3, `paths/schematic_dir` — the schematic templates
  folder is a second on-disk root the Save-as-Template / New Schematic flows write)
  at a fresh per-test temp dir. See Invariant 7.
- **`_fake_clipboard`** (autouse) + **`FakeClipboard`** — an in-memory stand-in
  patched over `QApplication.clipboard` and `QGuiApplication.clipboard` for every
  test. Opt out with `@pytest.mark.real_clipboard`. See Invariant 12.
- **`_redirect_autosave`** (session, autouse) + **`_isolate_autosave`** (autouse) —
  patch `MainWindow._autosave_path` once per session (importing `main`) and point
  it at a fresh per-test temp dir. See Invariant 11.
- **`dispose_main_window(win)`** (`tests/_mainwindow_helpers.py`, not a fixture) —
  the one teardown for a test `MainWindow`. See Invariant 6's fixture note.
- **`real_qsettings`** — yields the unpatched `QSettings` class so a test can read
  the REAL registry (only the isolation guard test needs this).
- *(retired 2026-09-26: `tmp_settings` and the per-file `isolated_settings` /
  `patched_qsettings` / monkeypatch-`QSettings` redirects — tests read the pane's
  own `QSettings(org, app)`, which the autouse store already isolates per test.
  Explicit INI-file constructions are still honored, not rerouted.)*
- **`model_space` / `make_model_space` / `model_scene` / `shown_model_view` /
  `section_scene_for`** — scene/view factories. `make_model_space` and
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
   `QMouseEvent`/`QKeyEvent`. Calling handlers directly, or `QTest.mouseMove` on a
   widget, is a false green (drives zero handlers).
   - **Tests drive handlers with `QApplication.sendEvent`** (non-spontaneous events).
     The two `QTest.mouseMove` overloads are not substitutes:
     - **`QTest.mouseMove(<QWidget>, …)` — never.** It moves the **user's real cursor**
       (`QCursor::setPos`; a 2026-10-01 fixer did exactly that) and any resulting move
       arrives asynchronously, if at all — the false green above.
     - **`QTest.mouseMove(<QWindow>, …)`** (`view.window().windowHandle()`) injects a
       **spontaneous** window-system move without touching the cursor. It is only for
       *simulating OS input* in an Invariant 9 guard
       (`test_os_mouse_input_cannot_reaim_the_axis`); `ignore_os_mouse` drops exactly
       these events, so it is never a way to drive handlers.

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
     module (why the crash *moves* with test selection), and an app-wide
     `setStyleSheet` repolish walks its half-dead widgets. **Rule (2026-10-15):**
     every fixture or test body that builds a real `MainWindow` tears it down with
     `tests/_mainwindow_helpers.dispose_main_window(win)` — clears the plan
     selection, drops the dirty flag, `close()`, `deleteLater()`, then
     `sendPostedEvents(None, DeferredDelete)` so the window dies now. Restores
     that touch app-wide state (`setStyleSheet`, fonts, snap globals) run
     *after* it. Exceptions: fake windows, and the raw-teardown child-process
     guard `test_mainwindow_teardown_gc.py`. Guard:
     `tests/test_mainwindow_dispose.py` (its premise test proves close +
     deleteLater alone leaves the window alive).
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
   chunks, one process each (a single process is memory-killed), with
   `-m "not perf"`. The chunk layout, the isolate list (known native-crash files
   run in their own process) and the run environment live in
   **`tests/run-suite.psd1`**, consumed by the /todo plugin's `run-suite.ps1`
   (its suite-runner spec owns the perf stage: perf guards run only when the diff
   touches a configured `PerfPaths` entry, or with `-Perf run` — none are
   configured yet). Every process's exit code is read on its own (VC6). A generous sanity bound
   that is "not a benchmark" (seconds, orders of magnitude of slack) stays
   unmarked. Why: 2026-09-26 the offset guard measured 31.7 ms in-batch vs
   22.8 ms standalone — load, not a regression.
9. **Shown test windows are deaf to the real OS mouse.** A shown, exposed view
   (Invariant 4) can sit under the user's real cursor; every real mouse move over it
   arrives as a **spontaneous** event between a test's own events and its assertions
   and re-aims hover-driven state (Flip / Mirror axis, Scale / Array ghosts, offset
   distance, snap / ALIGN acquisition). Root cause **proven 2026-10-01** for the
   shown-window flakes (probe log of spontaneous `MouseMove`s at the user's cursor;
   deterministic repro via the `QWindow` overload above). Rule: a test that shows a
   view and asserts hover-driven state wraps it in **`ignore_os_mouse(view)`**
   (`tests/_modify_tools_helpers.py`) — a viewport event filter (parented to the
   viewport) that drops spontaneous mouse-move / press / release / double-click /
   wheel events; the test's own `sendEvent`ed events (`spontaneous() is False`) still
   pass. **`tests/_snap_polish_helpers.make_view` installs it itself** (before
   `show()`, 2026-10-15), so every `make_view` view is deaf — don't re-wrap one
   (a second filter is harmless but redundant); a view built any other way (a
   hand-built second `Model_View`, a Block Editor or MainWindow view) still calls
   `ignore_os_mouse` itself. Guards: `tests/test_snap_polish_os_mouse.py` (a snap
   cannot be re-aimed) and
   `test_modify_tools_flip_mirror.py::test_os_mouse_input_cannot_reaim_the_axis` —
   both RED with the `make_view` filter removed. Each sends a window-system move
   (`QTest.mouseMove` on the `QWindow`) to its own point: Qt drops a move to the
   position the window already holds, so two guards in one process aiming at the
   same point leave the second with no OS move (its `assert seen` fails).
10. **A Python-owned stub scene is destroyed deterministically at fixture exit.**
    `tests/test_scene_tools.py`'s `scene` fixture delegates to the
    `stub_scene_session(qapp)` context manager, which `sip.delete()`s the view and the
    `_StubScene` on exit (`f766f73`). Why: the stub scene was kept alive only by a
    reference cycle (`scene._tools = SceneTools(scene)` ↔ `SceneTools._scene`) with
    posted events still queued on it (`_q_polishItems`, index / update). The next
    test's `processEvents()` dispatched them into the garbage scene; a cyclic GC firing
    inside the resulting Python virtual (`itemChange` / `shape`) freed the scene under
    Qt → "wrapped C/C++ object has been deleted" → PyQt `qFatal` → silent `0xC0000409`
    (exit 127). `~QObject` purges the queued events, so deleting at teardown closes
    it. Rule: any fixture that builds a Python-owned scene/view kept alive by a cycle
    `sip.delete()`s it at teardown — `view.close()` alone is not enough. Guards:
    `TestStubSceneTeardown` (deletion contract + a child-process repro asserting exit 0).
11. **Tests must not reach the user's real home folder.** `MainWindow` autosaves to
    `~/.firepro3d/autosave/recovery.FPD` (`os.path.expanduser("~")` — the APPDATA
    monkeypatch does not cover it), and `closeEvent` / `_check_recovery` *delete*
    that file. Unredirected, a test could plant one (every later `MainWindow`
    fixture hangs on the Recover dialog) or wipe the user's real one. conftest's
    session autouse `_redirect_autosave` patches `MainWindow._autosave_path` before
    any module fixture builds a window (many test bodies import `main` lazily, so
    the patch is on the class, once); the function autouse `_isolate_autosave`
    repoints it at a fresh per-test dir. A module-scoped window built before a
    test's function fixtures sees the previous test's (temp) dir — never home.
    Per-file `_autosave_path` patches still win inside their own scope (filed for
    retirement). A child process (no conftest) redirects its own path, as
    `test_mainwindow_teardown_gc.py` does. Guards: `tests/test_autosave_isolation.py`
    (real `_autosave` / `_check_recovery` paths; the real home file's existence and
    mtime unchanged). Never delete a real `recovery.FPD` without asking the user.

12. **Tests never depend on the OS clipboard.** The Windows clipboard refuses writes
    (ACCESS_DENIED) while another process holds it, so every test gets a fresh
    in-memory `FakeClipboard` (`text` / `setText` / `clear` / `dataChanged`, emitted
    synchronously) in place of `QApplication.clipboard()` and
    `QGuiApplication.clipboard()`. The only test that needs the real one is a Qt text
    control's own Ctrl+C / Ctrl+V (it never goes through Python) and carries
    `@pytest.mark.real_clipboard`; it still fails while the OS clipboard is held. A
    test that must simulate a dead clipboard patches the accessors itself
    (`dead_clip`) and layers over the fake. **The fixture owns a private
    `pytest.MonkeyPatch()` — never request the shared `monkeypatch` fixture from an
    autouse fixture:** that sets `monkeypatch` up before every test's own fixtures and
    tears it down after them, so a test that patches a method its fixture's teardown
    calls errors at teardown (`test_selection_readouts_fixes`). Guard:
    `tests/test_fake_clipboard.py`.

## Known native-crash families

- **Orphaned-lambda destruction emit** — a parentless `PaperScene` (non-empty undo
  stack) outlives its `MainWindow`; its GC-time `indexChanged` ran `main.py`
  `self`-lambdas against the dead window (`0xC0000005` "Garbage-collecting →
  main.py <lambda>", or silent `0xC0000409`/exit 127 at shutdown). Fixed
  2026-09-23 by bound-method connects (Invariant 6).

- **GC inside a Qt-queued slot (Python-owned stub scene)** — a garbage `_StubScene`
  whose queued posted events are dispatched by a later test's `processEvents()`; a GC
  inside the dispatched Python virtual frees the scene under Qt → `qFatal` →
  `0xC0000409` / exit 127 (`test_scene_tools.py`, GC-timing sensitive, pre-existing).
  Fixed `f766f73` (Invariant 10). The whole `tests/test_[s-z]*.py` chunk, which used to
  abort reproducibly in `test_scene_tools.py` when the earlier s-z files shared the
  process, ran clean in **one** process at `c8ff4f4` (2105 passed, exit 0) — **likely
  fixed by `f766f73`, pending one more confirming VC6 run** (`todo_open.md` keeps the
  s-z chunk item open until then).
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
  (`mainwindow-chrome-revamp.md`). **Fixture workaround:**
  `dispose_main_window` clears the plan scene's selection before `close()`
  (Invariant 6 note; other scenes' selections are a filed latent gap). Remove the
  workaround when the bug is fixed (disconnect selection slots in
  `closeEvent`, or guard the slot).
- **Leaked-MainWindow repolish / exit 127** (closed 2026-10-15) — module-singleton
  windows outlived their module and crashed a later app-wide `setStyleSheet` or a
  later test's event pump; `test_opening_ribbon.py` exited 127 every run (base
  127 x4 vs 0 x4 after the fix). Fixed by `dispose_main_window` (Invariant 6).
  Remaining intermittent native faults and the `test_block_drag_drop.py` in-body
  crash are tracked in `todo_open.md` ("Full-suite native crashes split the
  chunked VC6 run").
