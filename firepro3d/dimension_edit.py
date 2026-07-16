"""
dimension_edit.py
=================
A QLineEdit-based widget for dimensional input with automatic unit
parsing and formatting.  Accepts input in any unit (ft-in, mm, m, etc.)
and converts to the project's current display unit on commit.

Internal storage is always **millimetres**.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLineEdit, QStyledItemDelegate
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFocusEvent

from .scale_manager import ScaleManager


class DimensionEdit(QLineEdit):
    """Line-edit that stores a dimension in mm and displays it using
    the project's current unit system.

    Usage::

        edit = DimensionEdit(scale_manager, initial_mm=3048.0)
        layout.addWidget(edit)

        # Read current value
        mm = edit.value_mm()
        ft = edit.value_ft()

        # Set value programmatically
        edit.set_value_mm(6096.0)
        edit.set_value_ft(20.0)

        # React to changes
        edit.valueChanged.connect(lambda mm: print(f"New value: {mm} mm"))

        # Custom parser (e.g. paper-space text height, forces mm fallback)
        edit = DimensionEdit(None, initial_mm=3.175,
                             parser=_parse_text_height_mm, minimum=0.0)
    """

    # Emitted when a valid edit commits, with the new value in mm
    valueChanged = pyqtSignal(float)

    def __init__(self, scale_manager: ScaleManager | None = None,
                 initial_mm: float = 0.0, parent=None,
                 parser=None, minimum: float | None = None,
                 formatter=None):
        super().__init__(parent)
        self._sm = scale_manager
        self._value_mm: float = initial_mm
        self._last_valid_mm: float = initial_mm
        self._parser = parser        # optional str -> float|None override
        self._minimum = minimum      # accepted values must be strictly > minimum
        self._formatter = formatter  # optional mm -> str display override
        self._seed_text = ""

        # Display the initial value
        self._reformat()

        # Commit on Enter / Return
        self.editingFinished.connect(self._on_editing_finished)

    # ── Public API ────────────────────────────────────────────────────

    def value_mm(self) -> float:
        """Return the current value in millimetres."""
        return self._value_mm

    def value_ft(self) -> float:
        """Convenience: return value in feet."""
        return self._value_mm / 304.8

    def set_value_mm(self, mm: float) -> None:
        """Set the value (in mm) and reformat the display."""
        self._value_mm = mm
        self._last_valid_mm = mm
        self._reformat()

    def set_value_ft(self, ft: float) -> None:
        """Convenience: set value from feet."""
        self.set_value_mm(ft * 304.8)

    def set_scale_manager(self, sm: ScaleManager) -> None:
        """Update the scale manager (e.g. after unit system change)."""
        self._sm = sm
        self._reformat()

    def commit(self) -> None:
        """Parse and commit the current text now (same path as
        ``editingFinished``).

        Needed by item-view delegates: on Tab-to-next-cell Qt commits the
        editor *before* ``editingFinished`` fires, so the delegate must
        force the parse first or it reads the stale seeded value.
        """
        self._on_editing_finished()

    # ── Internal ──────────────────────────────────────────────────────

    def _reformat(self) -> None:
        """Format the stored mm value using the project's display unit."""
        if self._formatter is not None:
            self.setText(self._formatter(self._value_mm))
        elif self._sm:
            self.setText(self._sm.format_length(self._value_mm))
        else:
            self.setText(f"{self._value_mm:.2f} mm")
        # Seed guard: an untouched commit must keep the exact stored value —
        # re-parsing the display text loses precision when the display unit
        # quantizes (e.g. imperial 1/8" resolution shows 3/16" as 1/4").
        self._seed_text = self.text()

    def _on_editing_finished(self) -> None:
        """Parse the user's text, update value or revert."""
        text = self.text().strip()
        if not text or text == self._seed_text.strip():
            # Blank or untouched -> keep exact stored value (no emit)
            self._value_mm = self._last_valid_mm
            self._reformat()
            return

        if self._parser is not None:
            parsed = self._parser(text)
        else:
            fallback = self._sm.bare_number_unit() if self._sm else "mm"
            parsed = ScaleManager.parse_dimension(text, fallback)

        if parsed is not None and (self._minimum is None
                                   or parsed > self._minimum):
            self._value_mm = parsed
            self._last_valid_mm = parsed
            self._reformat()
            self.valueChanged.emit(self._value_mm)
        else:
            # Invalid or below minimum -> revert
            self._value_mm = self._last_valid_mm
            self._reformat()

    def focusInEvent(self, event: QFocusEvent) -> None:
        """Select all text on focus for easy replacement."""
        super().focusInEvent(event)
        self.selectAll()


class DimensionDelegate(QStyledItemDelegate):
    """Item delegate that edits dimension table cells with a DimensionEdit.

    The mm value lives in *value_role*; the formatted display string is
    written to ``DisplayRole`` on commit, so cells always show
    ``ScaleManager.format_length`` output regardless of what the user typed.

    Usage::

        delegate = DimensionDelegate(lambda: self._sm, table)
        table.setItemDelegateForColumn(col, delegate)
    """

    def __init__(self, get_scale_manager, parent=None,
                 value_role: int = Qt.ItemDataRole.UserRole):
        super().__init__(parent)
        self._get_sm = get_scale_manager  # callable → ScaleManager | None
        self._value_role = value_role

    def createEditor(self, parent, option, index):
        return DimensionEdit(self._get_sm(), initial_mm=0.0, parent=parent)

    def setEditorData(self, editor, index):
        val = index.data(self._value_role)
        if val is not None:
            editor.set_value_mm(float(val))

    def setModelData(self, editor, model, index):
        editor.commit()   # Tab commits arrive before editingFinished fires
        mm = editor.value_mm()
        model.setData(index, mm, self._value_role)
        sm = self._get_sm()
        if sm:
            model.setData(index, sm.format_length(mm),
                          Qt.ItemDataRole.DisplayRole)
        else:
            model.setData(index, f"{mm:.1f} mm", Qt.ItemDataRole.DisplayRole)
