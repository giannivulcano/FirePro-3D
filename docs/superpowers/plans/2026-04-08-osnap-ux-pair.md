# OSNAP UX Pair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind F3 to the existing `Model_Space.toggle_osnap()`, add a persistent click-to-toggle OSNAP indicator to the main window status bar, and close roadmap item 12 by documenting the per-type-toggle-UI gap in the snap spec.

**Architecture:** Item 11 is pure wiring — the state machine (`toggle_osnap`, `_osnap_enabled`, `SnapEngine.enabled`) already exists at `firepro3d/model_space.py:2806`. We add (a) an application-global `QShortcut(QKeySequence("F3"))` on `MainWindow` and (b) a persistent `QLabel` OSNAP indicator added via `status_bar.addPermanentWidget()`, clickable via `mousePressEvent`. Both call `self.scene.toggle_osnap()`. A `scene.osnapToggled` signal broadcasts state changes so the label stays in sync regardless of which input path triggered them. Item 12 is a documentation-only change to the snap spec and TODO.md.

**Tech Stack:** PyQt6 (`QShortcut`, `QKeySequence`, `QLabel`, `pyqtSignal`), pytest with the existing session-scoped `qapp` fixture at `tests/conftest.py`.

---

## File Structure

**Modify:**
- `firepro3d/model_space.py` — add `osnapToggled = pyqtSignal(bool)` to `Model_Space`; emit it from `toggle_osnap()`.
- `main.py` — in `MainWindow.__init__`, add the F3 `QShortcut`, the OSNAP `QLabel` indicator, and the slot that restyles the label. Wire `scene.osnapToggled` to the restyle slot. Call `_update_osnap_indicator()` once at startup to set initial style.
- `docs/specs/snapping-engine.md` — amend §9.5 and §12 items 11 & 12 with the finding and done-tags.
- `TODO.md` — mark roadmap items 11 & 12 done; add new P1 OSNAP-toolbar-spec task.

**Create:**
- `tests/test_osnap_toggle.py` — unit tests for `toggle_osnap()` state machine and signal emission.
- `tests/test_osnap_ui.py` — integration tests covering F3 shortcut, indicator restyling, and click-to-toggle. Uses `MainWindow` under the existing `qapp` fixture.

**No changes needed to:** `firepro3d/snap_engine.py` (per-type booleans stay as-is), `firepro3d/model_view.py` (no F3 handler in the view — the global shortcut handles it).

---

## Task 1: Add `osnapToggled` signal to `Model_Space`

**Why first:** The UI layer (Task 3) needs a signal to subscribe to so the indicator stays in sync whether F3, the click, or a future caller triggers the toggle. Adding the signal first lets us unit-test the state-machine contract before touching the UI.

**Files:**
- Modify: `firepro3d/model_space.py` (import area + `Model_Space.__init__` + `toggle_osnap` at line 2806)
- Create: `tests/test_osnap_toggle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_osnap_toggle.py`:

```python
"""Unit tests for Model_Space OSNAP toggle state machine and signal."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.model_space import Model_Space


@pytest.fixture
def scene(qapp):
    """Fresh Model_Space per test."""
    s = Model_Space()
    yield s


def test_osnap_default_enabled(scene):
    assert scene._osnap_enabled is True
    assert scene._snap_engine.enabled is True


def test_toggle_flips_both_flags(scene):
    scene.toggle_osnap()
    assert scene._osnap_enabled is False
    assert scene._snap_engine.enabled is False
    scene.toggle_osnap()
    assert scene._osnap_enabled is True
    assert scene._snap_engine.enabled is True


def test_toggle_explicit_true_false(scene):
    scene.toggle_osnap(False)
    assert scene._osnap_enabled is False
    scene.toggle_osnap(False)  # idempotent
    assert scene._osnap_enabled is False
    scene.toggle_osnap(True)
    assert scene._osnap_enabled is True


def test_toggle_clears_snap_result(scene):
    # Simulate an active snap marker.
    scene._snap_result = object()
    scene.toggle_osnap()
    assert scene._snap_result is None


def test_toggle_emits_signal(scene):
    received: list[bool] = []
    scene.osnapToggled.connect(received.append)
    scene.toggle_osnap()  # True -> False
    scene.toggle_osnap()  # False -> True
    scene.toggle_osnap(False)  # True -> False
    assert received == [False, True, False]


def test_toggle_signal_emits_even_when_state_unchanged(scene):
    """Explicit set to current value still emits (idempotent callers
    may rely on the signal to resynchronize UI)."""
    received: list[bool] = []
    scene.osnapToggled.connect(received.append)
    scene.toggle_osnap(True)  # already True
    assert received == [True]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_osnap_toggle.py -v`
Expected: `test_toggle_emits_signal` and `test_toggle_signal_emits_even_when_state_unchanged` FAIL with `AttributeError: 'Model_Space' object has no attribute 'osnapToggled'`. The other four should PASS (they cover existing behavior).

- [ ] **Step 3: Add the signal to `Model_Space`**

In `firepro3d/model_space.py`, find the existing `pyqtSignal` imports (search for `pyqtSignal` near the top of the file) and ensure `pyqtSignal` is imported from `PyQt6.QtCore`. It already is — `Model_Space` already defines signals like `cursorMoved`, `modeChanged`, etc. Add the new signal alongside those existing class-level signal declarations in `Model_Space`:

```python
    osnapToggled = pyqtSignal(bool)   # emitted whenever toggle_osnap() runs
```

Place it near the other `pyqtSignal(...)` lines in the class (search for `cursorMoved = pyqtSignal` to find the block).

- [ ] **Step 4: Emit the signal from `toggle_osnap`**

Locate `toggle_osnap` at `firepro3d/model_space.py:2806`. Replace the method body with:

```python
    def toggle_osnap(self, enabled: bool | None = None):
        """Toggle or explicitly set OSNAP.  Called from F3 shortcut and
        the status bar OSNAP indicator."""
        if enabled is None:
            self._osnap_enabled = not self._osnap_enabled
        else:
            self._osnap_enabled = bool(enabled)
        self._snap_engine.enabled = self._osnap_enabled
        self._snap_result = None
        # Refresh foreground overlay
        for v in self.views():
            v.viewport().update()
        self.osnapToggled.emit(self._osnap_enabled)
```

Only two changes: updated docstring, and `self.osnapToggled.emit(...)` added at the end.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_osnap_toggle.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add firepro3d/model_space.py tests/test_osnap_toggle.py
git commit -m "feat(osnap): add osnapToggled signal to Model_Space"
```

---

## Task 2: Add F3 global shortcut on `MainWindow`

**Files:**
- Modify: `main.py` — imports + `MainWindow.__init__`
- Create: `tests/test_osnap_ui.py` (first test case; expanded in Task 3)

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_osnap_ui.py`:

```python
"""Integration tests for the OSNAP UX pair (F3 shortcut + status bar
indicator). All tests reuse the session-scoped ``qapp`` fixture from
tests/conftest.py.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest

from main import MainWindow


@pytest.fixture
def main_window(qapp):
    """Fresh MainWindow per test. Not shown — headless."""
    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()


def test_f3_shortcut_toggles_osnap(main_window):
    assert main_window.scene._osnap_enabled is True
    QTest.keyClick(main_window, Qt.Key.Key_F3)
    assert main_window.scene._osnap_enabled is False
    QTest.keyClick(main_window, Qt.Key.Key_F3)
    assert main_window.scene._osnap_enabled is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_osnap_ui.py::test_f3_shortcut_toggles_osnap -v`
Expected: FAIL — state does not change because no F3 binding exists yet.

- [ ] **Step 3: Add the QShortcut in `MainWindow.__init__`**

In `main.py`, update the existing PyQt6 imports near the top. Find the `from PyQt6.QtGui import ...` line (there is one — it currently pulls in `QKeySequence` if already present, otherwise add it) and ensure both `QKeySequence` and `QShortcut` are imported:

```python
from PyQt6.QtGui import QKeySequence, QShortcut  # merge into existing QtGui import
```

If a `QtGui` import already exists, append `QKeySequence, QShortcut` to its import list (do not add a duplicate line).

Then, in `MainWindow.__init__` near the status-bar setup (around `main.py:386`, right after `self.scene.instructionChanged.connect(...)` — i.e., after all existing `self.scene.*` signal wiring — add:

```python
        # OSNAP global F3 toggle (snap-spec §9.4 / §12 item 11).
        # Application-global so pressing F3 in any view (plan,
        # elevation, 3D) flips OSNAP state.
        self._osnap_shortcut = QShortcut(QKeySequence("F3"), self)
        self._osnap_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._osnap_shortcut.activated.connect(self.scene.toggle_osnap)
```

Note: `Qt` is already imported in `main.py`; verify by searching for `from PyQt6.QtCore import` — if `Qt` is not there, add it.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_osnap_ui.py::test_f3_shortcut_toggles_osnap -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_osnap_ui.py
git commit -m "feat(osnap): bind F3 to global OSNAP toggle"
```

---

## Task 3: Add persistent status-bar OSNAP indicator with click-to-toggle

**Files:**
- Modify: `main.py` — `MainWindow.__init__` + new private method `_update_osnap_indicator`
- Modify: `tests/test_osnap_ui.py` — append three new tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_osnap_ui.py`:

```python
def test_indicator_exists_and_initial_state(main_window):
    label = main_window.osnap_indicator
    assert label is not None
    assert label.text() == "OSNAP"
    # Initial state is enabled -> "on" marker in property
    assert label.property("osnapOn") is True


def test_indicator_restyles_on_toggle(main_window):
    label = main_window.osnap_indicator
    main_window.scene.toggle_osnap()  # -> False
    assert label.property("osnapOn") is False
    main_window.scene.toggle_osnap()  # -> True
    assert label.property("osnapOn") is True


def test_indicator_click_toggles(main_window):
    label = main_window.osnap_indicator
    assert main_window.scene._osnap_enabled is True
    QTest.mouseClick(label, Qt.MouseButton.LeftButton)
    assert main_window.scene._osnap_enabled is False
    QTest.mouseClick(label, Qt.MouseButton.LeftButton)
    assert main_window.scene._osnap_enabled is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_osnap_ui.py -v`
Expected: the three new tests FAIL with `AttributeError: 'MainWindow' object has no attribute 'osnap_indicator'`. The F3 test from Task 2 still PASSES.

- [ ] **Step 3: Add a clickable QLabel subclass and indicator to `MainWindow`**

In `main.py`, add the following small helper class **above** `class MainWindow(QMainWindow):`:

```python
class _OsnapIndicatorLabel(QLabel):
    """Clickable status-bar label for the OSNAP state indicator."""

    def __init__(self, parent=None):
        super().__init__("OSNAP", parent)
        self.setToolTip("Toggle Object Snap (F3)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(64)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("osnapOn", True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    # Declared at class level below with pyqtSignal import.
```

Then move the signal declaration inside the class (PyQt6 requires it to be a class attribute). Use this final form instead of the sketch above — replace the sketch in your edit:

```python
from PyQt6.QtCore import pyqtSignal  # merge into existing QtCore import

class _OsnapIndicatorLabel(QLabel):
    """Clickable status-bar label for the OSNAP state indicator."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("OSNAP", parent)
        self.setToolTip("Toggle Object Snap (F3)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(64)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("osnapOn", True)
        self._apply_style()

    def setOsnapOn(self, on: bool) -> None:
        self.setProperty("osnapOn", bool(on))
        self._apply_style()

    def _apply_style(self) -> None:
        on = bool(self.property("osnapOn"))
        if on:
            self.setStyleSheet(
                "font-weight: bold; color: #44ff88; padding: 2px 8px; "
                "border: 1px solid #44ff88; border-radius: 3px;"
            )
        else:
            self.setStyleSheet(
                "font-weight: bold; color: #666; padding: 2px 8px; "
                "border: 1px solid #666; border-radius: 3px;"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
```

Ensure `pyqtSignal` is on the `from PyQt6.QtCore import ...` line (merge; do not duplicate).

Next, inside `MainWindow.__init__`, after the existing status bar setup block (the block that adds `self.coord_label` via `status_bar.addPermanentWidget(self.coord_label)` around `main.py:389`), add:

```python
        # OSNAP status-bar indicator (snap-spec §9.5 / §12 item 11).
        self.osnap_indicator = _OsnapIndicatorLabel(self)
        self.osnap_indicator.clicked.connect(self.scene.toggle_osnap)
        status_bar.addPermanentWidget(self.osnap_indicator)
        self.scene.osnapToggled.connect(self._update_osnap_indicator)
        # Initialize style to current state.
        self._update_osnap_indicator(self.scene._osnap_enabled)
```

And add the slot as a method on `MainWindow` (near other small slot methods such as `_update_mode_label`):

```python
    def _update_osnap_indicator(self, enabled: bool) -> None:
        self.osnap_indicator.setOsnapOn(enabled)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_osnap_ui.py -v`
Expected: all 4 tests in the file PASS.

- [ ] **Step 5: Run the full test suite to verify nothing regressed**

Run: `pytest -v`
Expected: all tests (including `tests/test_osnap_toggle.py` and `tests/test_snap_engine_case_studies.py`) PASS.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_osnap_ui.py
git commit -m "feat(osnap): persistent status-bar OSNAP indicator with click-to-toggle"
```

---

## Task 4: Close item 12 — spec amendment + TODO.md updates

**Files:**
- Modify: `docs/specs/snapping-engine.md` (§9.5 and §12 rows for items 11 & 12)
- Modify: `TODO.md`

- [ ] **Step 1: Amend `docs/specs/snapping-engine.md` §9.5**

Locate §9.5 (line ~311 area — the paragraph about the deferred OSNAP toolbar). Append the following paragraph to the end of §9.5:

```markdown
**2026-04-08 finding (roadmap item 12):** A code search of the project confirmed that no UI surface currently toggles the per-type `SnapEngine` booleans (`snap_endpoint`, `snap_midpoint`, `snap_intersection`, `snap_center`, `snap_quadrant`, `snap_nearest`, `snap_perpendicular`, `snap_tangent`). They remain reachable only by direct attribute access. The per-type toggle UI is therefore formally deferred to a dedicated OSNAP-toolbar spec session, which has been promoted from "deferred" to a P1 backlog task. The persistent OSNAP status-bar indicator (delivered alongside this finding) is the anchor the toolbar will later integrate with.
```

- [ ] **Step 2: Amend `docs/specs/snapping-engine.md` §12 rows**

In §12, locate the table rows for items 11 and 12 (they currently end in `[ref:snap-spec§9.4-§9.5]` and `[ref:snap-spec§9.5]` respectively, around line ~384). Update both to show completion — append a `[done:2026-04-08]` note to each row's description. The exact edit:

For item 11 row, replace:

```markdown
| 11 | **P3** | Bind F3 to global OSNAP on/off and surface state in status bar | F3 toggles `SnapEngine.enabled`; status bar reflects current state | `[ref:snap-spec§9.4-§9.5]` |
```

with:

```markdown
| 11 | **P3** | Bind F3 to global OSNAP on/off and surface state in status bar | F3 toggles `SnapEngine.enabled`; status bar reflects current state | `[ref:snap-spec§9.4-§9.5]` `[done:2026-04-08]` |
```

For item 12 row, replace:

```markdown
| 12 | **P3** | Confirm and (if absent) expose per-type OSNAP toggle UI surface | Either confirm an existing UI surfaces `snap_endpoint`, `snap_midpoint`, etc., or document that none does and file the toolbar spec as a follow-up | `[ref:snap-spec§9.5]` |
```

with:

```markdown
| 12 | **P3** | Confirm and (if absent) expose per-type OSNAP toggle UI surface | Verified absent; §9.5 amended and OSNAP toolbar spec promoted to P1 backlog task | `[ref:snap-spec§9.5]` `[done:2026-04-08]` |
```

- [ ] **Step 3: Update `TODO.md` — mark items done**

In `TODO.md`, find the two snapping-roadmap entries (currently lines ~37 and ~38):

```markdown
- [ ] Bind F3 to global OSNAP toggle and reflect state in status bar [ref:snap-spec§9.4-§9.5] [type:Backlog] [P3] [subject:CAD]
- [ ] Confirm or build per-type OSNAP toggle UI surface (`snap_endpoint`, `snap_midpoint`, etc.) [ref:snap-spec§9.5] [type:Backlog] [P3] [subject:CAD]
```

Replace with:

```markdown
- [x] Bind F3 to global OSNAP toggle and reflect state in status bar [ref:snap-spec§9.4-§9.5] [type:Backlog] [P3] [subject:CAD] [done:2026-04-08]
- [x] Confirm or build per-type OSNAP toggle UI surface (`snap_endpoint`, `snap_midpoint`, etc.) [ref:snap-spec§9.5] [type:Backlog] [P3] [subject:CAD] [done:2026-04-08]
```

- [ ] **Step 4: Add the new P1 follow-up task to `TODO.md`**

In `TODO.md`, inside the "Snapping Engine Roadmap" section, add the following new bullet at the top of the un-done items (directly after the two newly-marked `[x]` items from Step 3):

```markdown
- [ ] Spec session: OSNAP toolbar — per-type toggle UI, dockable placement, indicator layout, interaction with status bar pill [ref:snap-spec§9.5] [type:Backlog] [P1] [subject:CAD]
```

- [ ] **Step 5: Verify files look correct**

Run: `git diff docs/specs/snapping-engine.md TODO.md`
Expected: four clean edits — §9.5 paragraph added, two §12 rows updated with done-tags, two TODO roadmap lines flipped to `[x]`, one new P1 task added. No other changes.

- [ ] **Step 6: Commit**

```bash
git add docs/specs/snapping-engine.md TODO.md
git commit -m "docs(snap): close roadmap items 11 & 12; promote OSNAP toolbar spec to P1"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass. Note the count for the PR body.

- [ ] **Step 2: Manual smoke check (document outcome in PR body, not as a committed file)**

Run: `python main.py`

Verify each of these and keep notes for the PR description:
1. Status bar shows a green "OSNAP" pill on the right side.
2. Press F3 — pill turns gray. Press again — pill turns green.
3. Click the pill — state toggles identically.
4. With OSNAP off, hover near a wall endpoint in plan view — no OSNAP marker appears.
5. While mid-draw (start a pipe or wall, hover over an endpoint so a marker appears), press F3 — marker disappears instantly.
6. Open the elevation view tab, press F3 — pill still flips (application-global shortcut confirmed).
7. No keybinding conflict: press F3 in the model browser, ribbon search field (if any), etc. — no crashes, no stolen key events.

- [ ] **Step 3: No commit for this task**

This task is verification only. Proceed to PR creation in Phase 6.

---

## Self-Review Notes

- **Spec coverage:** All 7 Item 11 acceptance criteria map to Tasks 1-3. Both Item 12 acceptance criteria map to Task 4. Testing expectations covered by Tasks 1 (unit) and 2-3 (integration); manual smoke list in Task 5.
- **Known limitation not addressed here (intentional):** F3 does not disable the separate `_snap_to_underlay` DXF underlay snap path. Note this in the PR body; no plan task.
- **Out of scope confirmed not leaking in:** no per-type toggles, no persistence, no toolbar, no ribbon button, no changes to `Model_View.keyPressEvent`.
- **Type consistency:** `osnapToggled` signal name, `_OsnapIndicatorLabel` class name, `osnap_indicator` attribute name, `_update_osnap_indicator` slot name, and `setOsnapOn` method name are used consistently across Tasks 1-3.
