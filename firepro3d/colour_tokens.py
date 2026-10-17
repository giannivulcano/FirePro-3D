"""Colour tokens: one resolver for stored colour strings (HF1).

A colour value is a plain string -- ``#rrggbb`` | ``token:auto`` |
``token:accent``. Tokens are resolved per paint, never at set time: a model
item paints on the canvas and inside a paper viewport in the same frame
(hatch-and-fill.md § HF1 build design -- colour tokens).
"""
from __future__ import annotations

import logging

from PyQt6.QtGui import QColor

from .constants import TOKEN_ACCENT, TOKEN_AUTO, TOKEN_PREFIX

_log = logging.getLogger(__name__)
_warned: set[str] = set()
_LABELS = {TOKEN_AUTO: "Automatic", TOKEN_ACCENT: "Accent"}
_PAPER_INK = "#000000"


def is_token(value) -> bool:
    """True when *value* is a ``token:*`` colour string."""
    return isinstance(value, str) and value.startswith(TOKEN_PREFIX)


def token_label(value) -> str | None:
    """UI label of a token ("Automatic" / "Accent"); None for hex."""
    if not is_token(value):
        return None
    return _LABELS.get(value, "Automatic")


def normalize_colour(value, default: str = "#ffffff") -> str:
    """Lower-case ``#rrggbb`` for a str / QColor; tokens pass unchanged;
    anything else becomes *default*."""
    name = getattr(value, "name", None)
    if callable(name):
        value = name()
    s = str(value or "").strip().lower()
    if is_token(s) or s.startswith("#"):
        return s
    return default


def _paper_mode(item):
    """None on the canvas; else the PaperColorMode that applies to *item*.

    Inside the SheetViewport window (screen, PDF, print) B&W/Custom is
    already substituted upstream, so the pass reports FULL_COLOR. A
    ``paints_on_paper`` scene (PaperScene, white previews) reads the saved mode.
    """
    from . import paper_display as _pd
    if _pd.paper_pass_active():
        return _pd.PaperColorMode.FULL_COLOR
    sc = item.scene() if item is not None else None
    if sc is not None and getattr(sc, "paints_on_paper", False):
        return _pd.load_paper_color_mode()
    return None


def resolve_colour(value, alpha: int | None = None, item=None) -> QColor:
    """QColor for a stored colour string on the surface *item* paints on.

    Hex passes through ``QColor(value)`` unchanged. ``token:auto`` -> theme
    ``ink`` on canvas, black on paper; ``token:accent`` -> theme ``accent`` on
    canvas, the light-theme accent on paper; B&W paper -> black for both.
    An unknown token draws as Automatic (one warning per value).
    """
    if not is_token(value):
        c = QColor(value) if value else QColor()
    else:
        from . import theme as _th
        if value not in _LABELS and value not in _warned:
            _warned.add(value)
            _log.warning("unknown colour token %r drawn as Automatic", value)
        mode = _paper_mode(item)
        if mode is None:
            t = _th.detect()
            c = QColor(t.accent if value == TOKEN_ACCENT else t.ink)
        elif value == TOKEN_ACCENT and mode.value == "full_color":
            c = QColor(_th.LIGHT.accent)
        else:
            c = QColor(_PAPER_INK)
    if alpha is not None:
        c.setAlpha(alpha)
    return c
