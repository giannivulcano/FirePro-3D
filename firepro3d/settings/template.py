"""Template lifecycle for FirePro3D project defaults.

A template is a blank ``.fpdt`` file — same JSON structure as a ``.fpd`` project
file — carrying settings (scale + project_info) but NO geometry.  New/blank
projects are seeded from this template so that display-unit preferences are
project-scoped rather than global.

The template file lives at ``<user_data_root>/default.fpdt``.

Functions
---------
template_path()
    Return the absolute path to the default template file.
ensure_template()
    Create the template if it does not exist, seeding units from legacy
    app-wide QSettings.  Return the path.
clone_template_into(scene)
    Load the template into *scene* and clear the project path so the scene
    remains untitled (not bound to the template file).
save_current_as_default(scene)
    Persist the scene's current scale + project_info into the template.
    Geometry is NEVER copied.
"""

from __future__ import annotations

import json
import logging
import os

from firepro3d import app_data
from firepro3d.scale_manager import ScaleManager, DisplayUnit

log = logging.getLogger(__name__)

_TEMPLATE_FILENAME = "default.fpdt"

# Keys required for a valid blank-project payload (geometry lists are always []).
_BLANK_GEOMETRY_KEYS = [
    "nodes", "pipes", "walls", "rooms", "floor_slabs", "roofs", "gridlines",
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _blank_template_payload(sm: ScaleManager | None = None) -> dict:
    """Build a fresh blank-template payload dict.

    Args:
        sm: ScaleManager whose settings to embed.  Defaults to a fresh
            ``ScaleManager()`` when *None*.

    Returns:
        A dict suitable for ``json.dump`` that carries ``"template": True``,
        the given scale settings, and empty lists for every geometry key.
    """
    if sm is None:
        sm = ScaleManager()
    payload: dict = {
        "version": 1,
        "template": True,
        "project_info": {},
        "scale": sm.to_dict(),
        # Linked default title-block: a library uuid (not an embedded copy).
        # New projects resolve this against the library and embed the CURRENT
        # version, so edits to the linked template flow into future projects
        # (existing saved projects keep their embedded copy — DD-5). "" = none.
        "titleblock_template_uuid": "",
    }
    for key in _BLANK_GEOMETRY_KEYS:
        payload[key] = []
    return payload


def _seed_scale_from_legacy_qsettings() -> ScaleManager:
    """Read the legacy app-wide QSettings unit/precision and return a seeded
    ScaleManager.

    Keys read: ``display/unit``, ``display/precision`` from
    ``QSettings("GV", "FirePro3D")``.  Unknown/missing keys are silently
    ignored and the defaults from a fresh ``ScaleManager()`` are preserved.

    Returns:
        A ``ScaleManager`` with any migrated settings applied.
    """
    sm = ScaleManager()
    try:
        from PyQt6.QtCore import QSettings
        qs = QSettings("GV", "FirePro3D")
        unit = qs.value("display/unit", None)
        precision = qs.value("display/precision", None)
        if unit is not None:
            try:
                sm.display_unit = DisplayUnit(unit)
            except ValueError:
                pass  # unrecognised value — keep default
        if precision is not None:
            try:
                sm.precision = int(precision)
            except (TypeError, ValueError):
                pass
    except Exception:
        # QSettings unavailable (e.g. no QApplication) — proceed with defaults.
        pass
    return sm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def template_path() -> str:
    """Return the absolute path of the default template file.

    Returns:
        ``<user_data_root>/default.fpdt``
    """
    return os.path.join(app_data.user_data_root(), _TEMPLATE_FILENAME)


def ensure_template() -> str:
    """Create the default template file if it does not exist.

    On first call the template is seeded with units migrated once from the
    legacy app-wide QSettings (``display/unit``, ``display/precision``).

    Returns:
        The absolute path to the template file.
    """
    path = template_path()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sm = _seed_scale_from_legacy_qsettings()
        payload = _blank_template_payload(sm)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        log.debug("Created default template: %s", path)
    return path


def clone_template_into(scene) -> None:
    """Load the default template into *scene* and mark the scene as untitled.

    Wraps ``scene.load_from_file`` so that a corrupt template is regenerated
    and the load is retried once.  After loading (successful or recovered),
    ``scene._project_path`` is always reset to ``None`` so the clone is never
    accidentally saved back to the template file.

    Args:
        scene: A ``Model_Space`` instance (or compatible) with a
            ``load_from_file(path)`` method and a ``_project_path`` attribute.
    """
    path = ensure_template()
    try:
        scene.load_from_file(path)
    except Exception:
        log.exception("Template load failed — regenerating and retrying")
        try:
            os.remove(path)
        except OSError:
            pass
        path = ensure_template()
        scene.load_from_file(path)
    finally:
        # Always clear the project path — this is an untitled clone.
        scene._project_path = None


def apply_template_settings(scene) -> None:
    """Apply the template's SETTINGS (scale/units + project_info) onto an
    already-built scene — used by startup/New-Project, which construct their
    default scene procedurally (levels, gridlines) BEFORE seeding units.
    Full-scene cloning would wipe those; this only overlays settings.

    Args:
        scene: A ``Model_Space`` instance (or compatible) exposing
            ``scale_manager`` and ``_project_info``.
    """
    import json as _json
    import logging as _logging
    from firepro3d.scale_manager import ScaleManager
    path = ensure_template()
    try:
        with open(path) as f:
            data = _json.load(f)
    except (OSError, ValueError):
        _logging.getLogger(__name__).exception("Corrupt .fpdt; regenerating")
        try:
            os.remove(path)
        except OSError:
            pass
        path = ensure_template()
        with open(path) as f:
            data = _json.load(f)
    if "scale" in data:
        scene.scale_manager = ScaleManager.from_dict(data["scale"])
    info = data.get("project_info")
    if isinstance(info, dict):
        scene._project_info = dict(info)
    apply_template_titleblock(scene, data)


def apply_template_titleblock(scene, data: dict) -> None:
    """Resolve the template's linked title-block uuid and embed the CURRENT
    library version into *scene* (Task A: linked default that auto-reflects
    library edits into new projects).

    A missing/blank/unresolvable uuid leaves ``scene._titleblock_template``
    untouched (``None`` after ``_clear_scene`` → the sheet renders blank and
    prompts the user to build one). Never raises into the caller.

    Args:
        scene: A ``Model_Space`` exposing ``_titleblock_template``.
        data: The parsed ``.fpdt`` payload.
    """
    uuid = (data.get("titleblock_template_uuid") or "").strip()
    if not uuid:
        return
    try:
        from firepro3d.titleblock_template import load_library
        match = next((t for t in load_library() if t.uuid == uuid), None)
        if match is not None:
            scene._titleblock_template = match.to_dict()
        else:
            log.info("Linked title-block template %s not in library — "
                     "new project starts with no title block.", uuid)
    except Exception:
        log.exception("Failed to resolve linked title-block template %s", uuid)


def save_current_as_default(scene) -> str:
    """Persist *scene*'s current scale and project_info into the default template.

    Geometry is NEVER written — only ``scale_manager.to_dict()`` and
    ``_project_info`` are captured.  A fresh blank payload is built so that the
    template stays free of geometry regardless of the scene's state.

    Args:
        scene: A ``Model_Space`` instance (or compatible) exposing
            ``scale_manager`` and optionally ``_project_info``.

    Returns:
        The absolute path to the written template file.
    """
    path = ensure_template()
    payload = _blank_template_payload()
    payload["scale"] = scene.scale_manager.to_dict()
    payload["project_info"] = dict(getattr(scene, "_project_info", {}) or {})
    # Capture the current project's linked title-block by uuid (reference, not
    # embed): "Save as default" is how the user sets which library template new
    # projects inherit (Task A).
    raw_tb = getattr(scene, "_titleblock_template", None)
    if isinstance(raw_tb, dict) and raw_tb.get("uuid"):
        payload["titleblock_template_uuid"] = raw_tb["uuid"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    log.debug("Saved current settings as default template: %s", path)
    return path
