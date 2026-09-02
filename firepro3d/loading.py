"""Staged loading overlay for the Import Underlay dialog.

While a source loads, a small card floats over the preview and narrates what
the importer is doing — read, scan, extract, clip — with each stage leaving
its result behind as it finishes ("6 pages · 34″ × 22″",
"3 layers · 234 entities"). A slow load stops feeling frozen because the
stage taking the time is named, and the facts double as a first sanity check
before the drawing even appears. Cancel returns to Source having touched
nothing.

Threading contract
-------------------
:class:`LoadProgress` is handed to whatever runs the load on a worker thread.
The loader calls its ``begin`` / ``stage`` / ``done`` methods from that
thread; the signals cross to the GUI thread as queued connections, so the
overlay updates safely.  Call :meth:`LoadProgress.is_cancelled` between chunks
of work and raise :class:`LoadCancelled` (or simply let :meth:`LoadProgress.stage`
raise it for you) so Cancel actually stops the work, not just the window.

Never pump the event loop from any widget here (the guard test enforces this
by name) — the overlay is driven from worker-signal handlers dispatched by the
event loop; pumping would re-enter the loop and recurse until the C stack
overflows.  The widgets rely on cross-thread queued signals + ``update()``
instead, which is safe.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .theme import Theme, detect


class LoadCancelled(Exception):
    """Raised inside a staged load when the user cancels."""


class LoadProgress(QObject):
    """Thread-safe reporter handed to a staged loader.

    The loader calls it from the worker thread; the signals cross to the GUI
    thread as queued connections, so the overlay updates safely.
    """

    began = pyqtSignal(int)          # expected stage count (progress bar)
    stageStarted = pyqtSignal(str)   # label
    stageDone = pyqtSignal(str)      # fact left behind ("2.1 MB", "6 pages …")

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._cancel = threading.Event()

    # -- called by the loader (worker thread) ------------------------------
    def begin(self, expected_stages: int) -> None:
        """Announce the expected stage count (drives the progress bar)."""
        self.began.emit(expected_stages)

    def stage(self, label: str) -> None:
        """Start a stage (adds a row). Raises :class:`LoadCancelled` if cancelled."""
        if self.is_cancelled():
            raise LoadCancelled()
        self.stageStarted.emit(label)

    def done(self, fact: str = "") -> None:
        """Finish the current stage, leaving *fact* behind as its evidence."""
        self.stageDone.emit(fact)

    # -- called by the dialog (GUI thread) ---------------------------------
    def cancel(self) -> None:
        """Request cancellation (GUI thread)."""
        self._cancel.set()

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancel.is_set()


class LoaderWorker(QObject):
    """Runs ``loader.load_staged`` on a QThread; emits exactly one end signal."""

    finished = pyqtSignal(object)    # LoadedSource | None
    cancelled = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, loader, source: str, progress: LoadProgress):
        super().__init__()
        self.loader, self.source, self.progress = loader, source, progress

    def run(self) -> None:
        """Run the staged load, translating its outcome into one end signal."""
        try:
            loaded = self.loader.load_staged(self.source, self.progress)
        except LoadCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:                      # noqa: BLE001 — surfaced as a toast
            self.failed.emit(str(exc))
            return
        if self.progress.is_cancelled():
            self.cancelled.emit()
        else:
            self.finished.emit(loaded)


# ===========================================================================
# widgets
# ===========================================================================

class _Spinner(QWidget):
    """Small rotating arc on a faint track (header spinner)."""

    def __init__(self, theme: Theme, diameter: int = 15, parent=None):
        super().__init__(parent)
        self.t = theme
        self._angle = 0
        self.setFixedSize(diameter, diameter)
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._angle = (self._angle + 24) % 360
        self.update()

    def start(self) -> None:
        """Begin the rotation animation."""
        self._timer.start()

    def stop(self) -> None:
        """Stop the rotation animation."""
        self._timer.stop()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        track = QPen(self.t.color("accent", 55), 2)
        p.setPen(track)
        p.drawEllipse(rect)
        arc = QPen(self.t.color("accent"), 2)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc)
        p.drawArc(rect, -self._angle * 16, 100 * 16)
        p.end()


class _StageIcon(QWidget):
    """Pending dot → running mini-spinner → done check."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.t = theme
        self.state = "pending"
        self._angle = 0
        self.setFixedSize(14, 14)
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._angle = (self._angle + 24) % 360
        self.update()

    def set_state(self, state: str) -> None:
        """Set the icon state: ``pending`` | ``run`` | ``done``."""
        self.state = state
        self._timer.start() if state == "run" else self._timer.stop()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.state == "pending":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.t.color("line_strong"))
            p.drawEllipse(QRectF(4.5, 4.5, 5, 5))
        elif self.state == "run":
            pen = QPen(self.t.color("accent"), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(QRectF(2, 2, 10, 10), -self._angle * 16, 110 * 16)
        else:  # done
            pen = QPen(self.t.color("ok"), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(QPointF(3, 7.6), QPointF(6, 10.4), QPointF(11, 3.8))
        p.end()


class _StageRow(QWidget):
    """icon | label | right-aligned mono fact (appears when the stage ends)."""

    def __init__(self, label: str, theme: Theme, parent=None):
        super().__init__(parent)
        self.state = "pending"
        self._base = label
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)
        self.icon = _StageIcon(theme)
        self.lbl = QLabel(label)
        self.lbl.setProperty("stageLbl", True)
        self.fact = QLabel("")
        self.fact.setProperty("stageFact", True)
        lay.addWidget(self.icon)
        lay.addWidget(self.lbl, 1)
        lay.addWidget(self.fact)

    def set_state(self, state: str, fact: str = "") -> None:
        """Set the row state and, when ``done``, its trailing *fact*."""
        self.state = state
        self.icon.set_state(state)
        self.lbl.setText(self._base + ("…" if state == "run" else ""))
        if state == "done" and fact:
            self.fact.setText(fact)
        self.lbl.setProperty("state", state)
        self.lbl.style().unpolish(self.lbl)
        self.lbl.style().polish(self.lbl)


class _Bar(QWidget):
    """Thin determinate progress bar."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.t = theme
        self._fraction = 0.0
        self.setFixedHeight(3)

    def set_fraction(self, fraction: float) -> None:
        """Set the fill fraction, clamped to ``[0.0, 1.0]``."""
        self._fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.t.color("surface2"))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 3), 1.5, 1.5)
        if self._fraction > 0:
            p.setBrush(self.t.color("accent"))
            p.drawRoundedRect(QRectF(0, 0, self.width() * self._fraction, 3), 1.5, 1.5)
        p.end()


class LoadingOverlay(QFrame):
    """The loading card: header, stage checklist, progress bar, hint + Cancel.

    Parent it to the preview view's viewport; call :meth:`recenter` on resize.
    Colours are pulled from the active house theme (``theme.detect()``).
    """

    cancelRequested = pyqtSignal()

    def __init__(self, theme: Theme | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.t = theme or detect()
        self.setObjectName("loadWin")
        self.setFixedWidth(380)
        self._apply_style()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(11)

        head = QHBoxLayout(); head.setSpacing(9)
        self._spin = _Spinner(self.t)
        self.name_lbl = QLabel(""); self.name_lbl.setObjectName("loadName")
        self.fmt_lbl = QLabel(""); self.fmt_lbl.setObjectName("loadFmt")
        head.addWidget(self._spin)
        head.addWidget(self.name_lbl, 1)
        head.addWidget(self.fmt_lbl)
        lay.addLayout(head)

        self._rows_lay = QVBoxLayout(); self._rows_lay.setSpacing(6)
        lay.addLayout(self._rows_lay)

        self._bar = _Bar(self.t)
        lay.addWidget(self._bar)

        foot = QHBoxLayout(); foot.setSpacing(10)
        self.hint_lbl = QLabel(""); self.hint_lbl.setObjectName("loadHint")
        self.hint_lbl.setWordWrap(True)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancelRequested.emit)
        foot.addWidget(self.hint_lbl, 1)
        foot.addWidget(self.btn_cancel, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(foot)

        self._rows: list[_StageRow] = []
        self._expected = 4
        self._active = False   # explicit — isVisible() is False under a hidden ancestor
        self.hide()

    def is_active(self) -> bool:
        """Return whether a load is currently being narrated.

        Explicit flag rather than ``isVisible()`` — a child of a not-yet-shown
        parent reports ``isVisible() == False`` even after :meth:`show`, which
        would make an idempotent-open guard reset the checklist on every call.
        """
        return self._active

    def _apply_style(self) -> None:
        """Object-scoped QSS so the card reads as a raised panel on the theme."""
        t = self.t
        self.setStyleSheet(f"""
            QFrame#loadWin {{
                background: {t.surface2};
                border: 1px solid {t.line_strong};
                border-radius: 10px;
            }}
            QFrame#loadWin QLabel {{ background: transparent; color: {t.ink}; }}
            QLabel#loadName {{ color: {t.ink}; font-size: 13px; font-weight: 600; }}
            QLabel#loadFmt  {{ color: {t.muted}; font-size: 11px; }}
            QLabel#loadHint {{ color: {t.muted}; font-size: 11px; }}
            QFrame#loadWin QLabel[stageLbl="true"] {{ color: {t.muted}; font-size: 12px; }}
            QFrame#loadWin QLabel[stageLbl="true"][state="run"] {{ color: {t.ink}; }}
            QFrame#loadWin QLabel[stageLbl="true"][state="done"] {{ color: {t.ink}; }}
            QFrame#loadWin QLabel[stageFact="true"] {{
                color: {t.muted}; font-family: "Consolas"; font-size: 11px;
            }}
            QFrame#loadWin QPushButton {{
                background: {t.table}; color: {t.ink};
                border: 1px solid {t.line_strong}; border-radius: 6px;
                padding: 4px 12px;
            }}
            QFrame#loadWin QPushButton:hover {{
                background: {t.accent_soft}; border-color: {t.accent};
            }}
        """)

    # ------------------------------------------------------------------ API
    def begin(self, name: str, fmt_label: str, hint: str) -> None:
        """Reset the checklist and show the card for a fresh load."""
        for row in self._rows:
            self._rows_lay.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        self._expected = 4
        self._active = True
        self.name_lbl.setText(name)
        self.fmt_lbl.setText(fmt_label)
        self.hint_lbl.setText(hint)
        self._bar.set_fraction(0.04)
        self._spin.start()
        self.show()
        self.raise_()
        self.recenter()

    def set_expected(self, count: int) -> None:
        """Set the expected stage count (drives the progress-bar fraction)."""
        self._expected = max(1, count)

    def stage_started(self, label: str) -> None:
        """Finalize the prior running row and add a new running stage row."""
        if self._rows and self._rows[-1].state == "run":
            self._rows[-1].set_state("done")
        row = _StageRow(label, self.t)
        self._rows.append(row)
        self._rows_lay.addWidget(row)
        row.show()                     # rows added while the overlay is already
        row.set_state("run")           # visible are not auto-shown
        self.recenter()

    def stage_done(self, fact: str) -> None:
        """Mark the current stage done, leaving *fact* behind, and advance the bar."""
        if self._rows:
            self._rows[-1].set_state("done", fact)
        done = sum(1 for r in self._rows if r.state == "done")
        self._bar.set_fraction(min(0.96, done / max(self._expected, len(self._rows))))

    def set_fraction(self, fraction: float) -> None:
        """Drive the determinate bar directly (e.g. from a counted phase)."""
        self._bar.set_fraction(fraction)

    def finish(self) -> None:
        """Stop all animations and hide the card."""
        self._active = False
        self._spin.stop()
        for row in self._rows:
            row.icon._timer.stop()          # a cancelled load may leave one running
        self.hide()

    def recenter(self) -> None:
        """Re-center the card over its parent (call from the parent's resize)."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.layout().activate()          # rows are added dynamically — settle first
        self.setFixedHeight(self.layout().sizeHint().height())
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = max(14, int(parent.height() * 0.42) - self.height() // 2)
        self.move(x, y)
