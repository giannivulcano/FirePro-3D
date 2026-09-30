"""Empty-canvas placeholder shown when every canvas tab is closed.

Governed by ``docs/specs/view-3d.md`` §10 I5; visual values are the
mockup-approved ``theme.M.EMPTY_CANVAS_*`` tokens. Text sizes live in each
label's own QSS — ``setFont`` loses to the app QSS ``QWidget { font-size }``.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from . import theme as th
from .theme import M


class EmptyCanvasPlaceholder(QWidget):
    """Message + quick buttons over an empty canvas rail and ground pane.

    Signals:
        open3DRequested: the "3D Model" button was clicked.
        openPlanRequested: the "Plan: <level>" button was clicked.
    """

    open3DRequested = pyqtSignal()
    openPlanRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        t = th.detect()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Empty tab rail + divider: keeps the dock-header dividers landing on
        # the canvas divider row (#centralTabs' bar collapses to 0 px empty).
        self._rail = QWidget()
        self._rail.setObjectName("emptyCanvasRail")
        self._rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._rail.setStyleSheet(f"#emptyCanvasRail {{ background: {t.surface}; }}")
        root.addWidget(self._rail)
        div = QFrame()
        div.setObjectName("emptyCanvasDivider")
        div.setFixedHeight(M.EMPTY_CANVAS_DIVIDER_H)
        div.setStyleSheet(f"#emptyCanvasDivider {{ background: {t.line_strong}; }}")
        root.addWidget(div)

        pane = QWidget()
        pane.setObjectName("emptyCanvasPane")
        pane.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pane.setStyleSheet(f"#emptyCanvasPane {{ background: {t.ground}; }}")
        root.addWidget(pane, 1)
        pl = QVBoxLayout(pane)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)

        self._title = QLabel("No views open")
        self._title.setObjectName("emptyCanvasTitle")
        self._title.setStyleSheet(
            f"#emptyCanvasTitle {{ font-size: {M.EMPTY_CANVAS_TITLE_PT}pt;"
            f" font-weight: bold; color: {t.ink}; background: transparent; }}")
        self._hint = QLabel("Open a view from the Project Browser")
        self._hint.setObjectName("emptyCanvasHint")
        self._hint.setStyleSheet(
            f"#emptyCanvasHint {{ font-size: {M.EMPTY_CANVAS_HINT_PT}pt;"
            f" color: {t.muted}; background: transparent; }}")
        for lbl in (self._title, self._hint):
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._btn_3d = QPushButton("3D Model")
        self._btn_3d.setToolTip("Open the 3D Model view")
        self._btn_plan = QPushButton("Plan")
        self._btn_plan.setToolTip("Open the plan view of the active level")
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(M.EMPTY_CANVAS_BTN_GAP)
        btns.addStretch(1)
        for b in (self._btn_3d, self._btn_plan):
            b.setMinimumWidth(M.EMPTY_CANVAS_BTN_MIN_W)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            btns.addWidget(b)
        btns.addStretch(1)
        self._btn_3d.clicked.connect(self.open3DRequested)
        self._btn_plan.clicked.connect(self.openPlanRequested)

        pl.addStretch(M.EMPTY_CANVAS_CENTRE_PCT)
        pl.addWidget(self._title)
        pl.addSpacing(M.EMPTY_CANVAS_GAP_HINT)
        pl.addWidget(self._hint)
        pl.addSpacing(M.EMPTY_CANVAS_GAP_BUTTONS)
        pl.addLayout(btns)
        pl.addStretch(100 - M.EMPTY_CANVAS_CENTRE_PCT)

    def set_rail_height(self, px: int) -> None:
        """Match the empty rail to the canvas tab bar's height."""
        self._rail.setFixedHeight(px)

    def set_active_level(self, name: str) -> None:
        """Label the plan quick button ``Plan: <name>``."""
        self._btn_plan.setText(f"Plan: {name}")
