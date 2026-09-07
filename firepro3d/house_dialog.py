"""house_dialog.py — HouseDialog base for house frameless dialogs.

Owns shell (via FramelessShellMixin) + header (icon+title + optional context
slot) + footer (canonical QDialogButtonBox, Cancel-left/primary-right). The
subclass owns the body via set_body/body_layout. See docs/specs/ui-design-system.md.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFrame, QLabel, QHBoxLayout,
                             QWidget, QDialogButtonBox, QPushButton)

from .frameless_shell import FramelessShellMixin
from .theme import build_dialog_qss, detect, M


class _FooterButtonBox(QObject):
    """Thin lookup/signal carrier replacing QDialogButtonBox in HouseDialog.

    Buttons are placed manually in the footer HBoxLayout so their screen order
    is guaranteed (Cancel-left/primary-right) regardless of platform style.
    This carrier exposes the subset of QDialogButtonBox API used by callers:
      - ``box.button(StandardButton.Cancel)`` → the Cancel QPushButton
      - ``box.rejected`` signal (re-emitted from the Cancel click)
    """

    rejected = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._std_map: dict[QDialogButtonBox.StandardButton, QPushButton] = {}

    def _register(self, std: QDialogButtonBox.StandardButton,
                  btn: QPushButton) -> None:
        self._std_map[std] = btn

    def button(self, std: QDialogButtonBox.StandardButton) -> QPushButton | None:
        return self._std_map.get(std)


class HouseDialog(FramelessShellMixin, QDialog):
    def __init__(self, parent=None, *, title, icon=None, controls=("close",),
                 resizable=False, min_width=None, theme=None):
        super().__init__(parent)
        self._theme = theme or detect()
        self.init_frameless_shell(title=title, controls=controls,
                                  resizable=resizable, icon=icon)
        self.setProperty("houseDialog", True)
        self.setStyleSheet(build_dialog_qss(self._theme))
        if min_width:
            self.setMinimumWidth(min_width)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)
        self._root.addWidget(self._titlebar)

        self._body = QFrame(objectName="dialogBody")
        self._body_outer = QVBoxLayout(self._body)
        self._body_outer.setContentsMargins(*M.DIALOG_BODY_MARGIN)
        self._body_outer.setSpacing(0)
        self._root.addWidget(self._body, 1)

        self._footer = None
        self._footer_box = None
        self._ctx_lbl = None

    # ── header context slot ─────────────────────────────────────────────
    def set_header_context(self, text):
        if self._ctx_lbl is None:
            self._ctx_lbl = QLabel()
            self._ctx_lbl.setProperty("role", "faint")
            lay = self._titlebar.layout()
            lay.insertWidget(lay.indexOf(self._shell_title_lbl) + 1, self._ctx_lbl)
        self._ctx_lbl.setText(text or "")

    # ── body seam ───────────────────────────────────────────────────────
    def set_body(self, widget, *, margin=None):
        if margin is not None:
            self._body_outer.setContentsMargins(*margin)
        self._body_outer.addWidget(widget)

    def body_layout(self):
        return self._body_outer

    # ── footer helper (Cancel-left / primary-right) ─────────────────────
    def set_footer_buttons(self, *, primary=None, cancel=True,
                           extra_left=None, danger=False):
        self._footer = QFrame(objectName="footerBar")
        fl = QHBoxLayout(self._footer)
        fl.setContentsMargins(*M.FOOTER_MARGIN)
        fl.setSpacing(M.FOOTER_BTN_GAP)
        if extra_left is not None:
            if isinstance(extra_left, QWidget):
                fl.addWidget(extra_left)
            else:
                fl.addLayout(extra_left)
        fl.addStretch(1)

        # Build buttons in explicit left-to-right order (Cancel first, primary
        # last) so the house rule — Cancel-left/primary-right — holds regardless
        # of platform style. We keep a thin _FooterButtonBox wrapper assigned to
        # self._footer_box so callers can do box.button(StandardButton.Cancel)
        # and box.rejected.connect(...) exactly as if it were a real
        # QDialogButtonBox, without letting Qt's internal layout reorder things.
        box = _FooterButtonBox()
        self._footer_box = box
        out = {}

        if cancel:
            cancel_btn = QPushButton("Cancel", self._footer)
            cancel_btn.clicked.connect(self.reject)
            box._register(QDialogButtonBox.StandardButton.Cancel, cancel_btn)
            box.rejected.connect(self.reject)
            fl.addWidget(cancel_btn)

        if primary is not None:
            label, slot = primary
            btn = QPushButton(label, self._footer)
            btn.setProperty("variant", "danger" if danger else "primary")
            btn.setDefault(True)
            btn.clicked.connect(slot)
            out["primary"] = btn
            fl.addWidget(btn)

        self._root.addWidget(self._footer)
        self.adjustSize()
        return out

    # ── live-restyle seam (wiring deferred, todo:276) ───────────────────
    def restyle(self):
        self._theme = detect()
        self.setStyleSheet(build_dialog_qss(self._theme))
