# Snap Polish Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SNAP accurate and complete. That means curve snaps landing on the curve, ALIGN crossings reaching the picker, a true perpendicular-from-start, handle snapping while moving, Ctrl angle-snap on polyline/polygon vertices, 2-point polylines committing as lines, and text emitting snap points.

**Architecture:**
- Most of the change is engine-level, in `snap_engine.py`: exact circle/curve geometry, a `from_point` input for perpendicular-from-start (PER), and a "weak foot" dominance rule so ALIGN crossings beat cursor-foot snaps.
- `Model_Space.get_effective_position` collapses its two tiers into one `find()` call.
- Move snapping gets a small new module, `handle_snap.py`. It collects the targets once per gesture and tests the moving items' own snap points on every mouse move.
- The grip, polyline and text changes reuse the existing handles, helpers and accessors.

**Tech Stack:** Python 3, PyQt6, pytest (no pytest-qt; `qapp` fixture), real `Model_Space`/`Model_View` with posted `QMouseEvent`s.

**Requirements:** `docs/plans/2026-09-24-snap-polish-requirements.md` (user-ratified 2026-09-24).
**Governing specs:** snapping-engine, align-placement, selection-manipulator, 2d-geometry, text-annotation-system, wall-room-floor-system, block-system.

**Conventions for every task**
- Run tests with the venv: `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" -m pytest <paths> -q`. Do NOT set `QT_QPA_PLATFORM=offscreen` for the floor/MainWindow tests, because PyVista aborts under offscreen. Plain `Model_Space`/`Model_View` tests are fine either way.
- Guard tests drive the real path: a shown `Model_View`, posted mouse events, and real items. Every guard is shown RED against the pre-change code: run it before implementing.
- Commit per task on branch `feat/snap-polish`.
- Snap-engine tunables such as `SNAP_TOLERANCE_PX` are module globals. Read them as `snap_engine.SNAP_TOLERANCE_PX` at call time; never copy them at import.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `tests/_snap_polish_helpers.py` | Create | Shared real-view builder + posted mouse helpers for this batch's guards |
| `firepro3d/snap_engine.py` | Modify | S4 exact circle/curve geometry; S5 weak-foot dominance; S1 `from_point` PER; S6 TextItem arm + block glyph suppression + block text box points |
| `firepro3d/model_space.py` | Modify | S5 one-picker seam; S1 `_snap_from_point`; S3b `_finish_polyline`; Fold D floor/roof Ctrl; S2 Move-tool hook |
| `firepro3d/manip_handle.py` | Modify | S3a `vertex_chain_grip_handles`; S2 `TranslateGripHandle` + raw-pos capture |
| `firepro3d/geometry_2d.py` | Modify | S3a PolylineItem handles; S2 LineItem midpoint handle; Fold E `last_point()` |
| `firepro3d/floor_slab.py`, `firepro3d/roof.py` | Modify | S3a vertex handles; Fold E `last_point()` |
| `firepro3d/block_definition.py` | Modify | S6 `text_snap_points()` cache |
| `firepro3d/handle_snap.py` | Create | S2 `HandleSnapSession` (targets once, handle×target per move) |
| `firepro3d/selection_manipulator.py` | Modify | S2 interior-drag uses `HandleSnapSession` |
| `firepro3d/geometry_drawing_controller.py`, `firepro3d/placement_input_coordinator.py` | Modify | Fold E call sites |
| `firepro3d/model_view.py` | Modify | Fold A docstring only |
| `firepro3d/constants.py` | Modify | `HANDLE_SNAP_MAX_HANDLES` |
| tests (new) | Create | `test_snap_curve_accuracy.py`, `test_snap_align_crossing_seam.py`, `test_snap_perpendicular_from.py`, `test_snap_text_points.py`, `test_polyline_polygon_ctrl.py`, `test_polyline_two_point_finish.py`, `test_move_handle_snap.py` |

**Execution grouping (FP6):**
- Tasks 2–5 are one coupled implementer group (same engine file and the same seam function, built up incrementally).
- Tasks 6, 7–10 and 11–12 are independent groups.
- Task 13 (docs) runs last.

---

### Task 1: Shared test helpers

**Files:**
- Create: `tests/_snap_polish_helpers.py`

- [ ] **Step 1: Write the helper module**

```python
"""Real-path helpers for the 2026-09-24 snap-polish guards.

Builds a SHOWN Model_View over a real Model_Space (pinned zoom) and posts real
QMouseEvents to the viewport, so presses/moves route through the scene's own
dispatch (get_effective_position, manipulator, placement handlers).
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication


def make_view(role: str = "block_editor", scale: float = 0.25, mode: str | None = "select"):
    """Return (view, scene): shown 800x600 Model_View, m11 == *scale*, centred on 0,0."""
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View
    from firepro3d.scale_manager import ScaleManager

    scene = Model_Space(scene_role=role)
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    view = Model_View(scene)
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.scale(scale, scale)
    view.centerOn(0, 0)
    view.setFocus()
    QApplication.processEvents()
    if mode is not None:
        scene.set_mode(mode)
    return view, scene


def close_view(view, scene) -> None:
    scene.cleanup()
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def post(view, etype, spt: QPointF,
         mods=Qt.KeyboardModifier.NoModifier,
         button=Qt.MouseButton.LeftButton) -> None:
    """Post one mouse event at scene point *spt* (float-mapped, not rounded)."""
    vpf = view.viewportTransform().map(spt)
    if etype == QEvent.Type.MouseMove:
        btn, btns = Qt.MouseButton.NoButton, (
            button if getattr(view, "_snap_polish_pressed", False) else Qt.MouseButton.NoButton)
    elif etype == QEvent.Type.MouseButtonRelease:
        btn, btns = button, Qt.MouseButton.NoButton
    else:
        btn, btns = button, button
    ev = QMouseEvent(etype, vpf, view.viewport().mapToGlobal(vpf), btn, btns, mods)
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def click(view, spt: QPointF, mods=Qt.KeyboardModifier.NoModifier) -> None:
    post(view, QEvent.Type.MouseButtonPress, spt, mods)
    post(view, QEvent.Type.MouseButtonRelease, spt, mods)


def move(view, spt: QPointF, mods=Qt.KeyboardModifier.NoModifier) -> None:
    post(view, QEvent.Type.MouseMove, spt, mods)


def drag(view, start: QPointF, end: QPointF, steps: int = 6,
         mods=Qt.KeyboardModifier.NoModifier) -> None:
    """Press at *start*, move in *steps* to *end* (mods on EVERY event), release."""
    post(view, QEvent.Type.MouseButtonPress, start, mods)
    view._snap_polish_pressed = True
    try:
        for i in range(1, steps + 1):
            t = i / steps
            move(view, QPointF(start.x() + (end.x() - start.x()) * t,
                               start.y() + (end.y() - start.y()) * t), mods)
    finally:
        view._snap_polish_pressed = False
    post(view, QEvent.Type.MouseButtonRelease, end, mods)


def dwell(view, spt: QPointF) -> None:
    """Real ALIGN dwell acquire: two moves on the same point 450 ms apart."""
    move(view, spt)
    time.sleep(0.45)
    move(view, spt)
```

- [ ] **Step 2: Sanity-run an import**

Run: `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" -c "import tests._snap_polish_helpers"`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add tests/_snap_polish_helpers.py
git commit -m "test(snap-polish): shared real-view + posted-mouse helpers"
```

---

### Task 2: S4a — circle snaps use the geometric rect, not boundingRect()

**Files:**
- Modify: `firepro3d/snap_engine.py` — the `_collect` QGraphicsEllipseItem branch (`br = item.boundingRect()`, ~L1158) and the `_geometric_snaps` full-circle branch (~L1679)
- Modify: `tests/test_snap_engine_matrix.py::TestFullCircle` (VC5 coupled rewrite)
- Test: `tests/test_snap_curve_accuracy.py` (new)

- [ ] **Step 1: Write the failing guard**

```python
"""S4 guard — grip-dragging an endpoint onto a circle/arc/ellipse lands ON the curve."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import ArcItem, CircleItem, EllipseItem, LineItem
from tests._snap_polish_helpers import close_view, drag, make_view

R = 500.0
A45 = math.radians(-45)      # scene Y-down: upper-right on screen


def _drag_line_end_to(view, scene, target_pt):
    ln = LineItem(QPointF(-1200, -900), QPointF(-800, -900))
    scene.addItem(ln)
    scene.clearSelection()
    ln.setSelected(True)
    drag(view, ln.grip_points()[2], target_pt)
    return ln.grip_points()[2]


@pytest.mark.parametrize("scale", [0.25, 1.0])
def test_circle_endpoint_lands_on_circle(qapp, scale):
    view, scene = make_view(scale=scale)
    try:
        scene.addItem(CircleItem(QPointF(0, 0), R))
        off = 3.0 / scale
        ep = _drag_line_end_to(view, scene, QPointF((R + off) * math.cos(A45),
                                                   (R + off) * math.sin(A45)))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 0.01
    finally:
        close_view(view, scene)


def test_circle_after_zoom_change_lands_on_circle(qapp):
    view, scene = make_view(scale=0.25)
    try:
        circ = CircleItem(QPointF(0, 0), R)
        scene.addItem(circ)
        circ.boundingRect()                      # cache the bbox at 0.25
        view.resetTransform(); view.scale(1.0, 1.0); view.centerOn(0, 0)
        qapp.processEvents()
        ep = _drag_line_end_to(view, scene, QPointF(R + 3.0, 0.0))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 0.01
    finally:
        close_view(view, scene)
```

- [ ] **Step 2: Run and confirm RED**

Run: `...python.exe -m pytest tests/test_snap_curve_accuracy.py -q`
Expected: FAIL. The errors are ~20 mm at 0.25, ~5 mm at 1.0, and ~20 mm after the zoom change.

- [ ] **Step 3: Implement.** In `_collect`'s ellipse branch replace `br  = item.boundingRect()` with:

```python
            # Geometric ellipse rect — NOT boundingRect(): a CircleItem's
            # bounding rect is its ~10 px hit-stroke shape() (radius + 5 px),
            # frozen by Qt's bbox cache at the zoom it was first computed.
            br  = item.rect()
```

In `_geometric_snaps` full-circle branch replace `br = item.boundingRect()` with `br = item.rect()` (same comment, one line).

- [ ] **Step 4: Rewrite the coupled matrix class.** In `tests/test_snap_engine_matrix.py::TestFullCircle`:
  - Delete the docstring paragraph about `boundingRect()` padding.
  - Delete `BR_TOL`, and change every `tol=self.BR_TOL` to the default (`ABS_TOL`).
  - In `test_tangent`, move the cursor to `QPointF(153, 100)`. That puts d=53 against the true r=50, so the tangent distance is sqrt(53²−50²) ≈ 17.6, inside the 20 px aperture. Replace the comment block with that arithmetic, and assert `abs(dist - 50) < ABS_TOL`.

- [ ] **Step 5: Run guard + matrix + keep-green**

Run: `...python.exe -m pytest tests/test_snap_curve_accuracy.py tests/test_snap_engine_matrix.py tests/test_snap_engine_primitives.py tests/test_snap_engine_underlay_fallback.py tests/test_design_area_snap_routing.py tests/test_manip_griphandle_designarea_parity.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add firepro3d/snap_engine.py tests/test_snap_curve_accuracy.py tests/test_snap_engine_matrix.py
git commit -m "fix(snap): circle snaps read rect(), not the padded/zoom-cached boundingRect (S4)"
```

---

### Task 3: S4b — curve projection onto the true curve (flattened path); ArcItem no fall-through

**Files:**
- Modify: `firepro3d/snap_engine.py` `_geometric_snaps`
- Test: `tests/test_snap_curve_accuracy.py`

- [ ] **Step 1: Add failing guards** (append):

```python
def test_arc_outside_cursor_lands_on_arc(qapp):
    view, scene = make_view(scale=0.25)
    try:
        scene.addItem(ArcItem(QPointF(0, 0), R, 0.0, 180.0))
        off = 10.0 / 0.25
        ep = _drag_line_end_to(view, scene, QPointF((R + off) * math.cos(A45),
                                                   (R + off) * math.sin(A45)))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 0.01
    finally:
        close_view(view, scene)


def test_ellipse_outside_cursor_lands_on_curve(qapp):
    view, scene = make_view(scale=0.25)
    try:
        el = EllipseItem(QPointF(0, 0), R, R)    # rx == ry: distance from centre == R
        scene.addItem(el)
        off = 10.0 / 0.25
        ep = _drag_line_end_to(view, scene, QPointF((R + off) * math.cos(A45),
                                                   (R + off) * math.sin(A45)))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 1.0   # flatten tolerance
    finally:
        close_view(view, scene)
```

(VC4: before running, grep `class EllipseItem` → `def __init__` in `geometry_2d.py` and adapt the constructor call to the real signature.)

- [ ] **Step 2: Run, confirm RED.** Expected: arc and ellipse both off by ~48.8 mm.

- [ ] **Step 3: Implement.** In `_geometric_snaps`:
  - (a) Change `if isinstance(item, ArcItem):` to `elif isinstance(item, ArcItem):`, so it joins the line/wall/rect/polyline chain.
  - (b) Change the full-circle `if isinstance(item, QGraphicsEllipseItem) and not hasattr(item, "pipes"):` to `elif`.
  - (c) The chain is now a single `if/elif` from LineItem through generic path. Replace the generic path branch body with:

```python
        # ── Generic QGraphicsPathItem (EllipseItem, SplineItem, DXF curves) —
        #    project onto the FLATTENED path. Raw elements include Bézier
        #    control points that sit off the curve, which snapped to empty
        #    space outside arcs/ellipses/splines (S4).
        elif isinstance(item, QGraphicsPathItem) and not isinstance(
                item, (WallSegment, PolylineItem)):
            n_seg = 0
            for poly in item.path().toSubpathPolygons():
                for i in range(poly.count() - 1):
                    if n_seg >= 511:
                        break
                    _seg_snap(item.mapToScene(poly.at(i)),
                              item.mapToScene(poly.at(i + 1)))
                    n_seg += 1
```

- [ ] **Step 4: Run guard + keep-green**

Run: `...python.exe -m pytest tests/test_snap_curve_accuracy.py tests/test_snap_engine_matrix.py tests/test_ellipse_spline_snap.py tests/test_snap_nearest_perpendicular_decoupling.py tests/test_polygon_snap.py tests/test_manip_griphandle_arc_parity.py tests/test_manip_griphandle_ellipse_parity.py tests/test_manip_griphandle_spline_parity.py tests/test_arc_grip_reshape.py tests/test_snap_engine_case_studies.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** — `fix(snap): nearest/perpendicular project onto the true curve, not the Bézier control polygon (S4)`

---

### Task 4: S5 — ALIGN crossings beat cursor-foot snaps; one-picker seam

**Files:**
- Modify: `firepro3d/snap_engine.py` (`_SnapCtx`, `find` hysteresis)
- Modify: `firepro3d/model_space.py` `get_effective_position` (the two-tier block after the design_area branch)
- Test: `tests/test_snap_align_crossing_seam.py` (new)

- [ ] **Step 1: Write failing guards**

```python
"""S5 guard — ALIGN crossings win over cursor-foot snaps through the real seam."""
import math

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.wall import WallSegment
from tests._snap_polish_helpers import close_view, dwell, make_view, move


def _setup_b(qapp):
    view, scene = make_view(mode="draw_line")
    scene.addItem(LineItem(QPointF(-2000, 0), QPointF(0, 0)))
    scene.addItem(WallSegment(QPointF(1500, -300), QPointF(1500, 1700), thickness_mm=200.0))
    scene.addItem(RectangleItem(QPointF(3000, -300), QPointF(3800, 1700)))
    dwell(view, QPointF(0, 0))
    assert len(scene._align_controller.acquired) >= 1
    return view, scene


def test_ray_x_wall_face_wins_over_perpendicular(qapp):
    view, scene = _setup_b(qapp)
    try:
        move(view, QPointF(1412, 16))
        pt = scene.get_effective_position(QPointF(1412, 16))
        assert math.hypot(pt.x() - 1400, pt.y()) < 0.01
    finally:
        close_view(view, scene)


def test_ray_x_rect_edge_wins_over_perpendicular(qapp):
    view, scene = _setup_b(qapp)
    try:
        move(view, QPointF(3012, 12))
        pt = scene.get_effective_position(QPointF(3012, 12))
        assert math.hypot(pt.x() - 3000, pt.y()) < 0.01
    finally:
        close_view(view, scene)


def test_path_x_path_on_geometry_wins(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(-2000, 0), QPointF(0, 0)))
        scene.addItem(LineItem(QPointF(1000, 2000), QPointF(1000, 1000)))
        dwell(view, QPointF(0, 0))
        dwell(view, QPointF(1000, 1000))
        scene.addItem(LineItem(QPointF(0, -1000), QPointF(3000, 2000)))   # through (1000,0)
        move(view, QPointF(1012, 4))
        pt = scene.get_effective_position(QPointF(1012, 4))
        assert math.hypot(pt.x() - 1000, pt.y()) < 0.01
    finally:
        close_view(view, scene)


def test_real_endpoint_still_beats_crossing(qapp):
    view, scene = _setup_b(qapp)
    try:
        scene.addItem(LineItem(QPointF(1395, 5), QPointF(1395, 900)))   # endpoint 5 units off crossing
        move(view, QPointF(1398, 4))
        res = scene._snap_result
        assert res is not None and res.snap_type == "endpoint"
    finally:
        close_view(view, scene)
```

- [ ] **Step 2: Run and confirm RED.** The first three fail with a `perpendicular` foot; the last passes.

- [ ] **Step 3: Engine — the weak-foot dominance rule.** In `snap_engine.py`, add below `SNAP_PRIORITY`:

```python
# ALIGN candidate types (transient tracking; see align-placement.md).
ALIGN_SNAP_TYPES = frozenset({"align_intersection", "align_path"})
```

In `_SnapCtx`:
- add `"weak_types"` to `__slots__`;
- give `__init__` a `weak_types: frozenset = frozenset({"nearest", "perpendicular"})` kwarg, stored on `self.weak_types`;
- in `check`, after `prio = ...` and `band = ...`, insert:

```python
        # S5 (align-placement §3.1): an in-aperture ALIGN crossing beats a
        # cursor-foot ("weak") snap outright. The foot on the very segment a
        # ray crosses is by construction at least as close as the crossing, so
        # the band arithmetic below could never let the crossing win.
        inc = self.best_result.snap_type if self.best_result is not None else None
        if snap_type == "align_intersection" and inc in self.weak_types:
            self.best_dist_px = d_px
            self.best_prio = prio
            self.best_result = OsnapResult(
                point=pt, snap_type=snap_type, source_item=src_item,
                source_item2=src_item2, source_lines=source_lines, name=name)
            return
        if snap_type in self.weak_types and inc == "align_intersection":
            return
```

In `find`'s hold logic, directly after `if best is None: return held`, insert:

```python
        # S5: the weak-foot dominance applies across the hold too.
        if best.snap_type == "align_intersection" and held.snap_type in ctx.weak_types:
            return best
        if held.snap_type == "align_intersection" and best.snap_type in ctx.weak_types:
            return held
```

- [ ] **Step 4: Seam — one picker.** In `model_space.py`, find everything in `get_effective_position` from the comment `# SNAP takes highest priority` down to (but not including) `return self.get_snapped_position(scene_pos.x(), scene_pos.y())`, and replace it with:

```python
        # ONE picker (align-placement §1.1/§3): real SNAP and ALIGN candidates
        # are ranked in a single find() call. Real SNAP is gated by mode (select
        # only while grip-dragging); ALIGN by an armed placement. When only
        # ALIGN is live, the whitelist restricts the call to ALIGN types.
        from .snap_engine import ALIGN_SNAP_TYPES
        real_ok = (self._snap_enabled
                   and self.mode is not None
                   and (self.mode != "select" or self._grip_dragging))
        align_ok = self._align_enabled and self._align_active_item is not None
        _view = self._snap_view()
        rays = None
        if _view is not None and align_ok:
            self._align_controller.set_active_anchor(
                self._align_anchor_point(), self._align_anchor_direction())
            # Parallel guide anchoring: once a placement FROM-point exists it
            # anchors THERE; before the first point it falls back to the cursor.
            _anchor = self._mode_placement_anchor()
            parallel_origin = ((_anchor.x(), _anchor.y()) if _anchor is not None
                               else (scene_pos.x(), scene_pos.y()))
            rays = self._align_controller.build_rays(parallel_origin) or None
        if _view is None or not (real_ok or rays):
            self._snap_result = None
            self._align_result = None
            self._align_track_ray = None
            return self.get_snapped_position(scene_pos.x(), scene_pos.y())
        held = self._snap_result if self._snap_result is not None else self._align_result
        res = self._snap_engine.find(
            scene_pos, self, _view.transform(),
            exclude=self._grip_item if self._grip_dragging else None,
            only_types=None if real_ok else set(ALIGN_SNAP_TYPES),
            held=held, align_paths=rays,
            align_aperture_px=self._align_path_tol_px)
        if res is None:
            self._snap_result = None
            self._align_result = None
            self._align_track_ray = None
            return self.get_snapped_position(scene_pos.x(), scene_pos.y())
        if res.snap_type in ALIGN_SNAP_TYPES:
            self._snap_result = None
            self._align_result = res
            # Navigate (D4): a single-path soft-snap arms the ``track`` schema;
            # an align_intersection is a fixed crossing (no distance field).
            if res.snap_type == "align_path":
                self._arm_align_track(rays, res.point)
            else:
                self._align_track_ray = None
            return res.point
        self._snap_result = res
        self._align_result = None
        self._align_track_ray = None
        return res.point
```

(VC4: grep `_arm_align_track`, `_align_path_tol_px`, `_snap_view` in `model_space.py`, and confirm each exists before relying on it.)

- [ ] **Step 5: Run guards + keep-green**

Run: `...python.exe -m pytest tests/test_snap_align_crossing_seam.py tests/test_align_*.py tests/test_wall_align.py tests/test_gridline_alignment_snap.py tests/test_snap_priority_band.py tests/test_snap_hysteresis.py tests/test_snap_whitelist.py tests/test_design_area_snap_routing.py tests/test_snap_underlay_reroute.py tests/test_manip_griphandle_parity.py tests/test_placement_input_slice_parity.py -q`
Expected: PASS. If an ALIGN extension test regresses because the line's own foot steals the pick past its end, debug with `superpowers:systematic-debugging`. Do not loosen the test.

- [ ] **Step 6: Commit** — `fix(align): one-picker seam; ALIGN crossings beat cursor-foot snaps (S5)`

---

### Task 5: S1 — perpendicular-from-start (AutoCAD PER)

**Files:**
- Modify: `firepro3d/snap_engine.py` (`find(from_point=)`, `_SnapCtx.from_point`, `_geometric_snaps`, `_geometric_snaps_from_geom`, new helpers)
- Modify: `firepro3d/model_space.py` (`_snap_from_point`; pass `from_point=` in the Task-4 `find` call)
- Test: `tests/test_snap_perpendicular_from.py` (new)

- [ ] **Step 1: Write failing guards**

```python
"""S1 guard — with a placement start point, ⊥ is the foot FROM the start point."""
import math

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import click, close_view, make_view, move


def _perp_dot(a, b, t1, t2):
    ux, uy = b.x() - a.x(), b.y() - a.y()
    vx, vy = t2.x() - t1.x(), t2.y() - t1.y()
    return abs(ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))


def test_draw_line_end_snaps_perpendicular_from_start(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        t1, t2 = QPointF(0, 0), QPointF(1000, 1000)          # 45° target line
        scene.addItem(LineItem(t1, t2))
        start = QPointF(0, 800)
        click(view, start)
        foot = QPointF(400, 400)                             # foot of ⊥ from start
        cursor = QPointF(430, 430)                           # on the line, 30 mm off the foot (≈7.5 px)
        move(view, cursor)
        assert scene._snap_result is not None
        assert scene._snap_result.snap_type == "perpendicular"
        click(view, cursor)
        ln = [i for i in scene._draw_lines if i.grip_points()[0] == start][0]
        end = ln.grip_points()[2]
        assert math.hypot(end.x() - foot.x(), end.y() - foot.y()) < 0.01
        assert _perp_dot(start, end, t1, t2) < 1e-4
    finally:
        close_view(view, scene)


def test_no_start_point_perpendicular_is_cursor_foot(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(0, 0), QPointF(1000, 0)))
        move(view, QPointF(500, 12))
        r = scene._snap_result
        assert r is not None and r.snap_type == "perpendicular"
        assert math.hypot(r.point.x() - 500, r.point.y()) < 0.01
    finally:
        close_view(view, scene)
```

Add one real-path test each for **wall** (plan role, `mode="wall"`, line primitive), **pipe** (plan role, `mode="pipe"`), **floor polygon** (plan role, `mode="floor"`, `_set_floor_primitive("polygon")`) and **roof** (`mode="roof"`). Each follows the same pattern: first click at `start`, cursor near the ⊥ foot on a 45° `LineItem` target (a plan scene can host a `LineItem` via `addItem`), then assert `scene._snap_result.snap_type == "perpendicular"` and the result point equals the foot within 0.01. (VC4: read `test_floor_placement_workflow.py`, `test_wall_*` and the pipe placement tests for each mode's first-click contract before writing these.)

- [ ] **Step 2: Run, confirm RED.** The first test's snap is a cursor-foot `perpendicular` at the cursor's projection (≈(430,430)), not (400,400).

- [ ] **Step 3: Engine helpers.** Add to `SnapEngine`, next to `_project_to_segment`:

```python
    @staticmethod
    def _perp_foot_on_segment(pt: QPointF, seg_a: QPointF,
                              seg_b: QPointF) -> QPointF | None:
        """Foot of the perpendicular from *pt* onto segment a–b (AutoCAD PER).

        Unclamped: returns None when the foot falls outside the segment, when
        the segment is degenerate, or when *pt* lies on the line (PER undefined).
        """
        dx = seg_b.x() - seg_a.x()
        dy = seg_b.y() - seg_a.y()
        len_sq = dx * dx + dy * dy
        if len_sq < _EPS_DEGENERATE:
            return None
        t = ((pt.x() - seg_a.x()) * dx + (pt.y() - seg_a.y()) * dy) / len_sq
        if t < 0.0 or t > 1.0:
            return None
        foot = QPointF(seg_a.x() + t * dx, seg_a.y() + t * dy)
        if math.hypot(pt.x() - foot.x(), pt.y() - foot.y()) < _EPS_COINCIDENT:
            return None
        return foot

    def _foot_snaps(self, cursor: QPointF, p1: QPointF, p2: QPointF,
                    from_point: QPointF | None, pts: list) -> None:
        """Segment foot snaps: ``nearest`` = cursor foot; ``perpendicular`` =
        foot FROM *from_point* when a placement start exists (S1), else the
        legacy cursor foot."""
        foot = self._project_to_segment(cursor, p1, p2)
        if self.snap_perpendicular:
            if from_point is None:
                if foot is not None:
                    pts.append(("perpendicular", foot))
            else:
                per = self._perp_foot_on_segment(from_point, p1, p2)
                if per is not None:
                    pts.append(("perpendicular", per))
        if self.snap_nearest and foot is not None:
            pts.append(("nearest", foot))

    def _circle_foot_snaps(self, cursor: QPointF, center: QPointF, r: float,
                           from_point: QPointF | None, pts: list,
                           accept: "Callable[[QPointF], bool] | None" = None) -> None:
        """Circle/arc foot snaps. ⊥ from a start point = the two points where
        the line centre→start meets the circle (PER to a circle is radial)."""
        ok = accept or (lambda _q: True)
        d = math.hypot(cursor.x() - center.x(), cursor.y() - center.y())
        foot = None
        if d > _EPS_COINCIDENT:
            foot = QPointF(center.x() + r * (cursor.x() - center.x()) / d,
                           center.y() + r * (cursor.y() - center.y()) / d)
        if self.snap_perpendicular:
            if from_point is None:
                if foot is not None and ok(foot):
                    pts.append(("perpendicular", foot))
            else:
                df = math.hypot(from_point.x() - center.x(), from_point.y() - center.y())
                if df > _EPS_COINCIDENT:
                    ux = (from_point.x() - center.x()) / df
                    uy = (from_point.y() - center.y()) / df
                    for s in (1.0, -1.0):
                        q = QPointF(center.x() + s * r * ux, center.y() + s * r * uy)
                        if ok(q):
                            pts.append(("perpendicular", q))
        if self.snap_nearest and foot is not None and ok(foot):
            pts.append(("nearest", foot))
```

- [ ] **Step 4: Thread `from_point`.**
  - `find(...)` gains `from_point: QPointF | None = None`, documented in its Args as "placement start point: turns `perpendicular` into the foot from this point (S1); `None` keeps the cursor foot".
  - `_SnapCtx` gains a `"from_point"` slot. `find` builds `ctx = _SnapCtx(..., weak_types=frozenset({"nearest"}) if from_point is not None else frozenset({"nearest", "perpendicular"}))` and sets `ctx.from_point = from_point`.
  - Every `self._geometric_snaps(ctx.cursor, item)` call inside `_check_scene_items` becomes `self._geometric_snaps(ctx.cursor, item, ctx.from_point)`, and every `self._geometric_snaps_from_geom(ctx.cursor, g, xf, local_bounds)` becomes `(..., local_bounds, ctx.from_point)`. Grep both names and update every call site.
  - `_geometric_snaps(self, cursor, item, from_point=None)`: its inner `_seg_snap` becomes `def _seg_snap(p1, p2): self._foot_snaps(cursor, p1, p2, from_point, pts)`.
  - The ArcItem branch's perp/nearest block becomes `self._circle_foot_snaps(cursor, QPointF(cx, cy), r, from_point, pts, accept=lambda q: _angle_in_arc(math.degrees(math.atan2(-(q.y() - cy), q.x() - cx)), item._start_deg, item._span_deg))`. The tangent code stays.
  - The full-circle branch's perp/nearest block becomes `self._circle_foot_snaps(cursor, center, r, from_point, pts)`. The tangent code stays.
  - `_geometric_snaps_from_geom(..., from_point=None)`: its `_seg_snap` delegates to `_foot_snaps`, and the circle and arc blocks become `self._circle_foot_snaps(cursor, center, r, from_point, pts)`. Arc geom dicts keep today's no-angle-check behaviour.

- [ ] **Step 5: Seam.** Add to `Model_Space` (near `_mode_placement_anchor`):

```python
    # S1: modes whose ⊥ snap measures from the placement start point.
    _PER_FROM_MODES = ("draw_line", "polyline", "wall", "pipe", "floor", "roof")

    def _snap_from_point(self) -> "QPointF | None":
        """Start point for perpendicular-from (AutoCAD PER), or None."""
        if self.mode not in self._PER_FROM_MODES:
            return None
        if self.mode == "wall" and self._wall_primitive == "rect":
            return None
        if self.mode == "floor" and self._floor_primitive == "rect":
            return None
        if self.mode == "roof":
            ra = self._roof_active
            return QPointF(ra._points[-1]) if ra is not None and ra._points else None
        return self._mode_placement_anchor()
```

In the Task-4 `find(...)` call add `from_point=self._snap_from_point(),`.

- [ ] **Step 6: Run guards + keep-green**

Run: `...python.exe -m pytest tests/test_snap_perpendicular_from.py tests/test_snap_*.py tests/test_align_*.py tests/test_polygon_snap.py tests/test_ellipse_spline_snap.py tests/test_osnap_toolbar.py tests/test_osnap_ui.py -q`
Expected: PASS. `test_snap_nearest_perpendicular_decoupling.py` asserts PER+NEA co-emission with no start point, and that should still hold. If it constructs a start-point context, rewrite it and name it in the done report (VC5).

- [ ] **Step 7: Commit** — `feat(snap): perpendicular measured from the placement start point (AutoCAD PER) (S1)`

---

### Task 6: S6 — text emits box snap points; blocks drop glyph vertices and emit text box points

**Files:**
- Modify: `firepro3d/snap_engine.py` (`_check_scene_items` skip, `_collect` TextItem arm, BlockInstance arm)
- Modify: `firepro3d/block_definition.py` (`text_snap_points()` + cache invalidation)
- Test: `tests/test_snap_text_points.py` (new); keep `tests/test_block_s2_fixes.py` green

- [ ] **Step 1: Write failing guards**

```python
"""S6 guard — TextItem emits 9 box snap points; blocks emit text box points, not glyph vertices."""
import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPen

from tests._snap_polish_helpers import close_view, make_view


def _place_text(scene, a, b, text="HELLO", rotation=0.0):
    """Place via the real two-click path (_press_text) — VC4: read
    tests/test_text_two_click_placement.py for the exact call recipe."""
    ...  # copy the recipe from test_text_two_click_placement.py verbatim


def test_text_corner_snaps_as_endpoint(qapp):
    view, scene = make_view(mode="select")
    try:
        t = _place_text(scene, QPointF(1000, 1000), QPointF(1500, 1200))
        eng = scene._snap_engine
        kinds = sorted(k for k, _p, _n in eng._collect(t))
        assert kinds == sorted(["endpoint"] * 4 + ["midpoint"] * 4 + ["center"])
        g = t.grip_points()
        r = eng.find(QPointF(g[4].x() + 4, g[4].y() + 4), scene, view.transform())
        assert r is not None and r.snap_type == "endpoint"
        assert math.hypot(r.point.x() - g[4].x(), r.point.y() - g[4].y()) < 0.01
    finally:
        close_view(view, scene)


def test_rotated_text_corner_is_independently_rotated(qapp):
    view, scene = make_view(mode="select")
    try:
        t = _place_text(scene, QPointF(1000, 1000), QPointF(1500, 1200))
        # VC4: set rotation through the real setter (grep text_item.py for it).
        ...  # rotate 30°
        box = t._box_rect_local()
        c = t.mapToScene(box.center())
        # expected TL: rotate the unrotated TL (pos + local TL) about the centre by the
        # item's rotation in Qt convention — computed here, NOT read from grip_points().
        ...
        pts = [p for k, p, _n in scene._snap_engine._collect(t) if k == "endpoint"]
        assert any(math.hypot(p.x() - exp.x(), p.y() - exp.y()) < 0.01 for p in pts)
    finally:
        close_view(view, scene)


def test_block_with_text_emits_box_points_not_glyph_vertices(qapp):
    # VC4: copy the block-with-text recipe from tests/test_block_text_compile.py
    # (BlockDefinition with a line prim + a text prim, placed via place_block_instance).
    ...
    kinds = [k for k, _p, _n in eng._collect(inst)]
    assert kinds.count("endpoint") == 2 + 4        # line ends + text corners, 0 glyph vertices
    assert kinds.count("midpoint") == 4
    assert kinds.count("center") == 1 + 1          # insertion origin + text centre
```

The implementer fills the three `...` recipe blocks from the named existing tests. They are construction recipes only; the assertions above are fixed.

- [ ] **Step 2: Run, confirm RED.** `_collect(text)` returns `[]`, and the block's endpoint count includes the glyph vertices.

- [ ] **Step 3: Implement the TextItem arm.**
  - In `_check_scene_items` delete `_skip_types = (TextItem,)` and the `if isinstance(item, _skip_types): continue` pair.
  - In `_collect`, insert this as the second arm, right after the `LineItem` arm:

```python
        # ── TextItem — the frame box snaps like a rectangle (S6):
        #    corners = endpoint, edge mids = midpoint, centre = center.
        #    grip_points() order: TL,TM,TR,RM,BR,BM,BL,LM,C (rotation-aware).
        elif isinstance(item, TextItem):
            g = item.grip_points()
            if self.snap_endpoint:
                pts.extend(("endpoint", g[i], None) for i in (0, 2, 4, 6))
            if self.snap_midpoint:
                pts.extend(("midpoint", g[i], None) for i in (1, 3, 5, 7))
            if self.snap_center:
                pts.append(("center", g[8], None))
```

- [ ] **Step 4: Implement the block text box points.** In `block_definition.py`:
  - add `self._text_snap_pts = None` next to `self._render_ops = None` in `__init__`;
  - reset it wherever `_render_ops` is reset (grep `self._render_ops = None`);
  - add:

```python
    def text_snap_points(self) -> list[list[QPointF]]:
        """Origin-relative 9-point frame boxes (TL,TM,TR,RM,BR,BM,BL,LM,C) of
        every text primitive — the block's text snap targets (S6). Cached with
        the render ops; glyph outlines are never snap targets."""
        if self._text_snap_pts is None:
            ox, oy = self.origin
            out = []
            for prim in self.primitives:
                cls = _PRIMITIVE_FACTORY.get(prim.get("type"))
                if cls is None:
                    continue
                item = cls.from_dict(prim)
                if not hasattr(item, "render_outline_path"):
                    continue
                out.append([QPointF(p.x() - ox, p.y() - oy) for p in item.grip_points()])
            self._text_snap_pts = out
        return self._text_snap_pts
```

  In `snap_engine._collect`'s BlockInstance arm, inside `if self.snap_endpoint:`, make the loop skip text ops, and then add the box points:

```python
                for pen, _brush, path in item.render_ops():
                    if pen.style() == Qt.PenStyle.NoPen:
                        continue   # text op = filled glyph outline — never snap targets (S6)
                    ...existing element loop...
            _defn = item.definition()
            for box in (_defn.text_snap_points() if _defn is not None else []):
                g = [_pose.map(p) for p in box]
                if self.snap_endpoint:
                    pts.extend(("endpoint", g[i], None) for i in (0, 2, 4, 6))
                if self.snap_midpoint:
                    pts.extend(("midpoint", g[i], None) for i in (1, 3, 5, 7))
                if self.snap_center:
                    pts.append(("center", g[8], None))
```

(A reference-mode definition has no text prims in `primitives`, so its list is empty.)

- [ ] **Step 5: Run guards + keep-green**

Run: `...python.exe -m pytest tests/test_snap_text_points.py tests/test_block_s2_fixes.py tests/test_block_text_compile.py tests/test_text_item.py tests/test_text_two_click_placement.py tests/test_snap_engine_matrix.py tests/test_manip_griphandle_note_parity.py -q`
Expected: PASS.

- [ ] **Step 6: Commit** — `feat(snap): text emits frame-box snap points; blocks snap text boxes, not glyph vertices (S6)`

---

### Task 7: S3a — Ctrl angle-snap on polyline / floor / roof vertex grips

**Files:**
- Modify: `firepro3d/manip_handle.py` (new `vertex_chain_grip_handles`)
- Modify: `firepro3d/geometry_2d.py` `PolylineItem.manip_handles`; `firepro3d/floor_slab.py` and `firepro3d/roof.py` `manip_handles`
- Test: `tests/test_polyline_polygon_ctrl.py` (new); update `tests/test_manip_griphandle_polyline_parity.py` docstring

- [ ] **Step 1: Write failing guards** (plan role for floor; block_editor for polyline):

```python
"""S3a / Fold D guard — Ctrl angle-constrains polyline/polygon vertices."""
import math

from PyQt6.QtCore import QPointF, Qt

from firepro3d.geometry_2d import PolylineItem
from tests._snap_polish_helpers import close_view, drag, make_view

CTRL = Qt.KeyboardModifier.ControlModifier


def _angle(a, b):
    return math.degrees(math.atan2(-(b.y() - a.y()), b.x() - a.x())) % 180.0


def _on_increment(a_deg, step=45.0):
    r = a_deg % step
    return min(r, step - r) < 0.01


def _poly(scene, pts):
    pl = PolylineItem(QPointF(pts[0]))
    for p in pts[1:]:
        pl.add_point(QPointF(p))      # VC4: grep PolylineItem for its real append API
    pl.finalize()
    scene.addItem(pl)
    scene._polylines.append(pl)
    scene.clearSelection()
    pl.setSelected(True)
    return pl


def test_open_polyline_end_grip_ctrl_constrains_against_neighbour(qapp):
    view, scene = make_view()
    try:
        pl = _poly(scene, [(0, 0), (1000, 0)])
        drag(view, pl.grip_points()[1], QPointF(600, 400), mods=CTRL)   # raw 33.69°
        assert _on_increment(_angle(pl.grip_points()[0], pl.grip_points()[1]))
    finally:
        close_view(view, scene)


def test_open_polyline_start_grip_ctrl_constrains_against_next(qapp):
    view, scene = make_view()
    try:
        pl = _poly(scene, [(0, 0), (1000, 0), (1000, -1000)])
        drag(view, pl.grip_points()[0], QPointF(400, 300), mods=CTRL)
        a = _angle(pl.grip_points()[1], pl.grip_points()[0])
        assert _on_increment(a)
    finally:
        close_view(view, scene)


def test_interior_vertex_ctrl_constrains_against_previous(qapp):
    view, scene = make_view()
    try:
        pl = _poly(scene, [(0, 0), (1000, 0), (1000, -1000)])
        drag(view, pl.grip_points()[1], QPointF(600, 400), mods=CTRL)
        a = _angle(pl.grip_points()[0], pl.grip_points()[1])
        assert _on_increment(a)
    finally:
        close_view(view, scene)
```

Add a floor-slab test (plan role): build a closed 4-vertex `FloorSlab` via its real API (VC4: grep `floor_slab.py` for `add_point`/`close_polygon`), select it, then Ctrl-drag vertex 0 and assert that the angle from vertex n−1 is on a 45° increment. Add the same test for `RoofItem`.

All angle guards assert the on-increment property via `_on_increment()` (convention-free; VC3). Do NOT change `_constrain_angle`.

- [ ] **Step 2: Run, confirm RED** (33.69° remains unconstrained).

- [ ] **Step 3: Implement.** In `manip_handle.py`, after `default_grip_handles`:

```python
def vertex_chain_grip_handles(item, closed: bool,
                              circular: "frozenset[int] | set[int] | None" = None):
    """Vertex grips that Ctrl-angle-constrain against the PREVIOUS vertex (S3a).

    An open chain's first vertex constrains against the next one (it has no
    previous); a closed chain wraps (vertex 0 ↔ n−1). Reuses
    ``EndpointGripHandle`` — the anchor is re-read live from ``grip_points()``.
    """
    n = len(item.grip_points())
    fn = getattr(item, "grip_hittable", None)
    circ = set(range(n)) if circular is None else set(circular)
    out = []
    for i in range(n):
        if fn is not None and not fn(i):
            continue
        if n < 2:
            out.append(GripHandle(item, i, circular=(i in circ)))
            continue
        if i > 0:
            opp = i - 1
        else:
            opp = n - 1 if closed else 1
        out.append(EndpointGripHandle(item, i, opposite_index=opp,
                                      circular=(i in circ)))
    return out
```

`PolylineItem.manip_handles` returns `vertex_chain_grip_handles(self, closed=self.is_closed())`. Update its docstring: vertex grips Ctrl-constrain against the previous vertex, and an open start constrains against the next.

`FloorSlab.manip_handles` and `RoofItem.manip_handles` return `vertex_chain_grip_handles(self, closed=True)`. Replace their "Zero special semantics … no EndpointGripHandle" docstring sentences with the new contract. Keep the `manip_rotate` note.

- [ ] **Step 4: Update the stale docstring** at the top of `tests/test_manip_griphandle_polyline_parity.py` (line ~6, "no special drag semantics (no Ctrl-constrain …)") to "vertex grips Ctrl-constrain against the previous vertex (S3a)".

- [ ] **Step 5: Run guards + keep-green**

Run: `...python.exe -m pytest tests/test_polyline_polygon_ctrl.py tests/test_manip_griphandle_polyline_parity.py tests/test_manip_griphandle_line_parity.py tests/test_manip_griphandle_floor_parity.py tests/test_manip_griphandle_roof_parity.py tests/test_manip_griphandle_admissibility.py tests/test_manip_ctrl_resize.py tests/test_polyline_closed.py -q`
Expected: PASS.

- [ ] **Step 6: Commit** — `fix(grips): Ctrl angle-snap on polyline/floor/roof vertex grips (S3a)`

---

### Task 8: Fold D — Ctrl angle-snap during floor/roof polygon placement

**Files:**
- Modify: `firepro3d/model_space.py` — `_move_floor`, `_press_floor`, `_move_roof`, `_press_roof`
- Test: `tests/test_polyline_polygon_ctrl.py`

- [ ] **Step 1: Failing guard** (append). Plan role, `mode="floor"`, `scene._set_floor_primitive("polygon")`:
  - `click(view, QPointF(0, 0))`;
  - `move(view, QPointF(600, 400), mods=CTRL)`;
  - assert `scene.get_resolved_point()` is on a 45° increment from (0,0);
  - `click(view, QPointF(600, 400), mods=CTRL)`;
  - assert `scene._floor_active._points[1]` is on a 45° increment.

  Add the same test for roof (`mode="roof"`), stopping before the close (closing opens a modal dialog). (VC4: grep `get_resolved_point` and `_set_floor_primitive`.)

- [ ] **Step 2: RED** (33.69°).

- [ ] **Step 3: Implement.**
  - In `_move_floor`'s else-branch, after `last_pt = ...`, insert:

```python
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                snapped = self._constrain_angle(last_pt, snapped)
```

  - Insert the same three lines in `_move_roof`'s else-branch after `last_pt = ...`.
  - In `_press_floor`'s else-branch, insert at the top: `tip = snapped`, then `if event is not None and event.modifiers() & Qt.KeyboardModifier.ControlModifier: tip = self._constrain_angle(pts[-1], snapped)`. Keep the close-near-first test on the raw `snapped` (the polyline precedent), and change the final `self._floor_active.add_point(snapped)` to `add_point(tip)`.
  - Apply the identical change to `_press_roof`'s final `add_point` in its else-branch. (VC4: read the lines after the close block in `_press_roof` to find it.)

- [ ] **Step 4: Run guard + `tests/test_floor_placement_workflow.py` + roof placement tests** (no offscreen). Expected: PASS.

- [ ] **Step 5: Commit** — `feat(floor,roof): Ctrl angle-snap during polygon placement (Fold D)`

---

### Task 9: S3b — a 2-point polyline finish commits a LineItem

**Files:**
- Modify: `firepro3d/model_space.py` — new `_finish_polyline`; replace the finish blocks in the double-click handler and the Enter key handler
- Modify: `tests/test_dynamic_input_parity.py::…test_two_point_polyline_survives_the_finish` (VC5 rewrite)
- Test: `tests/test_polyline_two_point_finish.py` (new)

- [ ] **Step 1: Failing guards.** In a block_editor role scene, `set_mode("polyline")`, click (0,0), click (1000,0), then finish. Enter uses `QTest.keyClick(view, Qt.Key.Key_Return)` or posts a key event (VC4: copy the finish recipe from `test_dynamic_input_parity.py`'s double-click class and the Enter test). Assert:
  - `len(scene._polylines) == 0`;
  - one new `LineItem` in `scene._draw_lines` whose `grip_points()[0] == (0,0)` and `[2] == (1000,0)`;
  - it is selected;
  - `scene.mode == "select"`.

  Add a 3-point control that still yields a `PolylineItem`. Test both finish gestures.

- [ ] **Step 2: RED.**

- [ ] **Step 3: Implement.** Add to `Model_Space`:

```python
    def _finish_polyline(self) -> None:
        """Commit the in-progress polyline (Enter / double-click finish).

        A 2-vertex result commits as a ``LineItem`` (S3b) — a single segment
        IS a line. Built directly (not via ``_make_line_like``, whose draw_line
        "reference" variant could leak in). Colour + lineweight carry over; a
        polyline fill on an open 2-point path is meaningless and is dropped.
        """
        pl = self._polyline_active
        if pl is None or len(pl._points) < 2:
            return
        pl.finalize()
        self._polyline_active = None
        self._hide_polyline_close_indicator()
        self.clearSelection()  # only the just-placed item stays selected
        placed = pl
        if len(pl._points) == 2:
            placed = LineItem(QPointF(pl._points[0]), QPointF(pl._points[1]),
                              color=pl.pen().color().name(),
                              lineweight=getattr(pl, "_lineweight", pl.pen().widthF()))
            self.removeItem(pl)
            if pl in self._polylines:
                self._polylines.remove(pl)
            self.addItem(placed)
            self._draw_lines.append(placed)
        placed.setSelected(True)
        for v in self.views():
            v.viewport().update()
        self.push_undo_state()
        self.instructionChanged.emit("Pick first point")
        self._end_placement_switch(placed)
```

  - In the double-click handler, replace the `if len(pts) >= 2: pl = … self._end_placement_switch(pl)` block with `self._finish_polyline()`, keeping the `if len(pts) > 2: pts.pop()` line above it.
  - In the Enter handler, replace the `if len(self._polyline_active._points) >= 2: … self._end_placement_switch(pl)` block with `self._finish_polyline()`, keeping the trailing `# (single-placement…)` comment.
  - VC4: confirm `LineItem` is imported in `model_space.py`.

- [ ] **Step 4: Rewrite the coupled test** `test_two_point_polyline_survives_the_finish`. The 2-point double-click finish must now leave one `LineItem` in `_draw_lines`, no polyline in `_polylines`, and exactly one undo push. Name this rewrite in the done report.

- [ ] **Step 5: Run guard + keep-green**

Run: `...python.exe -m pytest tests/test_polyline_two_point_finish.py tests/test_dynamic_input_parity.py tests/test_dynamic_input_seam.py tests/test_geo2d_placement_selection.py tests/test_geometry_drawing_slice_parity.py tests/test_geo2d_ghost_preview.py tests/test_polyline_close_placement.py tests/test_geo2d_serialization.py tests/test_ribbon_contextual.py -q`
Expected: PASS.

- [ ] **Step 6: Commit** — `fix(polyline): a 2-point finish commits a Line (S3b); one shared finish helper`

---

### Task 10: Fold E — `last_point()` on PolylineItem / FloorSlab / RoofItem

**Files:**
- Modify: `firepro3d/geometry_2d.py`, `firepro3d/floor_slab.py`, `firepro3d/roof.py`, `firepro3d/geometry_drawing_controller.py` (3 sites), `firepro3d/placement_input_coordinator.py` (2 sites), `firepro3d/model_space.py` (floor/roof `last_pt` sites, including the Task-8 edits)

- [ ] **Step 1: Baseline** — run `tests/test_geometry_drawing_slice_parity.py tests/test_dynamic_input_parity.py tests/test_floor_placement_workflow.py tests/test_placement_input_slice_parity.py -q` and record the passes.

- [ ] **Step 2: Add** to each of the three classes:

```python
    def last_point(self) -> QPointF:
        """The most recently placed vertex (placement rubber-band anchor)."""
        return QPointF(self._points[-1])
```

- [ ] **Step 3: Replace** every `X._points[-1]` read, where X is a PolylineItem, FloorSlab or RoofItem, with `X.last_point()`. Re-grep `_points\[-1\]` over `firepro3d/` afterwards. The only allowed remainder is `_spline_points[-1]`, which is a different attribute.

- [ ] **Step 4: Re-run the baseline set.** Expected: the same passes.

- [ ] **Step 5: Commit** — `refactor: last_point() on polyline/floor/roof replaces _points[-1] reach-ins (Fold E)`

---

### Task 11: S2 — HandleSnapSession + manipulator interior-drag

**Files:**
- Create: `firepro3d/handle_snap.py`
- Modify: `firepro3d/constants.py` (`HANDLE_SNAP_MAX_HANDLES = 64`)
- Modify: `firepro3d/selection_manipulator.py` (`_begin`, `_update` move branch, drag end)
- Test: `tests/test_move_handle_snap.py` (new)

- [ ] **Step 1: Failing guards**

```python
"""S2 guard — moving items: their own snap points snap to other geometry."""
import math
import time

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import close_view, drag, make_view


def test_interior_drag_endpoint_snaps_while_cursor_far(qapp):
    view, scene = make_view(scale=1.0)
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        b = LineItem(QPointF(200, 10), QPointF(300, 10))
        scene.addItem(a); scene.addItem(b)
        scene.clearSelection(); a.setSelected(True)
        # grab at (25,0) (interior, not a grip); raw drop puts a.p2 at (198,8)
        drag(view, QPointF(25, 0), QPointF(123, 8))
        p2 = a.grip_points()[2]
        assert math.hypot(p2.x() - 200, p2.y() - 10) < 0.01
    finally:
        close_view(view, scene)


def test_handle_snap_move_cost_is_interactive(qapp):
    view, scene = make_view(scale=1.0)
    try:
        for i in range(2000):
            scene.addItem(LineItem(QPointF(i * 7.0, 500), QPointF(i * 7.0 + 5, 520)))
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(a); scene.clearSelection(); a.setSelected(True)
        from firepro3d.handle_snap import HandleSnapSession
        s = HandleSnapSession(scene._snap_engine, scene, view, [a], QPointF(25, 0))
        t0 = time.perf_counter()
        for k in range(50):
            s.best(QPointF(25 + k, 3))
        per_move_ms = (time.perf_counter() - t0) / 50 * 1000
        assert per_move_ms < 16.0
    finally:
        close_view(view, scene)
```

- [ ] **Step 2: RED.** The first test ends 2.83 units off; the second fails with `ImportError`.

- [ ] **Step 3: Create `firepro3d/handle_snap.py`:**

```python
"""Handle snap (S2): while a selection moves, its own snap points (endpoints,
midpoints, centres, quadrants, text-box points) snap to other geometry.

Targets are collected ONCE per gesture — the moving items are excluded and
nothing else changes during a drag — into a px-cell grid; each mouse move then
tests every handle against its neighbouring cells (O(handles)). Underlay
geometry is queried per handle through each group's spatial index. The model
scene is NoIndex, so a per-handle ``SnapEngine.find()`` (≈40–140 ms at
2k–8k items) is not viable. Governing spec: selection-manipulator.md §Move.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QGraphicsItemGroup

from . import snap_engine as _se
from .constants import HANDLE_SNAP_MAX_HANDLES
from .snap_engine import OsnapResult, SNAP_PRIORITY
from .underlay_snap_index import UnderlaySnapIndex

HANDLE_TYPES = frozenset({"endpoint", "midpoint", "center", "quadrant"})
_UNDERLAY_TAGS = ("DXF Underlay", "PDF Underlay")


class HandleSnapSession:
    """One move gesture's handle-snap state.

    Args:
        engine: The scene's ``SnapEngine`` (toggles + collectors).
        scene: The model scene.
        view: The view the drag happens in (zoom + visible rect).
        moving: Items being moved (excluded as targets, sources of handles).
        anchor: Scene point the handle offsets are measured from (the grab
            point / Move base point).
    """

    def __init__(self, engine, scene, view, moving, anchor: QPointF):
        self._engine = engine
        self._scale = _se._safe_scale(view.transform().m11())
        self._moving = set(moving)
        # Handles: offsets from the anchor, deduped, capped.
        seen, handles = set(), []
        for it in moving:
            for kind, p, _n in engine._collect(it):
                key = (round(p.x(), 6), round(p.y(), 6))
                if kind in HANDLE_TYPES and key not in seen:
                    seen.add(key)
                    handles.append(QPointF(p.x() - anchor.x(), p.y() - anchor.y()))
        self._handles = handles[:HANDLE_SNAP_MAX_HANDLES]
        # Targets: named points of non-moving items in the visible rect.
        self._cell = _se.px_to_scene(float(_se.SNAP_TOLERANCE_PX), self._scale)
        self._grid: dict[tuple[int, int], list[tuple[str, QPointF, object]]] = {}
        self._underlays = []
        visible = view.mapToScene(view.viewport().rect()).boundingRect()
        for item in scene.items(visible, Qt.ItemSelectionMode.IntersectsItemBoundingRect):
            if self._is_moving(item) or not item.isVisible():
                continue
            parent = item.parentItem()
            if (isinstance(item, QGraphicsItemGroup)
                    and item.data(0) in _UNDERLAY_TAGS):
                if isinstance(item.data(4), UnderlaySnapIndex):
                    self._underlays.append(item)
                continue
            if parent is not None and parent.data(0) in _UNDERLAY_TAGS:
                continue
            if item.zValue() > 150 or item.data(0) == "origin":
                continue
            for kind, p, _n in engine._collect(item):
                if kind in HANDLE_TYPES:
                    self._grid.setdefault(self._key(p), []).append((kind, p, item))

    def _is_moving(self, item) -> bool:
        p = item
        while p is not None:
            if p in self._moving:
                return True
            p = p.parentItem()
        return False

    def _key(self, p: QPointF) -> tuple[int, int]:
        c = self._cell or 1.0
        return (math.floor(p.x() / c), math.floor(p.y() / c))

    def best(self, anchor_now: QPointF):
        """Best (corrected_anchor, OsnapResult) for the anchor at *anchor_now*,
        or None when no handle is within the aperture of a target."""
        if not self._handles:
            return None
        aperture = float(_se.SNAP_TOLERANCE_PX)
        band = float(_se.SNAP_PRIORITY_BAND_PX)
        best = None   # (d_px, prio, handle, kind, target, src)
        for h in self._handles:
            q = QPointF(anchor_now.x() + h.x(), anchor_now.y() + h.y())
            kx, ky = self._key(q)
            cands = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cands.extend(self._grid.get((kx + dx, ky + dy), ()))
            cands.extend(self._underlay_targets(q))
            for kind, p, src in cands:
                d_px = math.hypot(p.x() - q.x(), p.y() - q.y()) * self._scale
                if d_px > aperture:
                    continue
                prio = SNAP_PRIORITY.get(kind, 6)
                if (best is None or d_px < best[0] - band
                        or (d_px < best[0] + band and prio < best[1])
                        or (d_px < best[0] and prio == best[1])):
                    best = (d_px, prio, h, kind, p, src)
        if best is None:
            return None
        _d, _pr, h, kind, p, src = best
        corrected = QPointF(p.x() - h.x(), p.y() - h.y())
        return corrected, OsnapResult(point=QPointF(p), snap_type=kind, source_item=src)

    def _underlay_targets(self, q: QPointF):
        out = []
        if not self._underlays:
            return out
        r = self._cell
        rect = QRectF(q.x() - r, q.y() - r, 2 * r, 2 * r)
        for group in self._underlays:
            xf = group.sceneTransform()
            inv, ok = xf.inverted()
            if not ok:
                continue
            lr = inv.mapRect(rect)
            bounds = (lr.x(), lr.y(), lr.x() + lr.width(), lr.y() + lr.height())
            for g in group.data(4).query(lr.x(), lr.y(), lr.width(), lr.height()):
                for kind, p, _n in self._engine._collect_from_geom(g, xf, bounds):
                    if kind in HANDLE_TYPES:
                        out.append((kind, p, group))
        return out
```

(VC4: confirm `_safe_scale`, `px_to_scene`, `SNAP_PRIORITY_BAND_PX`, `SNAP_TOLERANCE_PX` and `_collect_from_geom(g, xf, local_bounds)` exist with these signatures in `snap_engine.py`; `_safe_scale` is used by `_SnapCtx`.)

Add `HANDLE_SNAP_MAX_HANDLES = 64  # S2: handle-snap probes per move (selection-manipulator.md)` to `constants.py` next to `GRIP_OBJECT_LIMIT`.

- [ ] **Step 4: Wire the manipulator.**
  - In `SelectionManipulator._begin`, after `self._held_snap = None`, add `self._handle_snap = None`.
  - In `_update`'s move branch, replace `snapped = self._snap(scene_pos)` with:

```python
            snapped = self._snap(scene_pos)
            hs = self._handle_snap_session()
            hit = hs.best(scene_pos) if hs is not None else None
            if hit is not None:
                snapped, res = hit            # a handle landed on a target: wins (S2)
                self._held_snap = None
                sc = self.scene()
                if hasattr(sc, "_snap_result"):
                    sc._snap_result = res     # marker + trace at the target
```

  - Add the method:

```python
    def _handle_snap_session(self):
        """Lazily build the S2 HandleSnapSession for this move gesture."""
        if getattr(self, "_handle_snap", None) is None:
            sc = self.scene()
            view = self._view()
            engine = getattr(sc, "_snap_engine", None)
            if (engine is None or view is None
                    or not getattr(sc, "_snap_enabled", True) or not engine.enabled):
                return None
            from .handle_snap import HandleSnapSession
            self._handle_snap = HandleSnapSession(
                engine, sc, view, list(self._items), self._start_scene)
        return self._handle_snap
```

  - Wherever the manipulator ends or cancels a gesture (grep `self._held_snap = None` at the release/cancel site, ~L1166), also set `self._handle_snap = None` and `if hasattr(self.scene(), "_snap_result"): self.scene()._snap_result = None`.

- [ ] **Step 5: Run guards + keep-green**

Run: `...python.exe -m pytest tests/test_move_handle_snap.py tests/test_selection_manipulator.py tests/test_selection_manipulator_paper.py tests/test_manip_u2_parity.py tests/test_grip_object_limit.py tests/test_elev_manipulator_wiring.py tests/test_snap_hysteresis.py -q`
Expected: PASS. Paper has no `_snap_engine`, so `_handle_snap_session` returns None there.

- [ ] **Step 6: Commit** — `feat(move): moving items' own snap points snap to geometry (S2, manipulator drag)`

---

### Task 12: S2 — Move tool + LineItem midpoint grip

**Files:**
- Modify: `firepro3d/model_space.py` (`_press_paste_move`, `_move_paste_move`, `begin_move_from`)
- Modify: `firepro3d/manip_handle.py` (`GripHandle.on_drag` stores `self._raw_pt`; new `TranslateGripHandle`)
- Modify: `firepro3d/geometry_2d.py` `LineItem.manip_handles` (midpoint index 1 → `TranslateGripHandle`)
- Test: `tests/test_move_handle_snap.py`

- [ ] **Step 1: Failing guards** (append):
  - **Move tool:** select A. Enter move mode through the real path (VC4: grep how tests enter Move, e.g. `test_move_paste_ghost.py`). `click(view, QPointF(25,0))` sets the base, `move(view, QPointF(123,8))`, then `click(view, QPointF(123,8))`. Assert A's p2 == (200,10).
  - **Midpoint grip:** drag the grip at `a.grip_points()[1]` to (148,8). Assert A's p2 == (200,10).

- [ ] **Step 2: RED.**

- [ ] **Step 3: Move tool.** Add to `Model_Space`:

```python
    def _move_handle_snap(self, event, snapped: QPointF) -> QPointF:
        """S2: in Move (after the base point), let the selection's own snap
        points snap to geometry; the closest handle hit beats the cursor snap."""
        if self.mode != "move" or self.node_start_pos is None:
            return snapped
        hs = getattr(self, "_move_handle_session", None)
        if hs is None:
            return snapped
        raw = event.scenePos() if event is not None else snapped
        hit = hs.best(raw)
        if hit is None:
            return snapped
        corrected, res = hit
        self._snap_result = res
        return corrected
```

  - At the top of `_move_paste_move`, after the `node_start_pos is None` early return, add `snapped = self._move_handle_snap(event, snapped)`.
  - In `_press_paste_move`'s else-branch, first line: `snapped = self._move_handle_snap(event, snapped)`.
  - In `_press_paste_move`'s first branch (base point set), after `self._move_ghost_base = ...`, add:

```python
            if self.mode == "move":
                _v = self._snap_view()
                self._move_handle_session = (
                    HandleSnapSession(self._snap_engine, self, _v,
                                      list(self.selectedItems()), snapped)
                    if _v is not None and self._snap_enabled else None)
```

  - In `begin_move_from`, build the same session with anchor `base`.
  - Where the move completes (the else-branch end), clear `self._move_handle_session = None`. Also clear it in `set_mode` cleanup (grep `self._move_ghost = []` in set_mode/clear paths and add it beside that).
  - Import: `from .handle_snap import HandleSnapSession`.
  - VC4: check the event type passed to `_move_paste_move` / `_press_paste_move`, i.e. that `event.scenePos()` exists, by reading `_MOVE_DISPATCH` callers. If it's a view-level `QMouseEvent`, derive raw via the scene's stored raw cursor instead, and state which in the report.

- [ ] **Step 4: Midpoint grip.**
  - In `GripHandle.on_drag`, first line: `self._raw_pt = QPointF(scene_pos)`.
  - Add to `manip_handle.py`:

```python
class TranslateGripHandle(GripHandle):
    """A grip whose drag translates the whole item (LineItem midpoint). S2:
    the item's own snap points snap to geometry via a HandleSnapSession; the
    closest handle hit beats the grip's own cursor snap."""

    def on_press(self, m) -> None:
        super().on_press(m)
        self._hs = None
        sc = m.scene()
        engine = getattr(sc, "_snap_engine", None)
        view = m._view() if hasattr(m, "_view") else None
        if (engine is not None and view is not None
                and getattr(sc, "_snap_enabled", True) and engine.enabled):
            from .handle_snap import HandleSnapSession
            self._hs = HandleSnapSession(engine, sc, view, [self.item],
                                         self.item.grip_points()[self.index])

    def _transform_point(self, m, pt: QPointF, mods) -> QPointF:
        hs = getattr(self, "_hs", None)
        raw = getattr(self, "_raw_pt", None)
        if hs is None or raw is None:
            return pt
        hit = hs.best(raw)
        if hit is None:
            return pt
        corrected, res = hit
        sc = m.scene()
        if hasattr(sc, "_snap_result"):
            sc._snap_result = res
        return corrected
```

  - In `LineItem.manip_handles`, the midpoint handle (index 1) becomes `TranslateGripHandle(self, 1, circular=False)`. VC4: read the current construction and keep its `circular` value.

- [ ] **Step 5: Run guards + keep-green**

Run: `...python.exe -m pytest tests/test_move_handle_snap.py tests/test_move_paste_ghost.py tests/test_manip_griphandle_line_parity.py tests/test_manip_griphandle_parity.py tests/test_manip_griphandle_admissibility.py -q`
Expected: PASS.

- [ ] **Step 6: Commit** — `feat(move): Move tool + line midpoint grip snap the moving item's own points (S2)`

---

### Task 13: Fold A docstring + spec updates (governing docs)

**Files:**
- Modify: `firepro3d/model_view.py` — the drawForeground docstring (the "2. Grip handles … drawn in drawForeground" and "grip then paints over the marker centre" text)
- Modify specs:
  - `docs/specs/snapping-engine.md`:
    - §4 perpendicular row: PER from the start point when a placement start exists (S1), cursor foot otherwise;
    - §4 nearest row: drop the stale "buggy";
    - §5 matrix: circle correct; TextItem, BlockInstance, EllipseItem and SplineItem rows added; HatchItem dropped;
    - §5 note 6 / §12 item 6: arcs do emit tangents;
    - §6.1: phase-1 skip list — TextItem is no longer skipped;
    - §14.5: one-picker seam + weak-foot dominance.
  - `docs/specs/align-placement.md`:
    - §1.1/§3: one picker at the seam;
    - §3.1 ranking: an ALIGN crossing beats cursor-foot perpendicular/nearest, while real endpoint/midpoint/center/quadrant/intersection still win;
    - §4: marker claim corrected (no align glyph today);
    - fix the `_SNAP_PRIORITY` → `SNAP_PRIORITY` reference.
  - `docs/specs/selection-manipulator.md`:
    - PolylineItem handles row + U3 ledger line (vertex-chain Ctrl);
    - add PolylineItem/FloorSlab/RoofItem to the `EndpointGripHandle` reuse note;
    - Move: handle snap (`HandleSnapSession`, cap, targets once per gesture, Move tool + midpoint grip).
  - `docs/specs/wall-room-floor-system.md`:
    - make the ~L213 Ctrl grip paragraph a pointer to selection-manipulator (Rule A);
    - floor polygon placement gains Ctrl.
  - `docs/specs/2d-geometry.md`:
    - polyline placement: "a 2-vertex finish commits a LineItem", and fix "All stay in polyline mode" → returns to Select;
    - text snap points.
  - `docs/specs/block-system.md` ~L117: blocks snap the insertion origin, on-curve stroked vertices and text box points — never glyph outlines.

- [ ] **Step 1:** Edit each doc as listed above. One fact, one home: specs link each other rather than restating.
- [ ] **Step 2:** `git grep -n "_SNAP_PRIORITY\|boundingRect()" docs/specs/snapping-engine.md docs/specs/align-placement.md` → no stale claims remain.
- [ ] **Step 3: Commit** — `docs: snap-polish spec updates (S1–S6, folds A/D/E)`

---

### Task 14: Full suite (VC6)

- [ ] **Step 1:** Stop any background runs. Run the full suite once on the final tree, reading pytest's own exit code (not piped):
  `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" -m pytest tests -q -p no:cacheprovider`
- [ ] **Step 2:** Expect exit 0. Any failure is either fixed (if caused by this batch) or proved pre-existing at base `e940885` in a worktree (VC7), then filed.
