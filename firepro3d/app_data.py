"""Shared per-user app-data directory resolution.

One home for the ``%APPDATA% or ~`` + ``FirePro3D`` root that sprinkler_db and
titleblock_template previously duplicated. The root is overridable via a
persisted preference (Preferences → General → Data folder); existing content is
NOT moved when the preference changes.
"""
import os

_QSETTINGS_ORG = "GV"
_QSETTINGS_APP = "FirePro3D"
ROOT_KEY = "paths/user_data_root"   # Preferences data-folder override


def default_root() -> str:
    """The built-in per-user root: roaming ``%APPDATA%`` (or ``~``) + FirePro3D."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FirePro3D")


def _configured_root() -> str | None:
    """The user-configured data-folder override, or None when unset/unavailable.

    Read lazily from QSettings so a preference change takes effect immediately and
    ``app_data`` stays importable without a running QApplication.
    """
    try:
        from PyQt6.QtCore import QSettings
        raw = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP).value(ROOT_KEY, "", type=str)
        raw = (raw or "").strip()
        return raw or None
    except Exception:
        return None


def user_data_root() -> str:
    """Effective FirePro3D data root: the configured override, else the default."""
    return _configured_root() or default_root()


def app_data_dir(subdir: str = "") -> str:
    """Return the FirePro3D data dir, optionally joined with *subdir*.

    Honors the Preferences data-folder override (persisted in QSettings), falling
    back to ``default_root()`` (``%APPDATA%/FirePro3D``).

    Args:
        subdir: Optional child path (e.g. ``"blocks"``, ``"sprinklers.json"``).

    Returns:
        Absolute path ``<root>[/subdir]``.
    """
    root = user_data_root()
    return os.path.join(root, subdir) if subdir else root
