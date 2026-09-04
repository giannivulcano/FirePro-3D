"""Shared per-user app-data directory resolution.

One home for the ``%APPDATA% or ~`` + ``FirePro3D`` root that sprinkler_db and
titleblock_template previously duplicated.
"""
import os


def app_data_dir(subdir: str = "") -> str:
    """Return the FirePro3D per-user data dir, optionally joined with *subdir*.

    Roaming ``%APPDATA%`` on Windows, falling back to the home directory
    elsewhere / when unset.

    Args:
        subdir: Optional child path (e.g. ``"blocks"``, ``"sprinklers.json"``).

    Returns:
        Absolute path ``<%APPDATA% or ~>/FirePro3D[/subdir]``.
    """
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    root = os.path.join(base, "FirePro3D")
    return os.path.join(root, subdir) if subdir else root
