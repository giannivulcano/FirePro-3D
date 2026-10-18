"""Colour tokens: one resolver for stored colour strings (HF1).

A colour value is a plain string -- ``#rrggbb`` | ``token:auto`` |
``token:accent``. Tokens are resolved per paint, never at set time: a model
item paints on the canvas and inside a paper viewport in the same frame
(hatch-and-fill.md § HF1 build design -- colour tokens).
"""
from __future__ import annotations

import logging

from PyQt6.QtGui import QColor

from . import paper_display as _pd   # module imports (hot path)
from . import theme as _th
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
    """Lower-case ``#rrggbb`` for a str / QColor; tokens pass unchanged; the
    literal ``""`` (No Fill / no stroke, universal picker) passes unchanged;
    anything else becomes *default*."""
    if isinstance(value, str) and value == "":
        return ""
    name = getattr(value, "name", None)
    if callable(name):
        value = name()
    s = str(value or "").strip().lower()
    if is_token(s) or s.startswith("#"):
        return s
    return default


def _paper_mode(item):
    """None on the canvas; else the PaperColorMode that applies to *item*.

    Inside the SheetViewport window (screen, PDF, print) categorised items get
    their B&W/Custom colour substituted upstream, but uncategorised ones
    (TextItem) do not -- so the pass reports BW when the pass was applied under
    B&W, else FULL_COLOR. A ``paints_on_paper`` scene (PaperScene, white
    previews) reads the saved mode.
    """
    if _pd.paper_pass_active():
        if _pd.paper_pass_color_mode() is _pd.PaperColorMode.BW:
            return _pd.PaperColorMode.BW
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
    An unknown token draws as Automatic (one warning per value). ``""`` (No
    Fill / no stroke, universal picker) is fully transparent whatever *alpha*,
    so a pen, brush or text colour built from it draws nothing; ``None``
    (unset) is an invalid QColor.
    """
    if isinstance(value, str) and value == "":
        return QColor(0, 0, 0, 0)
    if not is_token(value):
        c = QColor(value) if value else QColor()
    else:
        if value not in _LABELS and value not in _warned:
            _warned.add(value)
            _log.warning("unknown colour token %r drawn as Automatic", value)
        mode = _paper_mode(item)
        if mode is None:
            t = _th.detect()
            c = QColor(t.accent if value == TOKEN_ACCENT else t.ink)
        elif value == TOKEN_ACCENT and mode is _pd.PaperColorMode.FULL_COLOR:
            c = QColor(_th.LIGHT.accent)
        else:
            c = QColor(_PAPER_INK)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def section_fill_colour(value, item=None) -> "QColor | None":
    """Solid section-cut body colour for a stored value, or None for no body
    fill: unset and ``""`` (No Fill) draw nothing; a ``#hex`` or ``token:*``
    resolves on *item*'s surface; anything else (a ``hatch:`` form) is None.
    """
    if not value:
        return None
    if value.startswith("#") or is_token(value):
        return resolve_colour(value, item=item)
    return None


def paint_resolver(item=None):
    """Per-paint memo of :func:`resolve_colour` for *item* (G12 perf).

    The surface (paper pass, paper scene mode, theme) cannot change inside
    one paint, so each distinct stored value resolves once. Use the returned
    callable for a single paint only -- nothing resolved here outlives it,
    so a theme or paper-mode change reaches the next paint.
    """
    cache: dict = {}

    def resolve(value) -> QColor:
        c = cache.get(value)
        if c is None:
            c = cache[value] = resolve_colour(value, item=item)
        return QColor(c)        # copy: callers may tint / set alpha

    return resolve
