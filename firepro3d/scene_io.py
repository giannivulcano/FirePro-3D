"""
scene_io.py
===========
Mixin providing file I/O (save / load / clear) for Model_Space.

Extracted from Model_Space.py to keep the main scene class focused on
interactive behaviour.  Mixed into Model_Space's MRO — all ``self``
references resolve against the Model_Space instance at runtime.

Usage::

    class Model_Space(SceneIOMixin, QGraphicsScene):
        ...
"""

from __future__ import annotations

import json
import logging
import os

from . import element_store
from .constants import DEFAULT_LEVEL
from .underlay import Underlay
from .network_codec import (
    serialize_node, serialize_pipe,
    serialize_water_supply, serialize_design_area,
)

log = logging.getLogger("FirePro3D")


def _plan_record_resolves(rec, uids) -> bool:
    """Editor/Build slice 2 (C8 exception): whether every ref of constraint
    record *rec* names a loaded wall / gridline / unhosted block uid
    (``plan_ref_uids``) (no loose geometry). The one ground allowed is the
    seed's origin tie (smoke ruling 2026-10-28): ``coincident`` [origin, p1];
    every other ground stays Block-Editor only."""
    refs = rec.get("refs") if isinstance(rec, dict) else None
    if not isinstance(refs, list) or not refs:
        return False
    if (rec.get("type") == "coincident" and len(refs) == 2
            and refs[0] == {"ref": "origin"}
            and isinstance(refs[1], dict) and refs[1].get("h") == "p1"):
        refs = refs[1:]
    if not all(isinstance(r, dict) and isinstance(r.get("uid"), str) for r in refs):
        return False
    return all(r["uid"] in uids for r in refs)


class SceneIOMixin:
    """Save / Load / Clear operations for the plan-view scene."""

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------

    def save_to_file(self, filename: str, *, backup: bool = True):
        """Serialise the full scene to JSON.

        Args:
            filename: Target project file.
            backup: Keep a dated copy of the existing file first (False for
                autosave).
        """
        self._project_path = os.path.abspath(filename)
        from .linked_document import relativize_sheet_links

        # --- Nodes (assign temp IDs) ---
        node_list = list(self.sprinkler_system.nodes)
        node_id = {n: i for i, n in enumerate(node_list)}

        nodes_data = [serialize_node(node, node_id) for node in node_list]

        # --- Pipes ---
        pipes_data = []
        for pipe in self.sprinkler_system.pipes:
            if pipe.node1 is None or pipe.node2 is None:
                continue
            if pipe.node1 not in node_id or pipe.node2 not in node_id:
                continue
            pipes_data.append(serialize_pipe(pipe, node_id))

        # --- Annotations: notes + dimensions are forbidden model content
        # (containment C8) — no longer written.  Annotation only ever held
        # notes/dimensions, so annotations serialise to [].
        annotations_data = []

        # (HatchItem retired 2026-08-22; legacy loose geometry / standalone
        #  text no longer written under containment C8; plan constraints on
        #  walls + gridlines are -- editor-build slice 2.)

        # --- Underlays ---
        underlays_data = []
        project_dir = os.path.dirname(os.path.abspath(filename))
        for data, item in self.underlays:
            if item is not None:
                data.x        = item.scenePos().x()
                data.y        = item.scenePos().y()
                data.scale    = item.scale()
                data.rotation = item.rotation()
                data.opacity  = item.opacity()
            d = data.to_dict()
            d["path"] = Underlay.relativize_path(
                os.path.abspath(data.path), project_dir)
            underlays_data.append(d)

        # --- Water supply ---
        ws = self.water_supply_node
        ws_data = serialize_water_supply(ws) if ws is not None else None

        # --- Design areas ---
        design_areas_data = [
            serialize_design_area(da, node_id, self.active_design_area)
            for da in self.design_areas
        ]

        # --- Levels ---
        levels_data = (
            self._level_manager.to_list()
            if self._level_manager
            else []
        )

        # --- Construction geometry + standalone text: forbidden loose content
        # (containment C8) — no longer written to the payload (their rows have
        # no ``file_key``; docs/specs/element-store.md D1).

        # --- Project tables (scene-io "Project tables") ---
        from . import project_tables
        tables = project_tables.tables_for_save()

        # --- Assemble and write ---
        payload = {
            "version":             self.SAVE_VERSION,
            "project_info":        self._project_info,
            "mark_patterns":       dict(self.mark_patterns),
            "annotation_defaults": dict(self.annotation_defaults),   # SB3: category -> block id
            "project_settings_size": (list(self.project_settings_size)
                                      if self.project_settings_size else None),
            "scale":               self.scale_manager.to_dict(),
            **tables,
            "levels":              levels_data,
            "plan_views":          (self._plan_view_manager.to_list()
                                    if self._plan_view_manager else []),
            "active_level":        self.active_level,
            "nodes":               nodes_data,
            "pipes":               pipes_data,
            "annotations":         annotations_data,
            "underlays":           underlays_data,
            "water_supply":        ws_data,
            "design_areas":        design_areas_data,
            # Element rows gridlines .. blocks (docs/specs/element-store.md D2):
            # constraints (plan walls, gridlines + unhosted blocks, C8
            # exception) after walls; block definitions before blocks.
            **element_store.file_records(
                self, constraints=self.constraint_ctl.to_records()),
            "detail_views":        (self._detail_manager.to_list()
                                    if getattr(self, "_detail_manager", None) else []),
            "sections":            (self._section_manager.to_list()
                                    if getattr(self, "_section_manager", None) else []),
            "sheets":              (relativize_sheet_links(
                                        [s.to_dict() for s in self._sheets], project_dir)
                                    if hasattr(self, '_sheets') else []),
            "titleblock_template": getattr(self, "_titleblock_template", None),
        }
        # Ensure all underlays have cache entries
        self._underlay_ctl._ensure_underlay_caches(os.path.abspath(filename))

        from .project_backup import write_atomic, write_backup
        try:
            if backup:
                write_backup(filename)
            write_atomic(filename, payload)
        except Exception as e:
            self._show_status(f"Save failed: {e}")
            return False
        self._show_status(f"Saved to {filename}")
        return True

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------

    def _refresh_view_head_copies(self) -> int:
        """Bring the project's Section and Detail head copies up to the seed that
        binds the view number (SB4f D2), outside undo.

        Untouched (``base_version`` None, or equal to ``version``) and older than
        the library file -> replaced by the library copy. Edited and still bound
        to Mark -> kept. ``source_status`` is not used: it reads an edited copy
        as "library" when the version numbers happen to match.

        Returns:
            The number of edited copies kept on Mark (one load notice).
        """
        from . import block_library
        from .system_blocks import SYSTEM_DEFAULTS
        kept = 0
        for cat in ("Section", "Detail"):
            bid = SYSTEM_DEFAULTS.get(cat)   # no id, no copy to refresh
            d = self._block_definitions.get(bid) if bid else None
            if d is None:
                continue
            if d.base_version is None or d.version == d.base_version:
                lib = block_library.reload_from_library(d)
                if lib is not None and lib.version > d.version:
                    lib.base_version = lib.version
                    self._block_definitions[bid] = lib
            elif any(a.get("host_key") == "Mark" for a in d.effective_attributes()):
                kept += 1
        return kept

    def load_from_file(self, filename: str):
        """Clear the scene and restore from JSON."""
        from .node import Node
        from .underlay import Underlay
        from .scale_manager import ScaleManager
        from .block_definition import BlockDefinition
        from . import fill_types, project_tables
        from PyQt6.QtGui import QColor

        try:
            with open(filename, "r") as f:
                payload = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError,
                UnicodeDecodeError) as e:
            self._show_status(f"Failed to open: {e}")
            return False

        version = payload.get("version", 1)
        project_tables.migrate_payload(payload)   # HF1 colour, D-PH6 phases: before _clear_scene
        self._clear_scene()
        self._uid_repairs = 0               # SB5 Q6: count this file's duplicate uids only
        self._project_path = os.path.abspath(filename)

        # --- Project tables: installed before any parse (scene-io "Project tables") ---
        session = project_tables.begin_load(payload)

        # --- Scale ---
        if "scale" in payload:
            self._project_info = payload.get("project_info", {})
            self.scale_manager = ScaleManager.from_dict(payload["scale"])
        else:
            self.scale_manager = ScaleManager()

        # --- Levels ---
        levels_data = payload.get("levels", [])
        if levels_data and self._level_manager:
            self._level_manager.from_list(levels_data)
        from . import marks as _marks
        self.mark_patterns = dict(_marks.DEFAULT_PATTERNS)
        self.mark_patterns.update(_marks.clean_patterns(payload.get("mark_patterns")))
        _pss = payload.get("project_settings_size")
        self.project_settings_size = (
            (int(_pss[0]), int(_pss[1]))
            if isinstance(_pss, (list, tuple)) and len(_pss) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and 0 < v < 100000          # also rejects inf / nan
                    for v in _pss)
            else None)
        saved_active = payload.get("active_level", "")
        if saved_active and self._level_manager and self._level_manager.get(saved_active):
            self.active_level = saved_active

        # --- Plan views (per-view cut-plane settings) ---
        pv_data = payload.get("plan_views", [])
        if pv_data and self._plan_view_manager:
            self._plan_view_manager.from_list(pv_data)

        # --- Detail views ---
        detail_data = payload.get("detail_views", [])
        if detail_data and getattr(self, "_detail_manager", None):
            self._detail_manager.from_list(detail_data)

        # --- Sheets (paper space) ---
        from .paper_space import Sheet
        sheet_data = payload.get("sheets", [])
        self._sheets = [Sheet.from_dict(d) for d in sheet_data]
        from .linked_document import resolve_sheet_links
        resolve_sheet_links(self._sheets, os.path.dirname(os.path.abspath(filename)))

        # --- Title block template (embedded copy is authoritative) ---
        self._titleblock_template = payload.get("titleblock_template", None)
        from .titleblock_template import migrate_legacy_fields, migrate_project_info
        from .paper_space import DEFAULT_TITLE_BLOCK_FIELDS
        # One-way address-key migration (2026-08-04): address/city/state →
        # address1/address2 before anything reads the dict.
        self._project_info = migrate_project_info(
            getattr(self, "_project_info", {}))
        try:
            migrate_legacy_fields(
                [s.title_block_fields for s in self._sheets],
                self._project_info,
                skip_values=DEFAULT_TITLE_BLOCK_FIELDS,
            )
        except Exception as exc:
            # Migration is best-effort: a malformed project_info container must
            # never abort project open (load continues with unmigrated fields).
            log.warning("Legacy title-block migration skipped: %s", exc)

        # --- Nodes ---
        # Create each node unconditionally — bypass find_nearby_node so that
        # vertical pipes (same XY, different Z) keep distinct node objects.
        from .network_codec import deserialize_node
        id_to_node: dict[int, Node] = {}
        for entry in payload.get("nodes", []):
            id_to_node[entry["id"]] = deserialize_node(self, entry)

        # --- Pipes ---
        from .network_codec import deserialize_pipe
        for entry in payload.get("pipes", []):
            deserialize_pipe(self, entry, id_to_node)

        # --- Fittings ---
        for node in id_to_node.values():
            node.fitting.update()
            pending = getattr(node, "_fitting_display_overrides_pending", {})
            if pending:
                node.fitting._display_overrides = pending
                del node._fitting_display_overrides_pending

        # --- Annotations: notes + dimensions are forbidden model content
        # (containment C8) — read-but-discard silently.  Annotation only ever
        # held notes/dimensions, so the restore loop is dropped entirely.

        # --- Underlays ---
        project_dir = os.path.dirname(os.path.abspath(filename))
        missing_underlays = []
        # LW-DC-8: underlays may be built asynchronously after this loader
        # returns (cache miss -> worker thread), so their weight names are
        # migrated here, from the payload, not by the end-of-load sweep.
        from .paper_display import migrate_underlay_entry
        lw_map = session.underlay_map
        for entry in payload.get("underlays", []):
            if lw_map:
                entry = migrate_underlay_entry(entry, lw_map)
            udata = Underlay.from_dict(entry)
            resolved = Underlay.resolve_path(udata.path, project_dir)

            if resolved is not None:
                udata.path = resolved
                source_mtime = os.path.getmtime(resolved)
            else:
                # Resolve path for cache key even though file is gone
                if not os.path.isabs(udata.path):
                    udata.path = os.path.normpath(
                        os.path.join(project_dir, udata.path))
                source_mtime = None

            # Try cache first (fast path)
            if self._underlay_ctl._load_underlay_from_cache(udata, source_mtime):
                continue
            # Cache miss — fall back to source file parsing
            if resolved is None:
                missing_underlays.append(udata)
                continue

            if udata.type == "pdf":
                self.import_pdf(udata.path, dpi=udata.dpi, page=udata.page,
                                x=udata.x, y=udata.y, _record=udata,
                                import_mode=udata.import_mode)
            elif udata.type == "dxf":
                self.import_dxf(udata.path, color=QColor(udata.colour),
                                line_weight=udata.line_weight,
                                x=udata.x, y=udata.y,
                                layers=udata.selected_layers,
                                _record=udata,
                                layout=udata.layout)
            elif udata.type == "dwg":
                from .dwg_converter import (
                    find_oda_converter, convert_dwg_to_dxf,
                )
                oda = find_oda_converter()
                if oda is None:
                    missing_underlays.append(udata)
                    continue
                converted = convert_dwg_to_dxf(
                    oda, udata.path,
                    project_dir=os.path.dirname(os.path.abspath(filename)))
                if converted is None:
                    missing_underlays.append(udata)
                    continue
                self.import_dxf(converted, color=QColor(udata.colour),
                                line_weight=udata.line_weight,
                                x=udata.x, y=udata.y,
                                layers=udata.selected_layers,
                                _record=udata,
                                layout=udata.layout,
                                skip_sanitize=True)  # ODA output is clean
                # Store DWG metadata for async cleanup in _on_dxf_finished.
                # _dxf_import_params moved to the controller (underlay slice);
                # import_dxf sets it synchronously above, so it is populated here.
                if self._underlay_ctl._dxf_import_params:
                    self._underlay_ctl._dxf_import_params["_dwg_cleanup_path"] = converted
                    self._underlay_ctl._dxf_import_params["_dwg_source_path"] = udata.path

        # Handle missing underlay files
        for udata in missing_underlays:
            self._create_underlay_placeholder(udata)

        if self.underlays:
            self.underlaysChanged.emit()

        if missing_underlays:
            from .themed_message import themed_warn
            paths = "\n".join(f"  \u2022 {u.path}" for u in missing_underlays)
            themed_warn(
                None, "Missing Underlay Files",
                f"{len(missing_underlays)} underlay file(s) could not be found:\n\n"
                f"{paths}\n\n"
                "Use right-click \u2192 Relink in the browser tree to reconnect.",
            )

        # --- Water supply ---
        ws_data = payload.get("water_supply")
        if ws_data:
            from .network_codec import deserialize_water_supply
            deserialize_water_supply(self, ws_data)

        # --- Design areas ---
        from .network_codec import deserialize_design_area
        for da_entry in payload.get("design_areas", []):
            deserialize_design_area(self, da_entry, id_to_node)
            # Tile geometry is recomputed after walls & rooms load —
            # computing here would produce wall-less (over-wide) tiles

        # --- Construction geometry + standalone model text: forbidden loose
        # content (containment C8) — read-but-discard silently.  The restore
        # loops for polylines / draw_* / legacy reference_lines / polygons / texts are
        # dropped; the single info line below reports the total dropped count.

        # --- Element rows: gridlines .. blocks (docs/specs/element-store.md D4) ---
        # Block definitions (registry) load before the instances.
        heads = []

        def _load_definitions():
            for bid, ddict in payload.get("block_definitions", {}).items():
                # HF5: a name-duplicate type's id re-points to the kept one (persisted on next save).
                fill_types.canonicalise_records(ddict.get("primitives"))
                self._block_definitions[bid] = BlockDefinition.from_dict(ddict)
            heads.append(self._refresh_view_head_copies())   # SB4f D2

        ctx = element_store.BuildContext("load")
        element_store.build_rows(self, payload, ctx, key="file_key",
                                 before_blocks=_load_definitions)
        heads_kept = heads[0]
        orphan_hosts = ctx.orphan_hosts
        self.blockDefinitionsChanged.emit()
        # Nested definitions the file lacks draw as red placeholders (D12).
        missing = self._block_registry.missing_nested()
        if missing:
            from .themed_message import themed_warn
            lines = "\n".join(
                f"  • {mid} (used in "
                f"{', '.join(sorted(self._block_definitions[u].name for u in users))})"
                for mid, users in sorted(missing.items()))
            themed_warn(
                None, "Missing Nested Blocks",
                f"{len(missing)} nested block(s) could not be found:\n\n{lines}\n\n"
                "They are drawn as red placeholders. Load the missing blocks "
                "from the library to fix them.")

        # --- Annotation defaults (SB3): the mapping as written; the resolve
        # (embedding + the one load notice, Q6) runs at the end of the load so
        # its status message outlives "Loaded from ...".
        _ad = payload.get("annotation_defaults")
        self.annotation_defaults = ({str(k): v for k, v in _ad.items() if isinstance(v, str)}
                                    if isinstance(_ad, dict) else {})
        self._annot_memo.clear()
        self._annot_notified.clear()      # a reload notices a broken mapping again

        # --- Design-area tiles (now that walls & rooms exist) ---
        for da in self.design_areas:
            da.compute_area(self.scale_manager)

        # --- Recalculate auto-name counters ---
        self._recalc_name_counters()
        from .gridline import sync_grid_counters, apply_duplicate_warnings
        sync_grid_counters(self._gridlines)
        apply_duplicate_warnings(self._gridlines)

        # --- Legacy hatch migration: retired under containment C8.  Legacy
        # "hatches" recreated loose PolylineItems (forbidden loose geometry),
        # so the migration block is dropped — those entries clean-drop too.

        # --- Constraints (editor-build slice 2, containment C8 exception):
        # records whose refs all resolve to a loaded wall / gridline / level-scoped block are
        # adopted and solved (ctl.load -- an unknown type stays inert, s6.4);
        # every other record is dropped and counted below (G9: a legacy file
        # loads with none).
        from .constraint_controller import plan_ref_uids
        _plan_uids = plan_ref_uids(self)       # walls, gridlines, unhosted blocks (PB1)
        _cons_in = payload.get("constraints")
        if not isinstance(_cons_in, list):
            _cons_in = []
        _cons_kept = [r for r in _cons_in if _plan_record_resolves(r, _plan_uids)]
        self.constraint_ctl.load(_cons_kept)
        _cons_dropped = len(_cons_in) - len(_cons_kept)

        # --- Clean-drop log (containment C1/C8) ---
        # Report a single info line if any forbidden loose content was present.
        _dropped = (element_store.dropped_record_count(payload)   # never-filed rows + legacy reference_lines
                    + len(payload.get("hatches", []))
                    + sum(1 for a in payload.get("annotations", []) if a.get("type") in ("note", "dimension"))
                    + _cons_dropped)
        if _dropped:
            log.info("Clean-drop: discarded %d unsupported loose item(s) on load (containment C1/C8)", _dropped)

        # --- Sections (spec s8, D4): key present -> replace markers; always seed
        # cardinals (after the items load, so a re-seeded box fits the building).
        sec_mgr = getattr(self, "_section_manager", None)
        if sec_mgr is not None:
            sec_data = payload.get("sections")
            if sec_data is not None:
                sec_mgr.from_list(sec_data)
            else:
                sec_mgr.clear()
            sec_mgr.seed_cardinals()

        # Re-point level refs that name a missing level (wall-room-floor s11.3 open repair)
        if self._level_manager:
            from .level_manager import leveled_items
            _fixed = self._level_manager.repair_missing_refs(leveled_items(self))
            if _fixed:
                log.info("Repaired %d level reference(s) to missing levels on load", _fixed)

        # Apply level visibility
        if self._level_manager:
            self._level_manager.apply_to_scene(self)

        # Old schematics turn Printed (notes design N13): reads definitions + sheets.
        from .schematic_scene import migrate_old_schematics
        migrate_old_schematics(self, version)

        # LW-DC-8: a pre-schema-2 file's by-name weights merge into the new
        # Defaults now that every holder is built, before the undo baseline
        # (outside undo; the file re-saves as schema 2 on the next save).
        session.migrate_holders(self)

        # Start fresh undo history
        self._undo_stack = []
        self._undo_pos = -1
        self.push_undo_state()
        dangling = sum(1 for b in self._block_instances
                       if b._host_uid is not None and self.element_by_uid(b._host_uid) is None)
        msg = f"Loaded from {filename}"
        if orphan_hosts:
            msg += f" -- dropped {orphan_hosts} hosted block(s) whose gridline is missing"
        if getattr(self, "_uid_repairs", 0):
            msg += f" -- {self._uid_repairs} duplicate element ids repaired"
        if dangling:
            msg += f" -- {dangling} hosted item(s) whose host is missing"
        if heads_kept:
            msg += (f" -- {heads_kept} edited section/detail head block(s) keep Mark "
                    f"in the top slot")
        self._show_status(msg)
        from .system_blocks import ANNOTATION_CATEGORIES
        for _cat in ANNOTATION_CATEGORIES:
            self.annotation_block(_cat)
        self.refresh_annotation_tags()          # tags built before the mapping existed drop their cached rect
        # DM rows + paper categories last: the scene comes back fully styled.
        session.apply_styles(self)
        return True

    # ------------------------------------------------------------------
    # CLEAR
    # ------------------------------------------------------------------

    def _clear_scene(self):
        """Remove all user content, keeping preview items and origin markers."""
        # End any active tool FIRST: its transients (captured selection, offset
        # source, dimmed originals) reference items clear() is about to delete,
        # and the tool's own teardown must still see them live to restore them.
        self.set_mode(None)
        # stop settle timer + drop pixmap before clear() deletes it (spec §18)
        self.abort_underlay_freeze()
        from .sprinkler_system import SprinklerSystem
        from .annotations import Annotation
        from .scale_manager import ScaleManager
        from .gridline import reset_grid_counters

        self._project_path = None
        self._project_info = {}
        from . import marks as _marks
        self.mark_patterns = dict(_marks.DEFAULT_PATTERNS)
        self.annotation_defaults = {}
        self._annot_memo.clear()
        self._annot_notified.clear()
        self.project_settings_size = None
        self._titleblock_template = None
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self._underlay_ctl.reset()
        self.scale_manager = ScaleManager()
        self.water_supply_node = None
        self.hydraulic_result = None
        # Element rows (docs/specs/element-store.md D4): design areas and block
        # instances leave the scene; every row's list is rebound.
        element_store.clear_lists(self)
        self.active_design_area = None
        from .materials import MATERIAL_NONE_ID
        for _tmpl in (self._wall_template, self._floor_template):
            if _tmpl is not None:     # the old project's material id is unknown to the next table
                _tmpl.material_id = MATERIAL_NONE_ID
        self._polyline_active = None
        self._block_definitions.clear()   # keep the registry's store identity
        # Block Editor capability (D-A32 / LT4): clear() below deletes the frame.
        self.block_capability = None
        self._cap_frame = None
        self._draw_line_anchor = None
        self._draw_rect_anchor = None
        self._draw_rect_side_pt = None
        self._draw_rect_ref_line0 = None
        self._wall_rect_side_pt = None
        self._wall_rect_ref_line0 = None
        self._floor_rect_side_pt = None
        self._floor_rect_ref_line0 = None
        self._draw_circle_center = None
        self._draw_rect_preview = None
        self._draw_circle_preview = None
        self._draw_arc_center = None
        self._draw_arc_radius = 0.0
        self._draw_arc_start_deg = 0.0
        self._draw_arc_step = 0
        self._draw_arc_ep_a = None
        self._draw_arc_ep_b = None
        self._draw_arc_ep_major = False
        self._draw_arc_ep_side = 1
        self._draw_arc_cw = False
        self._draw_arc_radius_line = None
        self._draw_arc_preview = None
        self._text_anchor = None
        self._text_preview = None
        self._wall_anchor = None
        self._wall_chain_start = None
        self._wall_start_target = None
        self._floor_active = None
        # Floor-void host pick (A6): clear() below deletes the highlight item.
        self._floor_opening_candidates = []
        self._floor_opening_host_idx = 0
        self._floor_opening_host_hl = None
        self._roof_active = None
        reset_grid_counters()
        self.active_level = DEFAULT_LEVEL
        if self._level_manager:
            self._level_manager.reset()
        # ET1 spec C: clear() below deletes the registered items; a Python
        # ref outliving the reset must not leave a dead wrapper in the set.
        self._screen_end_items.clear()
        # Section markers are scene items clear() is about to delete: the
        # manager drops them (and its views) first so it never holds dead
        # wrappers; the load / new path re-seeds the cardinals afterwards.
        _sec_mgr = getattr(self, "_section_manager", None)
        if _sec_mgr is not None:
            _sec_mgr.clear()
        # Detail markers are scene items too: the manager must drop them while
        # they are alive, or a load's from_list touches deleted wrappers.
        _det_mgr = getattr(self, "_detail_manager", None)
        if _det_mgr is not None:
            _det_mgr.clear()
        self.clear()
        # self.clear() deleted the shared close-cue ring too (DD8); drop the
        # dead wrapper so show_close_ring lazily recreates it.
        self._polyline_close_indicator = None
        # self.clear() deleted the selection manipulator (a scene item);
        # recreate it so the frame + press routing survive a load/new reset.
        if hasattr(self, "_create_manipulator"):
            self._create_manipulator()
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()
        # Constraints belong to the cleared content (New / Open): drop them
        # (and any pick / drag session) before the fresh undo baseline.
        self.constraint_ctl.reset()
        self._undo_stack = []
        self._undo_pos = -1
        self.push_undo_state()
