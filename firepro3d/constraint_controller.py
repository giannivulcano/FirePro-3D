"""Constraint controller — the Qt shell of the sketch solver.

parametric-constraint-system.md §3, §8. Composed into every Model_Space;
active only for ``scene_role == "block_editor"`` (D2). Every geometry edit in
the editor routes through one of the seams below.
"""
from __future__ import annotations

import contextlib


class ConstraintController:
    def __init__(self, scene):
        self._scene = scene
        self.enabled = getattr(scene, "scene_role", "plan") == "block_editor"
        self.constraints: list = []
        self.selected_id: str | None = None
        self.hover_id: str | None = None
        self.show_glyphs = True
        self.pick = None

    # ── edit seams (§8) ──────────────────────────────────────────────────
    @contextlib.contextmanager
    def edit(self, items):
        yield

    def begin_drag(self, item) -> None: ...
    def drag(self, item, grip_index: int) -> None: ...
    def end_drag(self) -> None: ...
    def cancel_drag(self) -> None: ...

    def on_items_removed(self, items) -> int:
        return 0

    # ── persistence / undo ───────────────────────────────────────────────
    def capture(self) -> list:
        return []

    def restore(self, records) -> None: ...
