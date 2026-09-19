"""header_rail.py — tokenized MainWindow header rail (chrome revamp).

Replaces the OS title bar / menu area with a custom widget (installed via
``QMainWindow.setMenuWidget``) carrying app identity, the Save/Undo/Redo
actions migrated off the ribbon Edit group, the current project name + an
unsaved-changes ``●`` dot, and the frameless window-control dots.

Approved v3 order:

    [icon] FirePro 3D (v9.9) │ Save Undo Redo │ Project ●  ……  – ▢ ✕

Everything is theme-token driven (no raw hex). See
docs/specs/mainwindow-chrome-revamp.md.
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame, QToolButton,
)
from PyQt6.QtGui import QIcon, QPixmap, QFontMetrics
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from .theme import detect, M
from .assets import asset_path
from .icons import themed_icon
from .frameless_shell import _WinDot

_PROJECT_MAXW = 320   # px budget for the middle-elided project label


def _theme_variant() -> str:
    return "light" if detect().name == "light" else "dark"


def _vsep() -> QFrame:
    f = QFrame()
    f.setFixedWidth(M.SEAM)
    f.setStyleSheet(f"background:{detect().line}; border:none;")
    return f


def _action_button(icon_name: str, tip: str) -> QToolButton:
    """A 26px flat header action button (Save/Undo/Redo)."""
    b = QToolButton()
    b.setAutoRaise(True)
    b.setFixedSize(26, 26)
    b.setIconSize(QSize(17, 17))
    b.setToolTip(tip)
    b.setIcon(themed_icon(icon_name, _theme_variant()))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class HeaderRail(QWidget):
    """Custom header: identity │ Save/Undo/Redo │ project ● … window dots."""

    saveRequested = pyqtSignal()
    undoRequested = pyqtSignal()
    redoRequested = pyqtSignal()
    minimizeRequested = pyqtSignal()
    maximizeRequested = pyqtSignal()
    closeRequested = pyqtSignal()

    def __init__(self, app_version: str = "", parent=None):
        super().__init__(parent)
        t = detect()
        self.setFixedHeight(M.HEADER_H)
        self._project_name = ""
        self._project_path = ""
        self._drag_offset = None   # window-drag anchor (frameless move-by-header)
        root = QHBoxLayout(self)
        root.setContentsMargins(*M.HEADER_MARGIN)
        root.setSpacing(0)
        _vc = Qt.AlignmentFlag.AlignVCenter

        # ── Identity: app icon + name + version ──────────────────────────────
        self._icon = QLabel()
        _logo = asset_path("Program Icon", "Logo.png")
        if os.path.isfile(_logo):
            self._icon.setPixmap(QPixmap(_logo).scaled(
                M.HEADER_ICON, M.HEADER_ICON,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        root.addWidget(self._icon, 0, _vc)
        root.addSpacing(M.HEADER_ICON_GAP)

        self._title = QLabel("FirePro 3D")
        self._title.setProperty("role", "title")
        self._title.setStyleSheet(f"color:{t.text_primary}; font-weight:600;")
        root.addWidget(self._title, 0, _vc)
        if app_version:
            ver = QLabel(f"(v{app_version})")
            ver.setStyleSheet(f"color:{t.muted};")
            root.addSpacing(M.XS)
            root.addWidget(ver, 0, _vc)

        root.addSpacing(M.HEADER_TITLE_GAP)
        root.addWidget(_vsep(), 0, _vc)
        root.addSpacing(M.HEADER_TITLE_GAP)

        # ── Actions: Save / Undo / Redo (migrated off the ribbon Edit group) ──
        self._save = _action_button("save_icon.svg", "Save [Ctrl+S]")
        self._undo = _action_button("undo_icon.svg", "Undo [Ctrl+Z]")
        self._redo = _action_button("redo_icon.svg", "Redo [Ctrl+Y]")
        self._save.clicked.connect(self.saveRequested)
        self._undo.clicked.connect(self.undoRequested)
        self._redo.clicked.connect(self.redoRequested)
        for b in (self._save, self._undo, self._redo):
            root.addWidget(b, 0, _vc)

        root.addSpacing(M.HEADER_TITLE_GAP)
        root.addWidget(_vsep(), 0, _vc)
        root.addSpacing(M.HEADER_TITLE_GAP)

        # ── Project name + unsaved ● dot ─────────────────────────────────────
        self._project = QLabel("")
        self._project.setStyleSheet(f"color:{t.muted};")
        root.addWidget(self._project, 0, _vc)
        self._dirty = QLabel("●")   # ●
        self._dirty.setStyleSheet(f"color:{t.accent};")
        self._dirty.hide()
        root.addSpacing(M.XS)
        root.addWidget(self._dirty, 0, _vc)

        root.addStretch(1)

        # ── Window-control dots (frameless) ──────────────────────────────────
        self._dots = {
            "min": _WinDot("min", self.minimizeRequested.emit, t),
            "max": _WinDot("max", self.maximizeRequested.emit, t),
            "close": _WinDot("close", self.closeRequested.emit, t),
        }
        for _k in ("min", "max", "close"):
            root.addWidget(self._dots[_k], 0, _vc)

    # ── window drag (frameless move-by-header) ───────────────────────────────
    # Clicks on the action/window buttons are consumed by those QToolButtons and
    # never reach here; clicks on the labels / empty header propagate up and
    # start a window drag — but only when the window is restored (not
    # maximized/fullscreen), matching native title-bar behaviour.
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if win is not None and not (win.isMaximized() or win.isFullScreen()):
                self._drag_offset = (event.globalPosition().toPoint()
                                     - win.frameGeometry().topLeft())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_offset is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click the header toggles fullscreen ↔ restore (native feel)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximizeRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ── project / dirty state ────────────────────────────────────────────────
    def set_project(self, name: str, path: str = "", dirty: bool = False) -> None:
        """Set the project label (middle-elided, full path as tooltip) + ● dot."""
        self._project_name = name or ""
        self._project_path = path or ""
        fm = QFontMetrics(self._project.font())
        elided = fm.elidedText(self._project_name, Qt.TextElideMode.ElideMiddle,
                               _PROJECT_MAXW)
        self._project.setText(elided)
        self._project.setToolTip(self._project_path or self._project_name)
        self._dirty.setVisible(bool(dirty))

    def project_text(self) -> str:
        """Return the full (un-elided) project name."""
        return self._project_name

    def is_dirty_shown(self) -> bool:
        return not self._dirty.isHidden()

    # ── action enabled-state ─────────────────────────────────────────────────
    def set_undo_enabled(self, on: bool) -> None:
        self._undo.setEnabled(bool(on))

    def set_redo_enabled(self, on: bool) -> None:
        self._redo.setEnabled(bool(on))

    # ── accessors (tests + MainWindow wiring) ────────────────────────────────
    def save_button(self) -> QToolButton:
        return self._save

    def undo_button(self) -> QToolButton:
        return self._undo

    def redo_button(self) -> QToolButton:
        return self._redo
