"""Small pure helpers for main.py — kept here so they stay headless-testable
without constructing a MainWindow (chrome revamp)."""
from __future__ import annotations


def _as_bool(v) -> bool:
    """Coerce a QSettings-ish value (bool / "true"/"false" / 0/1) to bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "", "no")
    return bool(v)


def migrate_fullscreen_pref(getter) -> bool:
    """Resolve the startup fullscreen preference, migrating the legacy key.

    Prefer ``ui/fullscreen`` when present; otherwise fall back to the legacy
    ``ui/immersive`` key; default to True (fullscreen-first shell).

    Args:
        getter: a ``QSettings.value``-like callable taking a single key and
            returning the stored value or ``None`` when absent (``dict.get``
            works in tests).
    """
    fs = getter("ui/fullscreen")
    if fs is not None:
        return _as_bool(fs)
    legacy = getter("ui/immersive")
    if legacy is not None:
        return _as_bool(legacy)
    return True
