"""Small themed modal message dialog (house frameless shell).

Exposes seven module-level helpers that replace native QMessageBox /
QInputDialog call sites across the app.  Return semantics match the
native equivalents so call sites are mechanical substitutions.

Public API
----------
themed_info(parent, title, message, icon=None) -> None
themed_warn(parent, title, message) -> None
themed_error(parent, title, message) -> None
themed_confirm(parent, title, message, *, danger=False,
               ok_label="Yes", cancel_label="No") -> bool
themed_input_text(parent, title, label, *, initial="") -> tuple[str, bool]
themed_input_number(parent, title, label, *, initial, dimension=True,
                    minimum=None, maximum=None) -> tuple[float, bool]
themed_input_choice(parent, title, label, items, *, current=0)
    -> tuple[str, bool]
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QComboBox)
from PyQt6.QtGui import QDoubleValidator

from .house_dialog import HouseDialog
from .dimension_edit import DimensionEdit
from . import theme as _theme
from .theme import M


# ── Icon glyphs (unicode symbols coloured via CSS) ───────────────────────────
_GLYPH = {
    "info":  ("ℹ", "ok"),
    "warn":  ("⚠", "warn"),
    "error": ("✖", "danger"),
}


class ThemedMessageDialog(HouseDialog):
    """Full house replacement for QMessageBox / QInputDialog.

    Modes
    -----
    * OK-only  (default)  — ``set_footer_buttons(primary=("OK", accept))``
    * Yes/No              — ``_make_yes_no()``
    * Custom confirm      — ``_make_confirm(ok_label, cancel_label, danger)``
    * Input               — body holds an input widget; ``value()`` reads it.

    The ``_make_*`` helpers fully rebuild the footer on each call so they can
    be composed freely after ``__init__``.
    """

    def __init__(self, title, message, parent=None, theme=None, icon=None,
                 kind: str | None = None):
        """Create the dialog.

        Args:
            title:   Window / header title.
            message: Body text shown in a word-wrapped QLabel.
            parent:  Qt parent widget (may be None).
            theme:   Override theme token object (uses auto-detect when None).
            icon:    Optional header icon (passed to HouseDialog / shell).
            kind:    Optional ``"info"`` / ``"warn"`` / ``"error"`` — renders a
                     coloured glyph above the message.
        """
        super().__init__(parent, title=title, icon=icon, min_width=340,
                         theme=theme)
        self.setObjectName("ThemedMessageDialog")

        self._input_widget = None  # set by _add_input_widget

        # Optional status glyph
        if kind and kind in _GLYPH:
            glyph_char, tok = _GLYPH[kind]
            t = self._theme
            colour = getattr(t, tok, t.ok)
            glyph_lbl = QLabel(glyph_char)
            glyph_lbl.setStyleSheet(
                f"color: {colour}; font-size: 22px; font-weight: bold;"
            )
            self.body_layout().addWidget(glyph_lbl)

        # Message label
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        self.body_layout().addWidget(lbl)

        # Default footer: OK only
        self.set_footer_buttons(primary=("OK", self.accept), cancel=False)

    # ── Footer rebuild helpers ────────────────────────────────────────────────

    def _clear_footer(self) -> None:
        """Remove the existing footer widget from the layout and orphan it."""
        if self._footer is not None:
            self._footer.setParent(None)
            self._footer = None

    def _make_yes_no(self) -> None:
        """Rebuild the footer as a Yes/No pair (No left, Yes right/primary).

        Kept for back-compat — existing callers already use this path via
        ``themed_confirm``.
        """
        self._clear_footer()
        no = QPushButton("No")
        no.clicked.connect(self.reject)
        self.set_footer_buttons(primary=("Yes", self.accept), cancel=False,
                                extra_left=no)

    def _make_confirm(self, ok_label: str, cancel_label: str,
                      danger: bool) -> None:
        """Rebuild the footer with custom labels and optional danger styling."""
        self._clear_footer()
        cancel_btn = QPushButton(cancel_label)
        cancel_btn.clicked.connect(self.reject)
        self.set_footer_buttons(primary=(ok_label, self.accept), cancel=False,
                                extra_left=cancel_btn, danger=danger)

    # ── N-button choice footer ────────────────────────────────────────────────

    def _make_choice(self, buttons, result_holder) -> None:
        """Rebuild the footer with an arbitrary ordered list of buttons.

        Args:
            buttons: List of ``(label, key, variant)`` tuples laid out
                left→right.  ``variant`` is ``"primary"``, ``"danger"``, or
                ``None``.  The buttons are right-aligned via a leading stretch.
            result_holder: A mutable dict with a ``"key"`` entry; whichever
                button the user clicks writes its key into
                ``result_holder["key"]`` before accepting the dialog.
        """
        self._choice_result = result_holder
        self._clear_footer()
        footer = QFrame(objectName="footerBar")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(*M.FOOTER_MARGIN)
        fl.setSpacing(M.FOOTER_BTN_GAP)
        fl.addStretch(1)
        for label, key, variant in buttons:
            btn = QPushButton(label)
            if variant:
                btn.setProperty("variant", variant)
            # Capture key in the closure explicitly.
            def _make_handler(k):
                def _handler():
                    result_holder["key"] = k
                    self.accept()
                return _handler
            btn.clicked.connect(_make_handler(key))
            fl.addWidget(btn)
        self._footer = footer
        self._root.addWidget(footer)
        self.adjustSize()

    # ── Input-widget seam ─────────────────────────────────────────────────────

    def _add_input_widget(self, caption: str, widget) -> None:
        """Insert a labelled input widget below the message."""
        if caption:
            cap_lbl = QLabel(caption)
            self.body_layout().addWidget(cap_lbl)
        self.body_layout().addWidget(widget)
        self._input_widget = widget

    def value(self):
        """Return the current value of the input widget.

        Returns:
            For ``DimensionEdit``  → float (mm).
            For plain ``QLineEdit`` → str.
            For ``QComboBox``       → int (current index).
            ``None`` when no input widget is present.
        """
        w = self._input_widget
        if w is None:
            return None
        if isinstance(w, DimensionEdit):
            w.commit()
            return w.value_mm()
        if isinstance(w, QComboBox):
            return w.currentIndex()
        if isinstance(w, QLineEdit):
            return w.text()
        return None


# ── Module-level helper functions ─────────────────────────────────────────────

def themed_info(parent, title, message, icon=None) -> None:
    """Show a themed modal info dialog (OK only).

    Signature preserved for back-compat with 9 existing call sites.

    Args:
        parent:  Qt parent widget.
        title:   Dialog / header title.
        message: Body text.
        icon:    Optional header icon path (passed to HouseDialog shell).
    """
    ThemedMessageDialog(title, message, parent=parent, icon=icon,
                        kind="info").exec()


def themed_warn(parent, title, message) -> None:
    """Show a themed modal warning dialog (OK only, warn glyph)."""
    ThemedMessageDialog(title, message, parent=parent, kind="warn").exec()


def themed_error(parent, title, message) -> None:
    """Show a themed modal error dialog (OK only, error glyph)."""
    ThemedMessageDialog(title, message, parent=parent, kind="error").exec()


def themed_confirm(parent, title, message, *, danger: bool = False,
                   ok_label: str = "Yes",
                   cancel_label: str = "No") -> bool:
    """Show a themed Yes/No (or custom-labelled) confirmation dialog.

    The first three positional parameters are identical to the original
    3-argument signature so every existing call site continues to work.
    The keyword-only parameters are all optional additions.

    Args:
        parent:       Qt parent widget.
        title:        Dialog / header title.
        message:      Body text / question.
        danger:       When ``True``, the confirm button gets danger styling.
        ok_label:     Label for the affirmative button (default ``"Yes"``).
        cancel_label: Label for the dismissive button (default ``"No"``).

    Returns:
        ``True`` iff the user accepted; ``False`` on cancel / close.
    """
    dlg = ThemedMessageDialog(title, message, parent=parent)
    if ok_label == "Yes" and cancel_label == "No" and not danger:
        dlg._make_yes_no()
    else:
        dlg._make_confirm(ok_label, cancel_label, danger)
    return dlg.exec() == QDialog.DialogCode.Accepted


def themed_input_text(parent, title, label, *, initial: str = "") -> tuple[str, bool]:
    """Show a text-input dialog, returning ``(text, True)`` on accept.

    Args:
        parent:  Qt parent widget.
        title:   Dialog / header title.
        label:   Field caption shown above the input.
        initial: Pre-filled text value.

    Returns:
        ``(text, True)`` when accepted; ``(initial, False)`` on cancel.
    """
    dlg = ThemedMessageDialog(title, "", parent=parent)
    edit = QLineEdit()
    edit.setText(initial)
    dlg._add_input_widget(label, edit)
    dlg._clear_footer()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dlg.reject)
    dlg.set_footer_buttons(primary=("OK", dlg.accept), cancel=False,
                           extra_left=cancel_btn)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        return edit.text(), True
    return initial, False


def themed_input_number(parent, title, label, *, initial: float,
                        dimension: bool = True,
                        minimum: float | None = None,
                        maximum: float | None = None) -> tuple[float, bool]:
    """Show a numeric-input dialog, returning ``(value, True)`` on accept.

    When ``dimension=True`` a :class:`DimensionEdit` widget is used
    (project unit display, parses any supported unit string); the
    ``initial`` value is treated as millimetres — the widget's native unit.
    When ``dimension=False`` a plain ``QLineEdit`` with a
    ``QDoubleValidator`` is used; ``initial`` is a plain float.

    Args:
        parent:    Qt parent widget.
        title:     Dialog / header title.
        label:     Field caption shown above the input.
        initial:   Seed value (mm for dimension=True, float for False).
        dimension: ``True`` to use DimensionEdit; ``False`` for plain float.
        minimum:   Optional lower bound; returned value is clamped to this.
        maximum:   Optional upper bound; returned value is clamped to this.

    Returns:
        ``(float_value, True)`` when accepted; ``(initial, False)`` on cancel.
        Accepted values are clamped to [minimum, maximum] when those are given.
    """
    dlg = ThemedMessageDialog(title, "", parent=parent)

    if dimension:
        # DimensionEdit with no ScaleManager → falls back to plain "N.NN mm"
        # display.  Seeded with initial_mm=initial.
        edit: DimensionEdit | QLineEdit = DimensionEdit(None, initial_mm=initial)
    else:
        edit = QLineEdit()
        edit.setText(str(initial))
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        if minimum is not None and maximum is not None:
            validator.setRange(minimum, maximum, 10)
        edit.setValidator(validator)

    dlg._add_input_widget(label, edit)
    dlg._clear_footer()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dlg.reject)
    dlg.set_footer_buttons(primary=("OK", dlg.accept), cancel=False,
                           extra_left=cancel_btn)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        if dimension:
            assert isinstance(edit, DimensionEdit)
            edit.commit()
            value = edit.value_mm()
        else:
            assert isinstance(edit, QLineEdit)
            try:
                value = float(edit.text())
            except ValueError:
                value = initial
        # Clamp to bounds (guaranteed regardless of validator path)
        if minimum is not None:
            value = max(value, minimum)
        if maximum is not None:
            value = min(value, maximum)
        return value, True
    return initial, False


def themed_choice(parent, title, message, buttons, *, kind=None):
    """N-button themed modal.

    Args:
        parent:   Qt parent widget.
        title:    Dialog / header title.
        message:  Body text.
        buttons:  List of ``(label, key, variant)`` tuples laid out left→right.
                  Put the primary/affirmative button last so it lands rightmost.
                  ``variant`` is ``"primary"``, ``"danger"``, or ``None``.
        kind:     Optional ``"info"`` / ``"warn"`` / ``"error"`` icon glyph.

    Returns:
        The chosen key string, or ``None`` if the dialog was closed without
        choosing (Escape / window-close).
    """
    dlg = ThemedMessageDialog(title, message, parent=parent, kind=kind)
    result = {"key": None}
    dlg._make_choice(buttons, result)
    dlg.exec()
    return result["key"]


def themed_input_choice(parent, title, label, items: list[str], *,
                        current: int = 0) -> tuple[str, bool]:
    """Show a drop-down choice dialog, returning ``(selected, True)`` on accept.

    Args:
        parent:  Qt parent widget.
        title:   Dialog / header title.
        label:   Field caption shown above the combo box.
        items:   List of string options.
        current: Index of the initially selected item.

    Returns:
        ``(items[index], True)`` when accepted; ``(items[current], False)`` on
        cancel.  Falls back to ``""`` when ``items`` is empty.
    """
    dlg = ThemedMessageDialog(title, "", parent=parent)
    combo = QComboBox()
    for item in items:
        combo.addItem(item)
    if items:
        combo.setCurrentIndex(max(0, min(current, len(items) - 1)))

    dlg._add_input_widget(label, combo)
    dlg._clear_footer()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dlg.reject)
    dlg.set_footer_buttons(primary=("OK", dlg.accept), cancel=False,
                           extra_left=cancel_btn)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        idx = combo.currentIndex()
        return (items[idx] if items else ""), True
    return (items[current] if items else ""), False
