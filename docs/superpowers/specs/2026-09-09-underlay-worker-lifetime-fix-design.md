# Underlay DXF Worker Lifetime Fix (#371) — Design

**Date:** 2026-09-09
**Scope:** the source-side mechanism only. Part of the P2 test-infrastructure cluster
(#312 QSettings isolation, #367 View3D stub, #371 this, #375 `tests/` governing spec).
The other three are problem-defined and planned directly; only #371 warranted a design pass.

## Goal

Make a **leaked** async `DxfImportWorker` structurally unable to crash the test suite
(deterministic `0xC0000409`), so the fix neutralises the whole *class* of leak — not just
one known leaking test.

## Motivation

`DxfImportWorker` is a `QThread` subclass; `run()` executes on the worker thread and emits
`progress/status/finished_data/error` → **queued** delivery to the main thread.

In `UnderlayController.import_dxf` the four signals are connected to **lambdas** that capture
`progress` (a `QProgressDialog` parented to `self._scene.views()[0]`, so it dies with the
view/scene) and `self` (the controller — a deliberately **plain object**, not a `QObject`).

When a test **leaks** the worker (never calls `cleanup()`), the scene/view is torn down and the
progress dialog's C++ object is deleted, but the worker lives on with a queued `finished_data`
meta-call still in the main-thread event queue. Because a functor/lambda connection's queued
**receiver defaults to the still-alive sender (the worker)**, Qt *dispatches* the call, and
dispatch faults touching the deleted dialog — **before** the lambda's Python body runs. Therefore
the receiver-side guard (`_drop_late_signal` / `sip.isdeleted`) never gets a chance. Faulthandler
shows a bare `<lambda>` with no `_on_dxf_*` frame.

**False-green trap:** a manual main-thread `signal.emit()` is a *direct* call that DOES hit the
Python guard and passes vacuously. The real crash is cross-thread/queued-only.

## Key Qt semantic exploited

When a `QObject` is C++-deleted, `~QObject` calls `QCoreApplication::removePostedEvents(obj)`,
which purges any pending `QMetaCallEvent` whose **receiver** is that object. So if the queued
delivery's receiver is an object that **dies with the scene/view**, its deletion purges the event
and it is never dispatched.

The current bug is precisely that the receiver (via the lambda) is the *worker* (sender), which
outlives the scene. Fix = make the receiver something that dies with the scene.

## Architecture & Constraints

- Minimal, arm's-length change to `UnderlayController`; the controller **stays a plain object**.
  The QObject-ness required to be a purgeable receiver is quarantined in a dedicated small class.
- Keep all existing hardening (do not regress): `_cleanup_dxf_worker()` disconnect/cancel/quit/wait,
  `Model_Space.cleanup()`, the `make_model_space`/`shown_model_view` fixture drains, and the
  `_drop_late_signal` receiver-side guard.
- Files touched: `firepro3d/underlay_controller.py` only + one new test file.

## Design Decisions

### New unit — `_DxfWorkerSink(QObject)` (module-private, ~15 lines)

- **Purpose:** be the queued-call *receiver* whose deletion purges pending meta-calls.
- **Shape:** constructed as `_DxfWorkerSink(controller, progress, parent=scene)`. Holds a back-ref
  to the controller and the captured `progress`. Four slots — `on_progress(cur, tot)`,
  `on_status(msg)`, `on_finished(geom_list)`, `on_error(msg)` — each **delegates verbatim** to the
  controller's existing `_on_dxf_*(…, progress)`. No logic moves into the sink; it is pure
  forwarding. QObject affinity is confined here.
- **Depends on:** the controller + the QObject parent (the scene). Nothing else.

### Wiring change — `import_dxf` (currently underlay_controller.py:96–109)

- Create `self._dxf_sink = _DxfWorkerSink(self, progress, parent=self._scene)`.
- Connect the four worker signals to the **sink's bound methods** instead of lambdas.
- `progress.canceled.connect(worker.cancel)` is unchanged — the receiver there is the worker and
  `cancel()` only sets a thread-safe flag, so there is no dead-object hazard.

### Cleanup change — `_cleanup_dxf_worker`

- Keep the existing disconnect/cancel/quit/wait exactly (the disconnect loop now severs the
  sink-bound connections). After it, `deleteLater()` the sink and null `self._dxf_sink`.

### Parent choice — the scene (not the dialog/view)

The sink is parented to `self._scene` (a `QGraphicsScene`, i.e. a `QObject`) rather than the
progress dialog or view, because the scene is the controller's back-reference and is the most
robust lifetime anchor (exists even when there is no view / no dialog). In the crash scenario the
scene *is* torn down, so a scene-child sink is deleted with it → purge.

## Behavior

- **Leaked worker + scene/view torn down (the crash):** sink (scene child) is C++-deleted →
  `removePostedEvents(sink)` purges the queued `finished_data` → never dispatched → **no crash**.
  Class-safe for any future leaker.
- **Scene alive, dialog dead:** dispatch reaches the *live* sink → `_on_dxf_*` →
  `_drop_late_signal` (`sip.isdeleted(progress)`) drops it. Existing guard kept as defense-in-depth.
- **Normal import:** identical behavior to today.

## Acceptance Criteria

- Full suite **completes** (the `0xC0000409` abort is gone) — the headline, since today it cannot
  finish.
- Zero *new* failures vs the `main` baseline (pre-existing failures diffed out, not counted).
- Existing `cleanup()` / `_drop_late_signal` hardening intact.
- A regression test demonstrates **RED on revert** via a genuine cross-thread/queued repro.

## Verification — regression proof (RED-on-revert), subprocess-based

A parent test spawns a child Python process that:

1. Builds `QApplication` + `Model_Space` + a real `QGraphicsView` (the dialog's parent).
2. Calls the real `import_dxf` on a tiny DXF fixture → real `DxfImportWorker` thread; `worker.wait()`
   so `run()` has emitted `finished_data` (queued, **not** dispatched).
3. **Does NOT call `cleanup()`** (simulates the leak); deletes the view/scene so the dialog dies.
4. `app.processEvents()` → dispatch attempt; then `print("OK"); sys.exit(0)`.

Parent asserts **child exit code == 0**. Fix reverted (lambdas → worker receiver) → child aborts
(SEH / non-zero) → RED. Fix present → sink purged with the scene → GREEN. Real QThread + real queued
emit means no direct-emit false green. The test doubles as verification of the purge semantic: if
the semantic were wrong, the fixed build would also crash.

**Fallback gate** (if the micro-repro proves non-deterministic): full suite green ×3 on a committed
tree.

## Out of Scope

- The exact leaking-test bisect/drain is best-effort defense-in-depth (per the cluster grill), not
  an acceptance gate.
- `thermal_radiation_report._export_pdf` QPrinter twin (#373-sibling) — documented in the `tests/`
  governing spec (#375), not fixed here.
