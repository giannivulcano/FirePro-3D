"""App-wide tooltip wrapping (ET1 Q8; ui-design-system.md "Tooltips").

Qt never wraps a plain-text tooltip. One ``QApplication`` event filter sees
every widget's ``QEvent.ToolTip`` before the widget does; when the widget's
plain tip has a line wider than ``TOOLTIP_MAX_PX`` it shows the same text as
width-capped rich text (``<table width>`` is the one form Qt wraps at exactly
the cap; a newline becomes ``<br>``) and consumes the event. Every shorter
tip -- and any tip already authored as rich text -- is left to the widget,
so it renders exactly as before. Graphics-item tips (the view's viewport
has an empty ``toolTip()``) pass through.
"""
from __future__ import annotations

import html

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QToolTip, QWidget

from .constants import TOOLTIP_MAX_PX


def wrap(text: str, cap: int = TOOLTIP_MAX_PX) -> str | None:
    """Width-capped rich text for *text*, or None when it needs no wrap.

    Args:
        text: A widget's plain tooltip (newlines = authored breaks).
        cap: Maximum line width in px at the tooltip font.

    Returns:
        ``<table width='cap'><tr><td>...</td></tr></table>`` with the text
        HTML-escaped and newlines as ``<br>``; None for an empty text, a
        rich-text tip (``Qt.mightBeRichText``) or one whose every line
        already fits.
    """
    if not text or Qt.mightBeRichText(text):
        return None
    fm = QFontMetrics(QToolTip.font())
    if max(fm.horizontalAdvance(line) for line in text.split("\n")) <= cap:
        return None
    body = html.escape(text).replace("\n", "<br>")
    return f"<table width='{cap}'><tr><td>{body}</td></tr></table>"


class _Filter(QObject):
    """The application event filter (one instance per app, ``install``)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.ToolTip and isinstance(obj, QWidget):
            rich = wrap(obj.toolTip())
            if rich is not None:
                QToolTip.showText(ev.globalPos(), rich, obj, obj.rect())
                return True
        return False


_FILTERS: dict = {}     # id(app) -> _Filter (so uninstall finds it; tests)


def install(app) -> None:
    """Install the wrap filter on *app* (idempotent)."""
    if id(app) in _FILTERS:
        return
    f = _Filter(app)
    app.installEventFilter(f)
    _FILTERS[id(app)] = f


def uninstall(app) -> None:
    """Remove the filter from *app* (tests)."""
    f = _FILTERS.pop(id(app), None)
    if f is not None:
        app.removeEventFilter(f)
        f.deleteLater()
