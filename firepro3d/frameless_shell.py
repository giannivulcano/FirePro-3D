"""
frameless_shell.py
==================
Reusable frameless-window shell primitives for FirePro 3D dialogs.

Extracted from ``underlay_import_dialog.py`` so the custom-chrome look (a single
themed header replacing the OS title bar, Win11 DWM rounded corners, header
drag-to-move, double-click-header maximize/restore, and the round min/max/close
control dots) can be shared with other frameless windows — notably the
resizable, modeless Underlay Manager.

Provides:

* ``_winctl_pixmap`` / ``_WinDot`` — the round window-control dots (grey circle
  + accent inlay; circle brightens on hover).
* ``FramelessShellMixin`` — mix into a ``QDialog`` (or ``QWidget``) to get
  frameless flags, a draggable custom titlebar, maximize toggle, DWM rounded
  corners, and OPTIONAL resize edges (``resizable=True``).

Behaviour contract (mirrors the original import-dialog chrome):

* The drag handlers only move the window when the press lands inside
  ``self._titlebar.geometry()``.
* ``mouseDoubleClickEvent`` on the titlebar toggles maximize/restore.
* Resize handlers are no-ops unless ``self._resizable`` and the press is within
  ``_RESIZE_MARGIN`` of a window edge (and the window is not maximized).

A host may either let the mixin build a plain titlebar (via
``init_frameless_shell(..)`` → ``_build_titlebar``) or build its own richer
``self._titlebar`` (icon + title + control dots) and skip the mixin's builder;
in the latter case the host is responsible for populating ``self._win_controls``.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QPushButton, QFrame, QHBoxLayout, QLabel
from PyQt6.QtGui import QPainter, QPixmap, QIcon
from PyQt6.QtCore import Qt, QSize, QByteArray
from PyQt6.QtSvg import QSvgRenderer

from .theme import detect


_WINCTL_INLAY = {
    "min":   '<path d="M7 12 H17"/>',
    "max":   '<path d="M12 7 V17 M7 12 H17"/>',
    "close": '<path d="M8.5 8.5 L15.5 15.5 M15.5 8.5 L8.5 15.5"/>',
}


def _winctl_pixmap(kind: str, circle: str, inlay: str, px: int = 16) -> QPixmap:
    """Render a window-control icon: grey circle + accent inlay."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'<circle cx="12" cy="12" r="11" fill="{circle}"/>'
           f'<g stroke="{inlay}" stroke-width="2.2" stroke-linecap="round"'
           f' fill="none">{_WINCTL_INLAY[kind]}</g></svg>')
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    return pm


class _WinDot(QPushButton):
    """A window-control dot (min/max/close): accent inlay on a grey circle;
    the circle brightens on hover."""
    def __init__(self, kind: str, slot, theme, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QPushButton{border:none;background:transparent;}")
        self._normal = QIcon(_winctl_pixmap(kind, theme.line_strong, theme.accent, 18))
        self._hover = QIcon(_winctl_pixmap(kind, theme.faint, theme.accent, 18))
        self.setIcon(self._normal)
        self.clicked.connect(slot)

    def enterEvent(self, e):
        self.setIcon(self._hover)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setIcon(self._normal)
        super().leaveEvent(e)


class FramelessShellMixin:
    """Frameless-window chrome for a QDialog/QWidget host.

    Mix in *before* the Qt base class so the event overrides here take
    precedence, e.g. ``class Foo(FramelessShellMixin, QDialog)``. The mixin has
    no ``__init__`` — the Qt base's ``__init__`` runs via normal MRO — so hosts
    must call :meth:`init_frameless_shell` from their own ``__init__``.
    """

    _RESIZE_MARGIN = 6

    # ── setup ────────────────────────────────────────────────────────────────
    def init_frameless_shell(self, title, controls=("close",), resizable=False,
                             build_titlebar=True):
        """Apply frameless flags and initialise shell state.

        Args:
            title: Window title (also used for the mixin-built titlebar label).
            controls: Ordered subset of ("min", "max", "close") to show.
            resizable: If True, enable resize-edge dragging + mouse tracking.
            build_titlebar: If True, build ``self._titlebar`` here. Hosts that
                build their own richer titlebar (icon + title + dots) should
                pass ``False`` and populate ``self._win_controls`` themselves.
        """
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.Dialog)
        self.setWindowTitle(title)
        self._drag_pos = None
        self._resizable = resizable
        self._resize_edge = None
        self._resize_origin = None
        self._resize_geom = None
        self._win_controls = {}
        if resizable:
            self.setMouseTracking(True)
        if build_titlebar:
            self._titlebar = self._build_titlebar(title, controls)

    def _build_titlebar(self, title, controls):
        """Build a plain themed titlebar: title label + control dots.

        Returns a ``QFrame`` (objectName ``importHeader`` to inherit the shared
        chrome QSS). Populates ``self._win_controls``.
        """
        t = detect()
        bar = QFrame(objectName="importHeader")
        bar.setFixedHeight(40)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(14, 7, 10, 7)
        self._shell_title_lbl = QLabel(title)
        self._shell_title_lbl.setStyleSheet(
            f"color:{t.ink}; font-size:14px; font-weight:700; background:transparent;")
        hb.addWidget(self._shell_title_lbl)
        hb.addStretch(1)
        _vc = Qt.AlignmentFlag.AlignVCenter
        _slots = {"min": self.showMinimized,
                  "max": self._toggle_max,
                  "close": self._shell_close}
        for _k in controls:
            dot = _WinDot(_k, _slots[_k], t)
            self._win_controls[_k] = dot
            hb.addWidget(dot, 0, _vc)
        return bar

    def _shell_close(self):
        """Default close slot (reject if available, else close)."""
        rej = getattr(self, "reject", None)
        if callable(rej):
            rej()
        else:
            self.close()

    def set_shell_title(self, text):
        """Update the mixin-built titlebar's title label (if present)."""
        self.setWindowTitle(text)
        lbl = getattr(self, "_shell_title_lbl", None)
        if lbl is not None:
            lbl.setText(text)

    # ── maximize toggle ──────────────────────────────────────────────────────
    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ── drag + resize ────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        if (self._resizable and event.button() == Qt.MouseButton.LeftButton
                and not self.isMaximized()):
            edge = self._edge_at(pos)
            if edge:
                self._resize_edge = edge
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_geom = self.geometry()
                event.accept()
                return
        tb = getattr(self, "_titlebar", None)
        if (tb is not None and event.button() == Qt.MouseButton.LeftButton
                and tb.geometry().contains(pos)):
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizable and self._resize_edge is not None:
            self._perform_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if (self._drag_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        if self._resizable and not (event.buttons() & Qt.MouseButton.LeftButton):
            self._update_resize_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        self._resize_origin = None
        self._resize_geom = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        tb = getattr(self, "_titlebar", None)
        if tb is not None and tb.geometry().contains(event.position().toPoint()):
            self._toggle_max()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ── resize helpers ───────────────────────────────────────────────────────
    def _edge_at(self, pos):
        """Return an edge string ("l"/"r"/"t"/"b" combos) if *pos* is within
        ``_RESIZE_MARGIN`` of a window edge, else None."""
        if not self._resizable or self.isMaximized():
            return None
        m = self._RESIZE_MARGIN
        r = self.rect()
        left = pos.x() <= m
        right = pos.x() >= r.width() - m
        top = pos.y() <= m
        bottom = pos.y() >= r.height() - m
        edge = ""
        if top:
            edge += "t"
        elif bottom:
            edge += "b"
        if left:
            edge += "l"
        elif right:
            edge += "r"
        return edge or None

    def _update_resize_cursor(self, pos):
        edge = self._edge_at(pos)
        cursors = {
            "t": Qt.CursorShape.SizeVerCursor,
            "b": Qt.CursorShape.SizeVerCursor,
            "l": Qt.CursorShape.SizeHorCursor,
            "r": Qt.CursorShape.SizeHorCursor,
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
        }
        if edge in cursors:
            self.setCursor(cursors[edge])
        else:
            self.unsetCursor()

    def _perform_resize(self, gpos):
        if self._resize_geom is None or self._resize_origin is None:
            return
        dx = gpos.x() - self._resize_origin.x()
        dy = gpos.y() - self._resize_origin.y()
        g = self._resize_geom
        left, top = g.left(), g.top()
        right, bottom = g.right(), g.bottom()
        edge = self._resize_edge or ""
        min_w = max(self.minimumWidth(), 1)
        min_h = max(self.minimumHeight(), 1)
        if "l" in edge:
            left = min(left + dx, right - min_w)
        if "r" in edge:
            right = max(right + dx, left + min_w)
        if "t" in edge:
            top = min(top + dy, bottom - min_h)
        if "b" in edge:
            bottom = max(bottom + dy, top + min_h)
        self.setGeometry(left, top, right - left, bottom - top)

    # ── DWM rounded corners ──────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._enable_rounded_corners()

    def _enable_rounded_corners(self):
        """Win11 DWM rounded corners for the frameless window (matches the
        native-framed Underlay Manager). No-op / harmless elsewhere."""
        try:
            import ctypes
            hwnd = int(self.winId())
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            val = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass
