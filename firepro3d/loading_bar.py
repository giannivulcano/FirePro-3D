"""
loading_bar.py
==============
Reusable inline progress bar widget for FirePro 3D.

Provides a styled ``QWidget`` row containing a status label, progress bar,
and optional cancel button.  Supports indeterminate (pulsing) and
determinate (0–100 %) modes.

Usage::

    bar = LoadingBar(parent, cancel=True)
    layout.addWidget(bar)

    bar.start("Reading file…")          # indeterminate
    bar.start_determinate(total, "Extracting…")  # 0-100 %
    bar.update(current)                  # advance
    bar.finish()                         # hide

    if bar.cancelled:                    # poll in extraction loop
        break
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QPushButton, QApplication,
)
from PyQt6.QtCore import pyqtSignal

# ── Shared style ─────────────────────────────────────────────────────────────

_BAR_STYLE = """
    QProgressBar {
        background: #e0e0e0;
        border: none;
        border-radius: 4px;
    }
    QProgressBar::chunk {
        background: #3399ff;
        border-radius: 4px;
    }
"""


class LoadingBar(QWidget):
    """Inline progress bar with status label and optional cancel button.

    Hidden by default.  Call :meth:`start` or :meth:`start_determinate` to
    show, :meth:`finish` to hide.

    Args:
        parent: Parent widget.
        cancel: If ``True``, show a Cancel button that sets :attr:`cancelled`.
    """

    cancel_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, cancel: bool = False):
        super().__init__(parent)
        self.cancelled = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._label = QLabel("")
        lay.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(_BAR_STYLE)
        lay.addWidget(self._bar, 1)

        self._cancel_btn: QPushButton | None = None
        if cancel:
            self._cancel_btn = QPushButton("Cancel")
            self._cancel_btn.clicked.connect(self._on_cancel)
            self._cancel_btn.setEnabled(False)
            lay.addWidget(self._cancel_btn)

        self.setVisible(False)

    # ── Public API ────────────────────────────────────────────────────────

    def start(self, message: str = ""):
        """Show the bar in indeterminate (pulsing) mode.

        Cancel button is disabled during indeterminate operations.
        """
        self.cancelled = False
        self._label.setText(message)
        self._bar.setRange(0, 0)  # indeterminate
        if self._cancel_btn:
            self._cancel_btn.setEnabled(False)
        self.setVisible(True)
        QApplication.processEvents()

    def start_determinate(self, total: int, message: str = ""):
        """Show the bar in determinate mode (0 to *total*).

        Cancel button is enabled during determinate operations.
        """
        self.cancelled = False
        self._label.setText(message)
        self._bar.setRange(0, total)
        self._bar.setValue(0)
        if self._cancel_btn:
            self._cancel_btn.setEnabled(True)
        self.setVisible(True)
        QApplication.processEvents()

    def update(self, current: int, message: str = ""):
        """Advance the bar to *current* and optionally update the message."""
        self._bar.setValue(current)
        if message:
            self._label.setText(message)
        QApplication.processEvents()

    def finish(self):
        """Hide the bar and reset state."""
        self.setVisible(False)

    @property
    def message(self) -> str:
        return self._label.text()

    @message.setter
    def message(self, text: str):
        self._label.setText(text)

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_cancel(self):
        self.cancelled = True
        self.cancel_clicked.emit()
