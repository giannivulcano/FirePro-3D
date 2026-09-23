"""Shared per-user app-data directory resolution.

One home for the ``%APPDATA% or ~`` + ``FirePro3D`` root that sprinkler_db and
titleblock_template previously duplicated. The root is overridable via a
persisted preference (Preferences → General → Data folder); existing content is
NOT moved when the preference changes.
"""
import os

_QSETTINGS_ORG = "GV"
_QSETTINGS_APP = "FirePro3D"
ROOT_KEY = "paths/user_data_root"       # Preferences data-folder override
TITLEBLOCK_DIR_KEY = "paths/titleblock_dir"   # dedicated title-block library dir
BLOCK_DIR_KEY = "paths/block_dir"             # dedicated block library dir

# Known content under a data root, migrated together when the root changes (E3).
_MIGRATABLE = ("titleblocks", "blocks", "sprinklers.json", "default.fpdt")


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


def _configured_dir(key: str) -> str | None:
    """A dedicated library-folder override stored under *key*, or None."""
    try:
        from PyQt6.QtCore import QSettings
        raw = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP).value(key, "", type=str)
        raw = (raw or "").strip()
        return raw or None
    except Exception:
        return None


def _configured_titleblock_dir() -> str | None:
    """The dedicated title-block library override, or None when unset."""
    return _configured_dir(TITLEBLOCK_DIR_KEY)


def titleblock_library_dir() -> str:
    """Directory holding the title-block ``<uuid>.json`` library files.

    Precedence (E2): an explicit override (Settings → *Title block library*) →
    else ``<user_data_root>/titleblocks`` (which itself honors the data-folder
    override). Lets the title-block library live somewhere shared independent of
    the general data folder.
    """
    return _configured_titleblock_dir() or app_data_dir("titleblocks")


def block_library_dir() -> str:
    """Root of the two-tier block library (``<Library>/<Series>/*.fpdb``).

    Precedence mirrors :func:`titleblock_library_dir`: an explicit override
    (System Settings > General > Data folder > *Block library*) → else
    ``<user_data_root>/blocks``.
    """
    return _configured_dir(BLOCK_DIR_KEY) or app_data_dir("blocks")


def migrate_data_root(old_root: str, new_root: str, *, move: bool = False) -> list[str]:
    """Copy (or move) known data content from *old_root* to *new_root* (E3).

    Copies each of ``_MIGRATABLE`` (titleblocks/, blocks/, sprinklers.json,
    default.fpdt) that exists under *old_root* and is **absent** under
    *new_root* — never clobbers content already at the destination. With
    ``move=True`` the source is removed after a successful copy.

    Args:
        old_root: The previous data root (source).
        new_root: The new data root (destination).
        move: When True, delete each source after copying.

    Returns:
        The list of item names actually migrated.
    """
    import shutil
    migrated: list[str] = []
    if not old_root or not new_root or os.path.abspath(old_root) == os.path.abspath(new_root):
        return migrated
    os.makedirs(new_root, exist_ok=True)
    for name in _MIGRATABLE:
        src = os.path.join(old_root, name)
        dst = os.path.join(new_root, name)
        if not os.path.exists(src) or os.path.exists(dst):
            continue    # nothing to copy, or destination already has it
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            if move:
                if os.path.isdir(src):
                    shutil.rmtree(src, ignore_errors=True)
                else:
                    os.remove(src)
            migrated.append(name)
        except OSError:
            continue    # best-effort; a failed item never aborts the rest
    return migrated


def data_root_has_content(root: str) -> bool:
    """True when *root* holds any migratable FirePro3D content (E3 gate)."""
    return bool(root) and any(
        os.path.exists(os.path.join(root, name)) for name in _MIGRATABLE)
