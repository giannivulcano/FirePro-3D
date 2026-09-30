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
    """Resolve the startup fullscreen preference.

    The System Settings "Maximize window on startup" toggle (``ui/immersive``)
    is the single source of truth; the retired ``ui/fullscreen`` key (written
    by the header toggle until 2026-09-30) is read only when ``ui/immersive``
    is absent. Defaults to True (fullscreen-first shell).

    Args:
        getter: a ``QSettings.value``-like callable taking a single key and
            returning the stored value or ``None`` when absent (``dict.get``
            works in tests).
    """
    pref = getter("ui/immersive")
    if pref is not None:
        return _as_bool(pref)
    legacy = getter("ui/fullscreen")
    if legacy is not None:
        return _as_bool(legacy)
    return True


def retire_fullscreen_key(settings) -> None:
    """One-time migration: fold the retired ``ui/fullscreen`` key into
    ``ui/immersive`` (only when the latter is unset), then remove it.

    Args:
        settings: a ``QSettings``-like object (``contains``/``value``/
            ``setValue``/``remove``).
    """
    if not settings.contains("ui/fullscreen"):
        return
    if not settings.contains("ui/immersive"):
        settings.setValue(
            "ui/immersive", _as_bool(settings.value("ui/fullscreen")))
    settings.remove("ui/fullscreen")
