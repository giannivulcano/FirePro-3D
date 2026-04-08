# Snap Engine Roadmap Items 1 + 3 + 10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the wall-corner false-negative snap bug (§7.1) and the apparent hatch snap bug (§7.2), introduce `WallSegment` named-target marker variants (filled yellow square for face corners, filled green triangle for face midpoints), and ship two case-study regression tests as the first headless pytest tests in this repo.

**Architecture:** Three linked changes. (1) `WallSegment` gains a side-effect-free `snap_quad_points()` that returns the mitered/joined wall quad without the paint-state mutation that `mitered_quad()` performs. Both `_collect()` face-target emission and phase-4 segment extraction call it, so snap targets always match the visible wall geometry. (2) `OsnapResult` and `_collect()` carry an optional `name: str | None` field so specific named targets (e.g. `face-left-corner-A`) can be distinguished from generic ones; the renderer inspects this name to draw filled glyphs for targets whose name starts with `face-`. (3) The picker gains an **endpoint protection band**: intersection candidates within ~6 px of any in-tolerance endpoint candidate are suppressed before they can steal priority. Combined with the *already-present* same-parent intersection filter (line 312, documented but not changed), these two rails eliminate the wall-corner false negative.

**Tech Stack:** Python 3.x, PyQt6, `QGraphicsScene` (headless-capable), pytest (new — bootstrapped by this plan).

---

## Important pre-reading for the implementer

Before starting, read these regions once so later tasks make sense:

- `firepro3d/snap_engine.py` lines 47–118 (constants, `OsnapResult`, `_SnapCtx.check`)
- `firepro3d/snap_engine.py` lines 258–328 (`_check_geometry_intersections`, phase 4)
- `firepro3d/snap_engine.py` lines 400–431 (`_collect` WallSegment branch)
- `firepro3d/snap_engine.py` lines 583–594 (`_geometric_snaps` WallSegment branch)
- `firepro3d/wall.py` lines 210–239 (`quad_points`)
- `firepro3d/wall.py` lines 858–956 (`mitered_quad`, `_intersect_lines`, `_resolve_join_mode`)
- `firepro3d/model_view.py` lines 145–317 (`drawForeground` marker pass)
- `docs/specs/snapping-engine.md` §6.3, §7.1, §7.2, §8

Finding to keep in mind: `_check_geometry_intersections` already contains `if src1 is src2: continue` at line 312. The §7.1 bug is therefore **not** caused by a same-wall face×face crossing slipping through; it is caused by a *cross-parent* face×face crossing inside the mitered corner region of two joined walls. That is why Task 4 (mitered phase-4 segments) is load-bearing: once both walls use their mitered quads for phase-4, the face crossings at the joint collapse onto the shared mitered corner and no longer steal priority from the endpoint candidate.

---

## File structure

**Create:**
- `tests/__init__.py` — empty, marks tests as a package.
- `tests/conftest.py` — module-level `QApplication` fixture so tests can instantiate a `QGraphicsScene`.
- `tests/test_snap_engine_case_studies.py` — two regression tests for §7.1 and §7.2.
- `docs/superpowers/plans/2026-04-07-snap-engine-items-1-3-10.md` — this file.

**Modify:**
- `firepro3d/wall.py` — add `snap_quad_points()` and a shared private helper `_compute_mitered_quad()`; refactor `mitered_quad()` to delegate.
- `firepro3d/snap_engine.py` — extend `OsnapResult`, `_SnapCtx.check`, `_collect()` and `_line_snaps()` signatures to carry `name`; update WallSegment branches in both `_collect` and `_check_geometry_intersections`; add the endpoint protection band in `_check_geometry_intersections`; add legend comment block above `SNAP_COLORS`/`SNAP_MARKERS`.
- `firepro3d/model_view.py` — marker pass in `drawForeground()` picks filled vs outlined brush based on `snap_result.name`.
- `docs/specs/snapping-engine.md` — amend §8.2 (invert filled/outlined convention), add T-joint deferral note in §8, mark roadmap items 1/3/10 done in §12.
- `TODO.md` — check off items 1, 3, 10 from the snap roadmap.

**No changes to:** `_geometric_snaps` internal logic (only the tuple shape of its return value is kept identical since it never emits named targets).

---

## Task 0: Create feature branch and verify clean state

**Files:**
- None (branch setup only).

- [ ] **Step 1: Verify clean working tree**

```bash
git status
```
Expected: No uncommitted changes to tracked files (untracked worktree / docs files may exist).

- [ ] **Step 2: Create and switch to feature branch**

```bash
git checkout -b feature/snap-items-1-3-10
```
Expected: `Switched to a new branch 'feature/snap-items-1-3-10'`.

- [ ] **Step 3: Verify Python + PyQt6 importable**

```bash
source venv/Scripts/activate && python -c "from PyQt6.QtWidgets import QGraphicsScene, QApplication; print('ok')"
```
Expected: `ok`

---

## Task 1: Add side-effect-free `snap_quad_points()` to `WallSegment`

**Goal:** Expose the mitered wall quad geometry without mutating `self._solid_pt1` / `self._solid_pt2` (which `mitered_quad()` does as a paint coordination side effect). Refactor so both `mitered_quad()` and the new `snap_quad_points()` share one pure computation.

**Files:**
- Modify: `firepro3d/wall.py` (around lines 890–956)

- [ ] **Step 1: Read `mitered_quad()` end-to-end**

Open `firepro3d/wall.py` lines 890–956 and confirm the side effects are exactly `self._solid_pt1 = True` / `self._solid_pt2 = True` (nothing else). If anything else mutates `self`, stop and flag the plan.

- [ ] **Step 2: Extract the pure helper**

Replace the body of `mitered_quad()` with a call to a new private static-logic helper. Final shape:

```python
def mitered_quad(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
    """Return quad_points adjusted for per-endpoint join modes.

    Also sets ``_solid_pt1`` / ``_solid_pt2`` flags indicating which
    endpoints use Solid mode (so paint() can skip drawing the end edge).
    """
    quad, solid_pt1, solid_pt2 = self._compute_mitered_quad()
    self._solid_pt1 = solid_pt1
    self._solid_pt2 = solid_pt2
    return quad

def snap_quad_points(self) -> tuple[QPointF, QPointF, QPointF, QPointF]:
    """Return the mitered/joined wall quad without any state mutation.

    Identical geometry to ``mitered_quad()`` but safe to call from the
    snap engine (which must not touch paint coordination state).
    """
    quad, _solid_pt1, _solid_pt2 = self._compute_mitered_quad()
    return quad

def _compute_mitered_quad(
    self,
) -> tuple[tuple[QPointF, QPointF, QPointF, QPointF], bool, bool]:
    """Pure computation shared by mitered_quad() and snap_quad_points().

    Returns ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2). Does NOT
    read or write ``self._solid_pt1`` / ``self._solid_pt2``.
    """
    p1l, p1r, p2r, p2l = self.quad_points()
    solid_pt1 = False
    solid_pt2 = False

    sc = self.scene()
    if sc is None or not hasattr(sc, '_walls'):
        return ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2)

    MITER_TOL = 1.0
    MAX_MITER = self.half_thickness_scene() * 4

    for my_idx in (0, 1):
        my_pt = self._pt1 if my_idx == 0 else self._pt2

        partners = []
        for other in sc._walls:
            if other is self:
                continue
            other_ep = other.endpoint_near(my_pt, MITER_TOL)
            if other_ep is not None:
                partners.append((other, other_ep))

        mode = self._resolve_join_mode(my_idx, 1 + len(partners))

        if mode == "Butt" or not partners:
            continue

        other, other_ep = partners[0]
        o_p1l, o_p1r, o_p2r, o_p2l = other.quad_points()

        cross = (my_idx == other_ep)
        if cross:
            left_target = (o_p1r, o_p2r)
            right_target = (o_p1l, o_p2l)
        else:
            left_target = (o_p1l, o_p2l)
            right_target = (o_p1r, o_p2r)

        int_l = self._intersect_lines(p1l, p2l,
                                      left_target[0], left_target[1])
        int_r = self._intersect_lines(p1r, p2r,
                                      right_target[0], right_target[1])

        if int_l is not None and int_r is not None:
            dist_l = math.hypot(int_l.x() - my_pt.x(),
                                int_l.y() - my_pt.y())
            dist_r = math.hypot(int_r.x() - my_pt.x(),
                                int_r.y() - my_pt.y())
            if dist_l < MAX_MITER and dist_r < MAX_MITER:
                if my_idx == 0:
                    p1l, p1r = int_l, int_r
                    if mode == "Solid":
                        solid_pt1 = True
                else:
                    p2l, p2r = int_l, int_r
                    if mode == "Solid":
                        solid_pt2 = True

    return ((p1l, p1r, p2r, p2l), solid_pt1, solid_pt2)
```

(`_intersect_lines` is an existing static method at line 861; `_resolve_join_mode` at 874; `quad_points` at 210; `endpoint_near` at 960. No further imports required.)

- [ ] **Step 3: Quick smoke — app still launches and paints walls**

```bash
python main.py
```
Expected: application window opens, a test project with walls renders without exception. Close the window. (We have not touched snap behavior yet, so this only validates the refactor preserved paint behavior.)

- [ ] **Step 4: Commit**

```bash
git add firepro3d/wall.py
git commit -m "refactor(wall): extract side-effect-free snap_quad_points from mitered_quad"
```

---

## Task 2: Extend `OsnapResult` and `_SnapCtx.check` with an optional `name` field

**Files:**
- Modify: `firepro3d/snap_engine.py` (lines 86–118)

- [ ] **Step 1: Add `name` to `OsnapResult`**

Replace the dataclass definition at lines 86–92 with:

```python
@dataclass
class OsnapResult:
    """A single snap point found by the engine."""
    point:       QPointF
    snap_type:   str                               # key from SNAP_COLORS
    source_item:  QGraphicsItem | None = field(default=None, repr=False)
    source_item2: QGraphicsItem | None = field(default=None, repr=False)
    name:         str | None = None
    """Optional semantic name for this candidate.

    Used for named/semantic targets on complex objects (e.g. a
    WallSegment emits ``centerline-end-A``, ``face-left-corner-A``,
    ``face-right-mid`` etc.).  Targets whose name starts with ``face-``
    are rendered with a *filled* marker glyph by the foreground pass
    in ``model_view.drawForeground``; all other targets (including
    ``name=None``) keep today's outlined rendering.
    """
```

- [ ] **Step 2: Thread `name` through `_SnapCtx.check`**

Replace the `check` method at lines 108–117 with:

```python
def check(self, snap_type: str, pt: QPointF, src_item: QGraphicsItem,
          name: str | None = None):
    """Compare a candidate snap against the current best."""
    d = math.hypot(pt.x() - self.cursor.x(), pt.y() - self.cursor.y())
    prio = SNAP_PRIORITY.get(snap_type, 6)
    if (d < self.best_dist - self.priority_band or
            (d < self.best_dist + self.priority_band and prio < self.best_prio)):
        self.best_dist = d
        self.best_prio = prio
        self.best_result = OsnapResult(
            point=pt, snap_type=snap_type,
            source_item=src_item, name=name,
        )
```

- [ ] **Step 3: Syntax check**

```bash
python -c "from firepro3d.snap_engine import OsnapResult, _SnapCtx; print(OsnapResult(point=None, snap_type='endpoint').name)"
```
Expected: `None` (or a TypeError if `point=None` is rejected — if so, pass `QPointF()` instead; the goal is only to prove the module imports cleanly and the new field defaults to `None`).

- [ ] **Step 4: Commit**

```bash
git add firepro3d/snap_engine.py
git commit -m "feat(snap): add optional name field to OsnapResult for named targets"
```

---

## Task 3: Convert `_collect()` to return triples and propagate through all call sites

**Goal:** `_collect()` now returns `list[tuple[str, QPointF, str | None]]`. Every non-wall branch emits `name=None`; the WallSegment branch emits actual names. All call sites unpack three.

**Files:**
- Modify: `firepro3d/snap_engine.py` (`_collect` lines 332–499, `_line_snaps` 501–513, call sites 218, 222, 253)

- [ ] **Step 1: Update `_line_snaps()`**

Replace lines 501–513 with:

```python
def _line_snaps(
    self, item: QGraphicsLineItem,
) -> list[tuple[str, QPointF, str | None]]:
    """Endpoint + midpoint snaps for a QGraphicsLineItem."""
    line = item.line()
    p1  = item.mapToScene(line.p1())
    p2  = item.mapToScene(line.p2())
    pts: list[tuple[str, QPointF, str | None]] = []
    if self.snap_endpoint:
        pts.append(("endpoint", p1, None))
        pts.append(("endpoint", p2, None))
    if self.snap_midpoint:
        mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        pts.append(("midpoint", mid, None))
    return pts
```

- [ ] **Step 2: Update `_collect()` signature and every `pts.append`**

Change the function signature at line 332 to:

```python
def _collect(
    self, item: QGraphicsItem,
) -> list[tuple[str, QPointF, str | None]]:
    """Return (snap_type, scene_pos, name) triples for one item.

    ``name`` is ``None`` for all item types except ``WallSegment``,
    which emits semantic names (centerline-end-A, face-left-corner-A,
    face-right-mid, etc.) so the foreground renderer can pick filled
    vs outlined glyph variants.
    """
    pts: list[tuple[str, QPointF, str | None]] = []
```

Then convert **every** `pts.append((snap_type, pt))` in non-wall branches to `pts.append((snap_type, pt, None))`. The branches to update (each is a simple 2-tuple → 3-tuple change, do them one by one):

- `ConstructionLine` (lines 344–352): endpoint pt1, endpoint pt2, midpoint.
- `RectangleItem` (lines 377–384): 4 corners, 4 edge mids, 1 center.
- `QGraphicsEllipseItem` (lines 391–398): center + 4 quadrants.
- `PolylineItem` (lines 437–445): all vertices, all segment mids.
- `ArcItem` (lines 455–497): start/end endpoints, center, midpoint, quadrants (whatever is there). Read the block and convert every `pts.append` line.
- Any other branch in `_collect()` between the `WallSegment` branch and the end.

(The `WallSegment` branch will be **replaced** in Task 4; for now, update its two centerline `pts.append` calls to trailing `None` so the module stays parseable. Task 4 overwrites them.)

- [ ] **Step 3: Update call sites in `_check_scene_items` and `_check_gridline_snaps`**

At `snap_engine.py` line 218, replace:
```python
                    for snap_type, scene_pt in self._collect(child):
                        ctx.check(snap_type, scene_pt, child)
```
with:
```python
                    for snap_type, scene_pt, name in self._collect(child):
                        ctx.check(snap_type, scene_pt, child, name)
```

At line 222, replace:
```python
            for snap_type, pt in self._collect(item):
                ctx.check(snap_type, pt, item)
```
with:
```python
            for snap_type, pt, name in self._collect(item):
                ctx.check(snap_type, pt, item, name)
```

At line 253, replace:
```python
            for snap_type, pt in self._collect(gl):
                ctx.check(snap_type, pt, gl)
```
with:
```python
            for snap_type, pt, name in self._collect(gl):
                ctx.check(snap_type, pt, gl, name)
```

(`_geometric_snaps` still returns 2-tuples and is NOT changed; its call sites remain at 2-tuple unpack.)

- [ ] **Step 4: Syntax + smoke launch**

```bash
python -c "from firepro3d.snap_engine import SnapEngine; print('ok')"
python main.py
```
Expected: module imports cleanly; app launches; snapping still works (hover over existing geometry, markers still draw). Close the app.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/snap_engine.py
git commit -m "refactor(snap): _collect returns (type, pt, name) triples; name=None for non-wall items"
```

---

## Task 4: WallSegment `_collect` branch emits named centerline + face targets

**Files:**
- Modify: `firepro3d/snap_engine.py` (WallSegment branch in `_collect`, lines 400–431)

- [ ] **Step 1: Replace the WallSegment branch in `_collect()`**

Replace the entire block at lines 400–431 with:

```python
        # ── WallSegment (must come before generic QGraphicsPathItem) ─────
        elif isinstance(item, WallSegment):
            p1, p2 = item.pt1, item.pt2

            # Centerline endpoints (named, but rendered OUTLINED — default glyph)
            if self.snap_endpoint:
                pts.append(("endpoint", p1, "centerline-end-A"))
                pts.append(("endpoint", p2, "centerline-end-B"))

            # Centerline midpoint
            if self.snap_midpoint:
                mid_c = QPointF((p1.x() + p2.x()) / 2,
                                (p1.y() + p2.y()) / 2)
                pts.append(("midpoint", mid_c, "centerline-mid"))

            # Face targets use mitered geometry so they land on the
            # visible wall corners, not the raw unmitered quad. Use the
            # side-effect-free snap_quad_points() (wall.py) — NOT
            # mitered_quad(), which writes paint coordination state.
            try:
                p1l, p1r, p2r, p2l = item.snap_quad_points()
            except Exception:
                p1l = p1r = p2r = p2l = None

            if p1l is not None and self.snap_endpoint:
                # Defensive rail: if a face corner is within ~3 screen
                # pixels of the centerline end at the current zoom, the
                # user cannot visually distinguish them — suppress the
                # face-corner candidate so the marker doesn't flicker.
                # Threshold in scene units = ``tol * (3/40)`` ≈ 0.075*tol,
                # but we don't have tol here; instead we use a small
                # absolute fraction of half-thickness: if half-thickness
                # in scene units is below ``_FACE_COLLAPSE_SCENE_EPS``
                # the face corners collapse onto the centerline and we
                # drop them entirely.
                try:
                    ht = item.half_thickness_scene()
                except Exception:
                    ht = 0.0
                _face_corners = [
                    ("face-left-corner-A",  p1l),
                    ("face-right-corner-A", p1r),
                    ("face-left-corner-B",  p2l),
                    ("face-right-corner-B", p2r),
                ]
                if ht >= _FACE_COLLAPSE_SCENE_EPS:
                    for name, pt in _face_corners:
                        pts.append(("endpoint", pt, name))
                # else: the wall is visually a line at any reasonable
                # zoom — skip face-corner emission; centerline endpoints
                # above are the only endpoints the user can see.

            if p1l is not None and self.snap_midpoint:
                try:
                    ht = item.half_thickness_scene()
                except Exception:
                    ht = 0.0
                if ht >= _FACE_COLLAPSE_SCENE_EPS:
                    left_mid = QPointF(
                        (p1l.x() + p2l.x()) / 2, (p1l.y() + p2l.y()) / 2)
                    right_mid = QPointF(
                        (p1r.x() + p2r.x()) / 2, (p1r.y() + p2r.y()) / 2)
                    pts.append(("midpoint", left_mid,  "face-left-mid"))
                    pts.append(("midpoint", right_mid, "face-right-mid"))
```

- [ ] **Step 2: Add the `_FACE_COLLAPSE_SCENE_EPS` constant**

Immediately after `SNAP_TOLERANCE_PX = 40` at the top of the file (around line 45), add:

```python
# Below this half-thickness (in scene units) a WallSegment is too thin
# for the user to visually distinguish its face corners from the
# centerline endpoint. We suppress named face-corner / face-mid
# candidates in that regime so the marker glyph doesn't flicker.
# The value matches half of a physical 6 mm wall in the default scale
# (practical floor for real FirePro3D drawings); drawings that use a
# finer scale will almost always have thicker walls.
_FACE_COLLAPSE_SCENE_EPS: float = 3.0
```

- [ ] **Step 3: Update `_geometric_snaps` WallSegment branch to use mitered geometry**

At lines 583–593, replace:

```python
        # ── WallSegment — project onto centerline and face edges ──────────
        elif isinstance(item, WallSegment):
            _seg_snap(item.pt1, item.pt2)  # centerline
            try:
                p1l, p1r, p2r, p2l = item.quad_points()
                _seg_snap(p1l, p2l)  # left face edge
                _seg_snap(p1r, p2r)  # right face edge
                _seg_snap(p1l, p1r)  # start cap
                _seg_snap(p2l, p2r)  # end cap
            except Exception:
                pass
```

with:

```python
        # ── WallSegment — project onto centerline and face edges ──────────
        elif isinstance(item, WallSegment):
            _seg_snap(item.pt1, item.pt2)  # centerline
            try:
                p1l, p1r, p2r, p2l = item.snap_quad_points()
                _seg_snap(p1l, p2l)  # left face edge (mitered)
                _seg_snap(p1r, p2r)  # right face edge (mitered)
                _seg_snap(p1l, p1r)  # start cap
                _seg_snap(p2l, p2r)  # end cap
            except Exception:
                pass
```

- [ ] **Step 4: Update phase-4 WallSegment segment extraction to use mitered geometry**

At lines 299–305, replace:

```python
            elif isinstance(item, WallSegment):
                try:
                    p1l, p1r, p2r, p2l = item.quad_points()
                    _segments.append((p1l, p2l, item))
                    _segments.append((p1r, p2r, item))
                except (ValueError, AttributeError):
                    pass
```

with:

```python
            elif isinstance(item, WallSegment):
                # Use mitered geometry so joined walls share clean corners
                # instead of crossing each other inside the joint — the
                # root cause of the §7.1 wall-corner false negative.
                try:
                    p1l, p1r, p2r, p2l = item.snap_quad_points()
                    _segments.append((p1l, p2l, item))
                    _segments.append((p1r, p2r, item))
                except (ValueError, AttributeError):
                    pass
```

- [ ] **Step 5: Smoke launch**

```bash
python main.py
```
Expected: app launches, walls render, hover-to-snap still works. Close.

- [ ] **Step 6: Commit**

```bash
git add firepro3d/snap_engine.py
git commit -m "feat(snap): WallSegment emits named centerline/face targets using mitered geometry"
```

---

## Task 5: Endpoint protection band (Change B) in phase-4 intersection scan

**Goal:** Before the phase-4 double loop emits an intersection candidate, check whether it lies within `protection_radius ≈ tol × 0.15` (≈ 6 px at the default 40 px tolerance) of *any* in-tolerance endpoint candidate already collected in phase 1. If yes, drop it.

**Files:**
- Modify: `firepro3d/snap_engine.py` (`_check_geometry_intersections` around lines 258–328)

- [ ] **Step 1: Collect endpoint candidates in phase 1 for the protection check**

We need a list of in-tolerance endpoint candidates (scene points) visible to phase 4. Extend `_SnapCtx` with a running list.

Replace `_SnapCtx.__slots__` + `__init__` at lines 97–106 with:

```python
class _SnapCtx:
    """Mutable snap-tracking context passed between find() phases."""
    __slots__ = ("cursor", "tol", "priority_band",
                 "best_dist", "best_prio", "best_result",
                 "endpoint_candidates")

    def __init__(self, cursor: QPointF, tol: float, priority_band: float):
        self.cursor = cursor
        self.tol = tol
        self.priority_band = priority_band
        self.best_dist: float = tol
        self.best_prio: int = 999
        self.best_result: OsnapResult | None = None
        # Scene-coord points of in-tolerance endpoint candidates seen so
        # far. Phase 4 uses this to suppress intersection candidates
        # that land inside the endpoint protection band (§6.3 Change B).
        self.endpoint_candidates: list[QPointF] = []
```

Then inside `_SnapCtx.check`, after the distance is computed, record endpoints:

```python
def check(self, snap_type: str, pt: QPointF, src_item: QGraphicsItem,
          name: str | None = None):
    """Compare a candidate snap against the current best."""
    d = math.hypot(pt.x() - self.cursor.x(), pt.y() - self.cursor.y())
    if snap_type == "endpoint" and d <= self.tol:
        self.endpoint_candidates.append(pt)
    prio = SNAP_PRIORITY.get(snap_type, 6)
    if (d < self.best_dist - self.priority_band or
            (d < self.best_dist + self.priority_band and prio < self.best_prio)):
        self.best_dist = d
        self.best_prio = prio
        self.best_result = OsnapResult(
            point=pt, snap_type=snap_type,
            source_item=src_item, name=name,
        )
```

- [ ] **Step 2: Suppress protected intersections in phase 4**

In `_check_geometry_intersections`, immediately before the segment–segment double loop at line 310, compute the protection radius:

```python
        # Endpoint protection band — §6.3 Change B. Intersection
        # candidates within this radius of any in-tolerance endpoint
        # candidate are suppressed before reaching the picker, so a
        # high-priority intersection can never silently displace an
        # endpoint at (for example) a mitered wall corner.
        protection_r = ctx.tol * 0.15
        protection_r_sq = protection_r * protection_r
        endpoints = list(ctx.endpoint_candidates)

        def _protected(ix: QPointF) -> bool:
            for ep in endpoints:
                ex = ix.x() - ep.x()
                ey = ix.y() - ep.y()
                if ex * ex + ey * ey <= protection_r_sq:
                    return True
            return False
```

Then wrap the two `ctx.check("intersection", ix, src1)` / `ctx.check("intersection", ix, src)` calls so they skip protected intersections:

```python
        # Segment–segment intersections
        for i, (sa1, sa2, src1) in enumerate(_segments):
            for sb1, sb2, src2 in _segments[i + 1:]:
                if src1 is src2:
                    # Same-parent intersection filter — §6.3 Change A,
                    # already present in the original implementation.
                    # Dropped candidates are wall-internal face×face
                    # crossings, rectangle edge self-crossings, etc.
                    continue
                ix = self._line_line_intersect(sa1, sa2, sb1, sb2)
                if ix is not None:
                    d = math.hypot(ix.x() - ctx.cursor.x(),
                                   ix.y() - ctx.cursor.y())
                    if d <= ctx.tol and not _protected(ix):
                        ctx.check("intersection", ix, src1)

        # Segment–circle intersections
        for center, radius, c_item in _circles:
            for sa1, sa2, src in _segments:
                for ix in self._line_circle_intersect(sa1, sa2, center, radius):
                    d = math.hypot(ix.x() - ctx.cursor.x(),
                                   ix.y() - ctx.cursor.y())
                    if d <= ctx.tol and not _protected(ix):
                        ctx.check("intersection", ix, src)
```

- [ ] **Step 3: Smoke launch — confirm wall-corner behavior improved**

```bash
python main.py
```

In the app: create two walls in an L joint (or open a project that has one). Hover the outer corner. **Expected:** yellow *filled* square marker on the corner, not a yellow X-cross. If the X-cross still wins, re-read steps 1–2 — most likely `endpoint_candidates` is not being populated (phase 1 ordering check) or `protection_r` is too small.

- [ ] **Step 4: Commit**

```bash
git add firepro3d/snap_engine.py
git commit -m "feat(snap): add endpoint protection band in phase-4 intersection scan (§6.3 Change B)"
```

---

## Task 6: Renderer — filled glyph pass for named face targets

**Files:**
- Modify: `firepro3d/model_view.py` (lines 264–317, marker pass in `drawForeground`)

- [ ] **Step 1: Read the current marker block**

Open `firepro3d/model_view.py` lines 264–317. Confirm that all shapes are drawn with `setBrush(QBrush(Qt.BrushStyle.NoBrush))`.

- [ ] **Step 2: Switch brush based on `snap_result.name`**

Replace lines 275–278 (the `pen = QPen(...)` through `painter.setBrush(...)` block) with:

```python
            pen = QPen(color, 2)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)

            # Filled glyph variant for WallSegment face-corner / face-mid
            # targets (§8.2 of the snap engine spec, amended: *filled* =
            # face / secondary, *outlined* = centerline / default).
            _name = getattr(snap_result, "name", None)
            if _name is not None and _name.startswith("face-"):
                painter.setBrush(QBrush(color))
            else:
                painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
```

- [ ] **Step 3: Smoke launch**

```bash
python main.py
```

Hover a wall's centerline endpoint — outlined yellow square (as today). Hover the outer face corner at an L-joint — **filled** yellow square. Hover the middle of a wall face — **filled** green triangle. Hover a line endpoint on any non-wall object — outlined yellow square (unchanged).

- [ ] **Step 4: Commit**

```bash
git add firepro3d/model_view.py
git commit -m "feat(view): fill snap marker glyph when snap_result.name starts with 'face-'"
```

---

## Task 7: Code-level legend comment block in `snap_engine.py`

**Files:**
- Modify: `firepro3d/snap_engine.py` (above `SNAP_COLORS`, around line 47)

- [ ] **Step 1: Insert the legend block**

Immediately before the line `SNAP_COLORS: dict[str, str] = {` (around line 47), insert:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Snap marker legend
# ─────────────────────────────────────────────────────────────────────────────
#
# Eight base glyphs, all rendered *outlined* (no fill) by the foreground
# pass in model_view.drawForeground. Color is carried by SNAP_COLORS;
# shape is carried by SNAP_MARKERS; priority (picker tie-break) is
# carried by SNAP_PRIORITY below.
#
#   endpoint        yellow     outlined square          END  (priority 1)
#   midpoint        green      outlined triangle        MID  (priority 2)
#   intersection    yellow     x inside square          INT  (priority 0)
#   center          cyan       circle                   CEN  (priority 3)
#   quadrant        orange     diamond                  QUA  (priority 5)
#   perpendicular   magenta    right-angle symbol       PER  (priority 4)
#   tangent         lime       tangent circle           TAN  (priority 6)
#   nearest         grey       cross                    NEA  (priority 7)
#
# Two *filled* named-target variants (added 2026-04 per snap engine
# spec §8.2, amended). These are triggered by the ``name`` field on
# OsnapResult: targets whose name starts with ``face-`` are rendered
# with the base glyph's fill color instead of the outlined default.
#
#   face-*-corner-* filled yellow square    WallSegment face corners
#   face-*-mid      filled green triangle   WallSegment face midpoints
#
# See docs/specs/snapping-engine.md §4, §8.
# ─────────────────────────────────────────────────────────────────────────────
```

- [ ] **Step 2: Commit**

```bash
git add firepro3d/snap_engine.py
git commit -m "docs(snap): add marker-glyph legend comment block above SNAP_COLORS"
```

---

## Task 8: Bootstrap pytest + headless Qt test infrastructure

**Goal:** This repo has no existing tests. Create the minimum infrastructure to run one test file that instantiates `QGraphicsScene` headlessly.

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create/modify: `pytest.ini` at repo root (or add `[tool.pytest.ini_options]` if a `pyproject.toml` already exists — it does not today, so create `pytest.ini`).

- [ ] **Step 1: Verify pytest is available in the venv**

```bash
source venv/Scripts/activate && python -c "import pytest; print(pytest.__version__)"
```
Expected: a version string. If `ModuleNotFoundError`:

```bash
pip install pytest
```

- [ ] **Step 2: Create `tests/__init__.py` (empty)**

```bash
touch tests/__init__.py
```

- [ ] **Step 3: Create `tests/conftest.py`**

Write this content to `tests/conftest.py`:

```python
"""Test fixtures for FirePro3D headless Qt tests.

Qt requires a single QApplication instance per process before any
QGraphicsScene / widget is instantiated, even when no window is shown.
This conftest provides a session-scoped fixture for it.
"""

from __future__ import annotations

import sys
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for headless Qt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    yield app
    # Do not call app.quit() — pytest may run more tests in the same
    # process and Qt dislikes repeated QApplication creation.
```

- [ ] **Step 4: Create `pytest.ini` at repo root**

Write this content to `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 5: Run pytest to confirm collection works (no tests yet → 0 collected, exit 5)**

```bash
pytest
```
Expected: `no tests ran in …s` with exit code 5 (or exit 0 if pytest is very lenient). Not a failure.

- [ ] **Step 6: Commit**

```bash
git add tests/__init__.py tests/conftest.py pytest.ini
git commit -m "chore(tests): bootstrap pytest + headless QApplication fixture"
```

---

## Task 9: Regression test — §7.1 L-joint corner

**Files:**
- Create: `tests/test_snap_engine_case_studies.py`

- [ ] **Step 1: Write the failing test**

Write this content to `tests/test_snap_engine_case_studies.py`:

```python
"""Case-study regression tests from docs/specs/snapping-engine.md §7.

Test 1 covers §7.1: snapping near the outer corner of an L-joint must
return the wall's face-corner endpoint, not a phase-4 intersection.
Test 2 covers §7.2: a single wall alone must not emit any intersection
candidate from wall-internal face crossings.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.snap_engine import SnapEngine
from firepro3d.wall import WallSegment


def _make_scene() -> QGraphicsScene:
    """Create a minimal scene that WallSegment will accept."""
    scene = QGraphicsScene()
    # WallSegment's mitered logic looks up scene._walls; seed it.
    scene._walls = []
    return scene


def _add_wall(scene: QGraphicsScene,
              p1: QPointF, p2: QPointF,
              thickness_mm: float = 150.0) -> WallSegment:
    """Create and register a WallSegment in the given scene."""
    wall = WallSegment(p1, p2, thickness_mm=thickness_mm)
    scene.addItem(wall)
    scene._walls.append(wall)
    return wall


def test_l_joint_corner_resolves_to_face_endpoint(qapp):
    """§7.1: Cursor at an L-joint outer corner must snap to a face
    endpoint, not an intersection."""
    scene = _make_scene()

    # L-joint: horizontal wall from (0,0) to (1000,0); vertical wall
    # from (1000,0) to (1000,1000). Walls meet at (1000, 0).
    wall_a = _add_wall(scene, QPointF(0, 0),    QPointF(1000, 0))
    wall_b = _add_wall(scene, QPointF(1000, 0), QPointF(1000, 1000))

    # Outer corner of the L (opposite the interior angle). For a
    # 150 mm centered wall with no scene scale_manager, the outer
    # corner is roughly at (1075, -75) — half-thickness outward on
    # each wall's outer face. Use the wall's own snap_quad_points
    # to find the real point rather than guessing.
    ql_a = wall_a.snap_quad_points()
    ql_b = wall_b.snap_quad_points()
    # Outer corner of wall_a's far-side cap closest to wall_b.
    # Cursor placed exactly on wall_a's face-right-corner-B, which is
    # the mitered corner at the joint.
    cursor = ql_a[2]  # p2r — right face, endpoint 2

    engine = SnapEngine()
    # Use identity transform → scale=1, tol in scene units = 40.
    result = engine.find(cursor, scene, QTransform())

    assert result is not None, "expected a snap result at the L-joint"
    assert result.snap_type == "endpoint", (
        f"expected endpoint, got {result.snap_type!r} "
        f"(name={result.name!r})"
    )
    assert result.name is not None and result.name.startswith("face-"), (
        f"expected a face-* named target, got name={result.name!r}"
    )


def test_isolated_wall_emits_no_internal_intersection(qapp):
    """§7.2: A lone wall must not produce an ``intersection`` snap
    from its own face×face crossings. With the same-parent filter
    already in place (Change A) this passes today; the test pins it
    against regressions."""
    scene = _make_scene()
    wall = _add_wall(scene, QPointF(0, 0), QPointF(1000, 0))

    # Cursor placed on the wall centerline well away from either cap.
    cursor = QPointF(500, 0)

    engine = SnapEngine()
    result = engine.find(cursor, scene, QTransform())

    # The closest valid candidate here is the centerline midpoint.
    assert result is not None
    assert result.snap_type != "intersection", (
        f"wall-internal face crossings leaked as intersection at "
        f"{result.point.x()},{result.point.y()}"
    )
```

- [ ] **Step 2: Run the tests to see them pass or surface real failures**

```bash
pytest tests/test_snap_engine_case_studies.py -v
```

Expected (success path): both tests PASS. If `test_l_joint_corner_resolves_to_face_endpoint` fails with "expected endpoint, got 'intersection'", Task 5's endpoint protection band is not firing for this cursor position — inspect `ctx.endpoint_candidates` and `protection_r` in a debugger, and re-verify Task 4's `snap_quad_points()` wiring. If it fails with "expected a face-* named target, got name='centerline-end-B'", the cursor landed on the centerline endpoint instead of the face corner because `snap_quad_points()` returned the unmitered quad — verify Task 1 wiring. If `WallSegment(...)` constructor raises (missing required kwarg), update `_add_wall` accordingly — read `wall.py`'s `__init__` and pass exactly what it needs.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_case_studies.py
git commit -m "test(snap): add §7.1 L-joint and §7.2 wall-internal regression tests"
```

---

## Task 10: Update `docs/specs/snapping-engine.md`

**Files:**
- Modify: `docs/specs/snapping-engine.md` (§8.2 paragraph, §12 roadmap table)

- [ ] **Step 1: Amend §8.2 filled/outlined convention**

In `docs/specs/snapping-engine.md` §8.2, replace the sentence:

> "The existing **filled** square and **filled** triangle continue to mean "centerline endpoint / midpoint" or "ordinary endpoint / midpoint on simple objects." Filled = primary/centerline; hollow = secondary/face — the rule is small enough to memorize at a glance."

with:

> "The existing **outlined** square and **outlined** triangle continue to mean "centerline endpoint / midpoint" or "ordinary endpoint / midpoint on simple objects." **Outlined = primary / centerline / default; filled = secondary / face** — the rule was inverted during implementation (April 2026) because all pre-existing markers in FirePro3D were already rendered outlined, and introducing new outlined variants would have required changing every non-wall glyph. The user-facing disambiguation is preserved: at an L-joint the filled face-corner glyph reads clearly against the outlined centerline-end glyph. See roadmap item 3."

- [ ] **Step 2: Add T-joint deferral note at the end of §8.3**

Append a new paragraph at the end of §8.3:

> **T-joint inferred targets (deferred).** When one wall terminates into the face of another, there is no candidate at the T-point today (neither endpoint nor phase-4 intersection; the walls do not cross). This is an *inferred* target — it belongs to the wall placement / joinery spec (tracked in `TODO.md` as a separate P1 spec & grill session, surfaced 2026-04 during the item-3 grill) and to the inferred-placement subsystem (roadmap item 14). This spec commits only to the L-joint case, which is handled by items 1 + 3.

- [ ] **Step 3: Mark roadmap items 1, 3, 10 done in §12**

In the §12 roadmap table, change the "Pri" column for items 1, 3, and 10 from `**P1**` / `**P2**` to `~~done~~` (or add a Status column — pick whichever matches the existing convention in the file). If the file uses checkbox lists elsewhere, use `[x]` / `[ ]`. Match the convention of the file.

- [ ] **Step 4: Commit**

```bash
git add docs/specs/snapping-engine.md
git commit -m "docs(spec): amend §8.2 filled/outlined, add T-joint deferral, mark items 1/3/10 done"
```

---

## Task 11: Update `TODO.md`

**Files:**
- Modify: `TODO.md`

- [ ] **Step 1: Check off items 1, 3, 10 in the snap roadmap**

Open `TODO.md`. Find the three lines:
- "Snap picker: same-parent intersection suppression + endpoint protection band …"
- "WallSegment named-target marker variants …"
- (Roadmap item 10 — case-study regression tests — it may be named "Snap engine case-study regression tests pinned to §7.1 and §7.2")

Change each `- [ ]` to `- [x]` and add a trailing `[done:2026-04-07]` tag.

- [ ] **Step 2: Commit**

```bash
git add TODO.md
git commit -m "chore(todo): mark snap roadmap items 1, 3, 10 as done"
```

---

## Task 12: Final verification

- [ ] **Step 1: Run all tests**

```bash
pytest -v
```
Expected: both case-study tests PASS; no unexpected collection errors.

- [ ] **Step 2: Smoke the app**

```bash
python main.py
```
Manual checklist inside the app:
- Create/open a project with at least one L-joint between two walls.
- Hover the **outer corner**: filled yellow square marker appears on the corner.
- Hover the **centerline endpoint** of an isolated wall end: outlined yellow square (as today).
- Hover the **middle of a wall face edge**: filled green triangle.
- Hover a **pipe endpoint** or **line endpoint**: outlined yellow square (unchanged).
- Close the app cleanly.

- [ ] **Step 3: Review the full diff**

```bash
git log main..HEAD --oneline
git diff main..HEAD --stat
```
Expected: ~12 commits, touching `firepro3d/wall.py`, `firepro3d/snap_engine.py`, `firepro3d/model_view.py`, `docs/specs/snapping-engine.md`, `TODO.md`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_snap_engine_case_studies.py`, `pytest.ini`, and this plan file.

- [ ] **Step 4: Hand off to finishing-a-development-branch**

Invoke `superpowers:finishing-a-development-branch` to choose how to integrate (merge to main, PR, etc.).

---

## Self-review notes

- **Spec coverage:** §6.3 Change A is documented (already present) in Task 5 Step 2 comment. §6.3 Change B ships in Task 5. §8 named targets ship in Tasks 1–4. §7.1 + §7.2 regression tests ship in Task 9. Legend (code-level) ships in Task 7.
- **Out-of-scope discipline:** no changes to ConstructionLine, ArcItem, generic QGraphicsPathItem, nearest/perpendicular decoupling, or matrix fixture harness — all remain as open roadmap items.
- **Risks:** (1) Test 1 depends on the real `WallSegment.__init__` signature and on `snap_quad_points()` returning the mitered corner for an L-joint that has no scene `scale_manager`; Task 9 Step 2 has fallback guidance if either assumption turns out wrong. (2) The `_FACE_COLLAPSE_SCENE_EPS = 3.0` scene-unit threshold is a rough approximation; thin-wall suppression may fire too aggressively in drawings with very small scene units per paper millimeter. If that becomes a reported issue, the right fix is to compute the threshold from the view transform at `find()` time and pass it into `_collect`, but that's a follow-up, not this task.
