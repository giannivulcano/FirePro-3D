"""footer_rail.py — tokenized MainWindow status footer (chrome revamp).

Replaces the ad-hoc status-bar pills/labels with a custom widget of three
sub-rails divided by tokenized muted lines:

    [ mode badge + instruction ] ……… │ [ X/Y + node-snap ] │ [ SNAP + osnaps + ALIGN + HALO ]

The inline osnap bar hosts one checkable icon toggle per snap type (icons
matching ``snap_engine.SNAP_MARKERS``); state reads/writes the same
``snap/{attr}`` QSettings keys + the live ``SnapEngine`` booleans as the
retired dockable toolbar did. Everything is theme-token driven (no raw hex).
See docs/specs/mainwindow-chrome-revamp.md.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame, QToolButton,
)
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import Qt, QSize, QByteArray, QSettings, pyqtSignal

from .theme import detect, M
from .assets import asset_path
from .svg_utils import svg_recolor
from .icons import PRIMARY_SENTINEL

_QORG, _QAPP = "GV", "FirePro3D"

# (marker-key [== snap_engine.SNAP_MARKERS key], SnapEngine attr, tooltip).
# Order MUST match snap_engine.SNAP_MARKERS.
_OSNAP: list[tuple[str, str, str]] = [
    ("endpoint",     "snap_endpoint",     "Endpoint — snaps to the end of a line or arc"),
    ("midpoint",     "snap_midpoint",     "Midpoint — snaps to the middle of a segment"),
    ("intersection", "snap_intersection", "Intersection — snaps where two edges cross"),
    ("center",       "snap_center",       "Center — snaps to the centre of a circle or arc"),
    ("quadrant",     "snap_quadrant",     "Quadrant — snaps to the 0/90/180/270° points of a circle"),
    ("nearest",      "snap_nearest",      "Nearest — snaps to the closest point on an edge"),
    ("perpendicular","snap_perpendicular","Perpendicular — snaps to the right-angle foot on an edge"),
    ("tangent",      "snap_tangent",      "Tangent — snaps to a tangent point on a circle or arc"),
]


def _osnap_icon(marker_key: str, color: str) -> QIcon:
    """Render ``snap_<marker_key>.svg`` recoloured to a single flat *color*."""
    path = asset_path("Ribbon", f"snap_{marker_key}.svg")
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    data = svg_recolor(raw, {PRIMARY_SENTINEL: color})
    r = QSvgRenderer(QByteArray(data))
    pm = QPixmap(QSize(32, 32))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    return QIcon(pm)


def _vsep() -> QFrame:
    f = QFrame()
    f.setFixedWidth(M.SEAM)
    f.setStyleSheet(f"background:{detect().line}; border:none;")
    return f


def _pill_style(on: bool) -> str:
    """Accent pill QSS (bare properties, so it applies to BOTH the QToolButton
    pills AND the QLabel mode badge — a QToolButton{}-scoped rule silently
    no-ops on a QLabel, which is why the mode badge lost its pill look)."""
    t = detect()
    if on:
        return (f"border:1px solid {t.accent}; color:{t.accent};"
                f" background:{t.accent_soft}; border-radius:{M.RADIUS_PILL}px;"
                f" padding:2px 10px; font-weight:600;")
    return (f"border:1px solid {t.line}; color:{t.muted};"
            f" background:transparent; border-radius:{M.RADIUS_PILL}px;"
            f" padding:2px 10px; font-weight:600;")


class _OsnapToggle(QToolButton):
    """One checkable osnap icon toggle (accent when on, muted when off)."""

    def __init__(self, marker_key: str, attr: str, tip: str, parent=None):
        super().__init__(parent)
        self.attr = attr
        self.setCheckable(True)
        self.setAutoRaise(False)
        self.setToolTip(tip)
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(26, 26)
        t = detect()
        # Match the pills: checked = accent glyph on the soft-accent (green)
        # fill + accent border; unchecked = muted glyph, no fill.
        self.setStyleSheet(
            f"QToolButton{{border:1px solid transparent;"
            f" border-radius:{M.RADIUS_CHIP}px; background:transparent;}}"
            f"QToolButton:checked{{background:{t.accent_soft};"
            f" border:1px solid {t.accent};}}")
        self._on_icon = _osnap_icon(marker_key, t.accent)
        self._off_icon = _osnap_icon(marker_key, t.muted)
        self.toggled.connect(self._sync_icon)

    def _sync_icon(self, on: bool) -> None:
        self.setIcon(self._on_icon if on else self._off_icon)

    def apply_state(self, on: bool) -> None:
        self.blockSignals(True)
        self.setChecked(on)
        self._sync_icon(on)
        self.blockSignals(False)


class InlineOsnapBar(QWidget):
    """Row of per-type osnap toggles; single source of truth = SnapEngine attrs."""

    osnapChanged = pyqtSignal(str, bool)  # (attr, checked)

    def __init__(self, snap_engine_obj=None, parent=None):
        super().__init__(parent)
        self._eng = snap_engine_obj
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(M.FOOTER_OSNAP_GAP)
        self._toggles: dict[str, _OsnapToggle] = {}
        for marker_key, attr, tip in _OSNAP:
            btn = _OsnapToggle(marker_key, attr, tip, self)
            init = bool(getattr(self._eng, attr, True)) if self._eng is not None else True
            btn.apply_state(init)
            btn.toggled.connect(lambda on, a=attr: self._on_toggle(a, on))
            lay.addWidget(btn)
            self._toggles[attr] = btn

    def _on_toggle(self, attr: str, on: bool) -> None:
        if self._eng is not None:
            setattr(self._eng, attr, on)
        QSettings(_QORG, _QAPP).setValue(f"snap/{attr}", on)
        self.osnapChanged.emit(attr, on)

    def marker_keys(self) -> list[str]:
        return [k for k, _, _ in _OSNAP]

    def set_osnap(self, attr: str, on: bool) -> None:
        self._toggles[attr].apply_state(on)
        self._on_toggle(attr, on)

    def refresh_from_engine(self) -> None:
        if self._eng is None:
            return
        for attr, btn in self._toggles.items():
            btn.apply_state(bool(getattr(self._eng, attr, True)))


class FooterRail(QWidget):
    """Custom status footer: mode/instruction │ position │ toggles."""

    snapSettingsRequested = pyqtSignal()

    def __init__(self, snap_engine_obj=None, parent=None):
        super().__init__(parent)
        self._eng = snap_engine_obj
        self.setFixedHeight(M.FOOTER_H)
        # Chrome tone: match the header rail (surface2 / raised). The generic
        # QWidget{background:bg_base} rule otherwise paints the rail ground and
        # covers the raised status bar behind it. Scoped via objectName.
        self.setObjectName("footerRail")
        # WA_StyledBackground: QSS background must paint LIVE on a plain QWidget
        # (see project memory unstyled_qwidget_black_live).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#footerRail {{ background: {detect().surface2}; }}")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sub-rail 1: mode badge + instruction ─────────────────────────────
        s1 = QHBoxLayout()
        s1.setContentsMargins(*M.FOOTER_SUBRAIL_MARGIN)
        s1.setSpacing(M.FOOTER_BTN_GAP)
        # Mode badge: a non-interactive QToolButton (not a QLabel) so it matches
        # the ALIGN/HALO pills exactly (a QLabel stretches to the footer height;
        # a QToolButton is the compact 22px pill). Mouse-transparent = no hover.
        self.mode_badge = QToolButton()
        self.mode_badge.setText("SELECT")
        self.mode_badge.setStyleSheet(_pill_style(True))
        self.mode_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.mode_badge.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.instruction = QLabel("")
        self.instruction.setStyleSheet(f"color:{detect().muted};")
        s1.addWidget(self.mode_badge)
        s1.addWidget(self.instruction)
        root.addLayout(s1)
        root.addStretch(1)

        # ── Sub-rail 2: position ─────────────────────────────────────────────
        root.addWidget(_vsep())
        s2 = QHBoxLayout()
        s2.setContentsMargins(*M.FOOTER_SUBRAIL_MARGIN)
        s2.setSpacing(M.FOOTER_BTN_GAP)
        self.coord = QLabel("X: —   Y: —")
        self.coord.setStyleSheet(f"color:{detect().text_primary}; font-family:Consolas;")
        self.node_chip = QLabel("")
        self.node_chip.setStyleSheet(f"color:{detect().warn}; font-family:Consolas;")
        self.node_chip.hide()
        s2.addWidget(self.coord)
        s2.addWidget(self.node_chip)
        root.addLayout(s2)

        # ── Sub-rail 3: toggles (SNAP + osnaps + chevron + ALIGN + HALO) ──────
        root.addWidget(_vsep())
        s3 = QHBoxLayout()
        s3.setContentsMargins(*M.FOOTER_SUBRAIL_MARGIN)
        s3.setSpacing(M.FOOTER_TOGGLE_GAP)
        self.snap_pill = QToolButton()
        self.snap_pill.setText("SNAP")
        self.snap_pill.setCheckable(True)
        self.snap_pill.setStyleSheet(_pill_style(True))
        self.snap_pill.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.snap_pill.customContextMenuRequested.connect(
            lambda _p: self.snapSettingsRequested.emit())
        s3.addWidget(self.snap_pill)

        self.osnap_bar = InlineOsnapBar(snap_engine_obj, self)
        s3.addWidget(self.osnap_bar)

        self.chevron = QToolButton()
        self.chevron.setAutoRaise(True)
        self._expanded = QSettings(_QORG, _QAPP).value("snap/bar_expanded", True, type=bool)
        self.chevron.clicked.connect(self._toggle_bar)
        s3.addWidget(self.chevron)
        self._apply_bar_expanded()

        self.align_pill = QToolButton()
        self.align_pill.setText("ALIGN")
        self.align_pill.setCheckable(True)
        self.align_pill.setStyleSheet(_pill_style(False))
        s3.addWidget(self.align_pill)

        self.halo_pill = QToolButton()
        self.halo_pill.setText("HALO")
        self.halo_pill.setCheckable(True)
        self.halo_pill.setStyleSheet(_pill_style(True))
        s3.addWidget(self.halo_pill)
        root.addLayout(s3)

    # ── osnap API (used by tests + main wiring) ──────────────────────────────
    def osnap_toggle_keys(self) -> list[str]:
        return self.osnap_bar.marker_keys()

    def set_osnap(self, attr: str, on: bool) -> None:
        self.osnap_bar.set_osnap(attr, on)

    # ── chevron collapse/expand ──────────────────────────────────────────────
    def _apply_bar_expanded(self) -> None:
        self.osnap_bar.setVisible(self._expanded)
        self.chevron.setText("−" if self._expanded else "+")   # − / +
        self.chevron.setToolTip("Collapse snap bar" if self._expanded else "Expand snap bar")

    def _toggle_bar(self) -> None:
        self._expanded = not self._expanded
        QSettings(_QORG, _QAPP).setValue("snap/bar_expanded", self._expanded)
        self._apply_bar_expanded()

    # ── readout setters (wired to scene signals by MainWindow) ───────────────
    def set_coord(self, text: str) -> None:
        self.coord.setText(text)

    def set_mode(self, name: str) -> None:
        self.mode_badge.setText((name or "Select").upper())

    def set_instruction(self, text: str) -> None:
        self.instruction.setText(text or "")

    def set_node_snap(self, text: str) -> None:
        self.node_chip.setText(text or "")
        self.node_chip.setVisible(bool(text))

    def set_snap_on(self, on: bool) -> None:
        self.snap_pill.setChecked(on)
        self.snap_pill.setStyleSheet(_pill_style(on))
        self.osnap_bar.setEnabled(on)

    def set_align_on(self, on: bool) -> None:
        self.align_pill.setChecked(on)
        self.align_pill.setStyleSheet(_pill_style(on))

    def set_halo_on(self, on: bool) -> None:
        self.halo_pill.setChecked(on)
        self.halo_pill.setStyleSheet(_pill_style(on))
