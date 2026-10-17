"""No transient top-level window: a ui_kit child made visible before it joins
its parent's layout is briefly its own window (AC2 smoke 2026-10-17 -- the
constraint panel's D41 footer badge flashed on every Block Editor commit)."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPointF
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget

from firepro3d.ui_kit import ActionRowList, PatternList
from tests.test_constraint_e2e import _click
from tests.test_constraint_pick_ribbon import (  # noqa: F401
    _editors, _plan_index, mw, win_with_editor)


class _WindowShows(QObject):
    """Records every top-level (``isWindow``) widget Show while installed."""

    def __init__(self):
        super().__init__()
        self.rows = []

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            self.rows.append((type(obj).__name__, obj.objectName()))
        return False

    def __enter__(self):
        QApplication.instance().installEventFilter(self)
        return self

    def __exit__(self, *exc):
        QApplication.instance().removeEventFilter(self)


class _Field(QLineEdit):
    def __init__(self, mm):
        super().__init__(f"{mm}")

    def value_mm(self):
        return float(self.text())


def test_action_row_footer_badge_is_never_its_own_window(qapp):
    with _WindowShows() as log:
        ActionRowList("Constraints", [], footer="2 DOF", footer_state="free")
        ActionRowList("Constraints", [], footer="Fully defined")
        QApplication.processEvents()
    assert log.rows == []


def test_pattern_note_is_never_its_own_window(qapp):
    with _WindowShows() as log:
        PatternList([("dash", 6.0), ("gap", 2.0)], note="Check the pattern",
                    field_factory=_Field, on_commit=lambda _v: None)
        QApplication.processEvents()
    assert log.rows == []


def test_block_editor_line_commit_flashes_no_window(win_with_editor):
    """The real path: a Block Editor line commit (+ its AC2 H record) rebuilds
    the property panel; no widget may surface as a window meanwhile."""
    win = win_with_editor
    sc = win._active_scene(); view = win._test_editor.view
    sc.set_align_enabled(False)
    sc.set_mode("draw_line")
    _click(view, view.mapFromScene(QPointF(20, 300)))
    QApplication.processEvents()
    with _WindowShows() as log:
        _click(view, view.mapFromScene(QPointF(220, 300)))
        for _ in range(5):
            QApplication.processEvents()
    assert [c.type for c in sc.constraint_ctl.constraints] == ["horizontal"]   # precondition
    assert log.rows == []
