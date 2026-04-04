"""Generate API reference pages for all firepro3d modules."""

from pathlib import Path
import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

# Module tier groupings for navigation
TIERS = {
    "Core": [
        "model_space", "model_view", "scene_tools", "scene_io", "snap_engine",
    ],
    "Entities": [
        "node", "pipe", "sprinkler", "room", "wall", "fitting", "roof",
        "floor_slab", "wall_opening", "annotations", "construction_geometry",
        "gridline", "grid_line", "view_marker", "underlay", "block_item",
        "water_supply", "design_area",
    ],
    "Managers": [
        "display_manager", "level_manager", "scale_manager", "layer_manager",
        "user_layer_manager", "elevation_manager",
    ],
    "Analysis": [
        "hydraulic_solver", "hydraulic_report", "hydraulic_node_badge",
        "thermal_radiation_solver", "thermal_radiation_report", "fire_curves",
    ],
    "UI": [
        "ribbon_bar", "theme", "property_manager", "model_browser",
        "project_browser", "level_widget", "view_cube",
    ],
    "Dialogs": [
        "auto_populate_dialog", "dxf_preview_dialog", "roof_dialog",
        "wall_dialog", "array_dialog", "grid_lines_dialog",
        "view_range_dialog", "calibrate_dialog", "detail_view",
        "dimension_edit", "fs_visibility_dialog", "underlay_context_menu",
        "entity_context_menu",
    ],
    "Views": [
        "view_3d", "elevation_scene", "elevation_view", "paper_space",
    ],
    "Utilities": [
        "cad_math", "geometry_utils", "geometry_intersect", "format_utils",
        "hatch_patterns", "constants", "constraints", "displayable_item",
        "sprinkler_db", "sprinkler_system", "assets",
    ],
    "Workers": [
        "dxf_import_worker", "pdf_import_worker",
    ],
}

src = Path("firepro3d")

for tier_name, modules in TIERS.items():
    for module_name in modules:
        module_path = src / f"{module_name}.py"
        if not module_path.exists():
            continue

        doc_path = Path("reference", tier_name, f"{module_name}.md")

        with mkdocs_gen_files.open(doc_path, "w") as fd:
            ident = f"firepro3d.{module_name}"
            fd.write(f"# {module_name}\n\n::: {ident}\n")

        mkdocs_gen_files.set_edit_path(doc_path, module_path)
        # Use as_posix() for forward slashes on Windows, and make path
        # relative to reference/ since SUMMARY.md lives there
        rel_path = Path(tier_name, f"{module_name}.md").as_posix()
        nav[tier_name, module_name] = rel_path

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
