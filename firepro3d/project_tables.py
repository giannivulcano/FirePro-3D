"""Project tables: migrate, install, finish and save them (scene-io.md "Project tables").

The project tables (``GLOSSARY.md``) are the line weights and aliases, fill
types, materials, phases, Display Manager rows and paper categories. This
module owns the order; each table module keeps its storage, and its
load / migrate / reset / save functions are internal seams only this module
calls.
"""
from __future__ import annotations


def migrate_payload(payload: dict) -> None:
    """Migrate a raw file payload in place, before ``_clear_scene`` and any
    deserializer: HF1 colour tokens (D-A20), then phase ids (D-PH6)."""
    from .colour_migration import migrate_project_payload
    from . import phase_registry
    migrate_project_payload(payload)
    phase_registry.migrate_payload(payload)


class LoadSession:
    """One file open's table state between ``begin_load`` and the end of
    ``load_from_file`` (replaces the old module-global weight stash)."""

    def __init__(self, display_settings, paper_display, weight_kind):
        self.display_settings = display_settings
        self.paper_display = paper_display
        self.weight_kind = weight_kind
        self._underlay_map: "dict[str, str] | None" = None

    @property
    def underlay_map(self) -> dict[str, str]:
        """LW-DC-8 map for underlay payloads, computed on first read (after
        the block-library merge) and cached for the rest of the load."""
        if self._underlay_map is None:
            from .paper_display import pending_weight_mapping
            self._underlay_map = pending_weight_mapping(self.weight_kind)
        return self._underlay_map

    def migrate_holders(self, scene) -> bool:
        """LW-DC-8: re-point every by-name holder, install the migrated table
        and fix the session's payloads in place. Runs before the undo
        baseline; a second call does nothing.

        Returns:
            True if a migration ran.
        """
        from .paper_display import apply_pending_weight_migration
        kind, self.weight_kind = self.weight_kind, None
        return apply_pending_weight_migration(
            scene, kind, self.paper_display, self.display_settings)

    def apply_styles(self, scene) -> None:
        """Display Manager rows (the file's, else the QSettings fallback),
        then the paper categories -- the last step of an open."""
        if self.display_settings:
            from .display_manager import apply_project_display_settings
            apply_project_display_settings(scene, self.display_settings)
        else:
            from .display_manager import apply_saved_display_settings
            apply_saved_display_settings(scene)
        from .paper_display import apply_paper_display_from_project
        apply_paper_display_from_project(self.paper_display)


def begin_load(payload: dict) -> LoadSession:
    """Install the file's tables right after ``_clear_scene``: weights and
    aliases first (before any definition / text parse canonicalises names,
    LT2-8 / H-g), then fill types, materials and phases (before any element
    resolves an id)."""
    from .paper_display import apply_project_weights
    from . import fill_types, materials, phase_registry
    display_settings = payload.get("display_settings", None)
    paper_display = payload.get("paper_display", None)
    kind = apply_project_weights(paper_display, stash=True)
    fill_types.load_project_fill_types(payload.get("fill_types"))
    materials.load_project_materials(payload.get("materials"))
    phase_registry.load_project_phases(payload.get("phases"))
    return LoadSession(display_settings, paper_display, kind)
