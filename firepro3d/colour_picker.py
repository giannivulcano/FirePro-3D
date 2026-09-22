"""colour_picker.py — house colour picker (todo #70).

One modal ``ColourPickerDialog(HouseDialog)`` + one entry point
``pick_colour(initial, parent, context, *, allow_none=False)`` replacing the
native QColorDialog app-wide. Result contract:
    None        → cancelled (caller changes nothing)
    ""          → No Fill (only possible when allow_none=True)
    "#RRGGBB"   → a colour
Callers must import the MODULE and call ``colour_picker.pick_colour`` so tests
can monkeypatch one attribute. See docs/specs/ui-design-system.md.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

NO_FILL = ""

# Fixed drawing colours (same in both themes) — AutoCAD ACI standard set.
STANDARD = ("#FF0000", "#FF7F00", "#FFFF00", "#00FF00", "#00FFFF",
            "#0000FF", "#FF00FF", "#808080", "#C0C0C0", "#FFFFFF")
STANDARD_NAMES = ("ACI 1 red", "ACI 30 orange", "ACI 2 yellow", "ACI 3 green",
                  "ACI 4 cyan", "ACI 5 blue", "ACI 6 magenta", "ACI 8 grey",
                  "ACI 9 light grey", "ACI 7 white")
GREYS = tuple("#" + f"{v:02X}" * 3
              for v in (0, 28, 57, 85, 113, 142, 170, 198, 227, 255))

RECENTS_KEY = "ui/colour_picker/recents"
RECENTS_MAX = 10


def _settings() -> QSettings:
    return QSettings("GV", "FirePro3D")


def load_recents() -> list[str]:
    raw = _settings().value(RECENTS_KEY, "", type=str) or ""
    return [h for h in raw.split(",") if h]


def _save_recents(lst: list[str]) -> None:
    _settings().setValue(RECENTS_KEY, ",".join(lst[:RECENTS_MAX]))


def push_recent(hex_color: str) -> None:
    """Record a committed colour: MRU-first, case-insensitive dedupe, cap 10.
    No Fill ("") is never recorded."""
    if not hex_color:
        return
    h = hex_color.upper()
    lst = [c for c in load_recents() if c.upper() != h]
    lst.insert(0, h)
    _save_recents(lst)


def clear_recents() -> None:
    _save_recents([])
