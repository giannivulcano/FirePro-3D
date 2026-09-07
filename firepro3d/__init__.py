"""FirePro3D -- Fire protection sprinkler system design and analysis.

Public API
----------
Import core types directly::

    from firepro3d import Node, Pipe, Sprinkler, WallSegment, Room

Or from their modules::

    from firepro3d.node import Node
"""

from __future__ import annotations

# Single source of truth for the application version (semantic versioning:
# MAJOR.MINOR.PATCH). Everything that displays a version — the splash screen,
# the main-window title — reads this. Bump here on release.
__version__ = "0.5.0"

# Lazy-import registry: name -> (module, attribute)
# Avoids circular imports while allowing ``from firepro3d import Node``.
_LAZY: dict[str, tuple[str, str]] = {
    # Scene / view
    "Model_Space":       (".model_space",       "Model_Space"),
    "Model_View":        (".model_view",        "Model_View"),
    # Entities
    "Node":              (".node",              "Node"),
    "Pipe":              (".pipe",              "Pipe"),
    "Sprinkler":         (".sprinkler",         "Sprinkler"),
    "SprinklerSystem":   (".sprinkler_system",  "SprinklerSystem"),
    "WallSegment":       (".wall",              "WallSegment"),
    "Room":              (".room",              "Room"),
    "FloorSlab":         (".floor_slab",        "FloorSlab"),
    "RoofItem":          (".roof",              "RoofItem"),
    "DoorOpening":       (".wall_opening",      "DoorOpening"),
    "WindowOpening":     (".wall_opening",      "WindowOpening"),
    "GridlineItem":      (".gridline",          "GridlineItem"),
    "WaterSupply":       (".water_supply",      "WaterSupply"),
    "DetailMarker":      (".detail_view",       "DetailMarker"),
    "DesignArea":        (".design_area",       "DesignArea"),
    "Underlay":          (".underlay",          "Underlay"),
    "Fitting":           (".fitting",           "Fitting"),
    # Construction geometry
    "LineItem":          (".construction_geometry", "LineItem"),
    "RectangleItem":     (".construction_geometry", "RectangleItem"),
    "CircleItem":        (".construction_geometry", "CircleItem"),
    "ArcItem":           (".construction_geometry", "ArcItem"),
    "PolylineItem":      (".construction_geometry", "PolylineItem"),
    # Annotations
    "DimensionAnnotation": (".annotations",     "DimensionAnnotation"),
    "NoteAnnotation":    (".annotations",       "NoteAnnotation"),
    # Managers
    "LevelManager":      (".level_manager",     "LevelManager"),
    "Level":             (".level_manager",     "Level"),
    "PlanViewManager":   (".level_manager",     "PlanViewManager"),
    "PlanView":          (".level_manager",     "PlanView"),
    "ScaleManager":      (".scale_manager",     "ScaleManager"),
    "DisplayUnit":       (".scale_manager",     "DisplayUnit"),
    "DisplayManager":    (".display_manager",   "DisplayManager"),
    # Snap engine
    "SnapEngine":        (".snap_engine",       "SnapEngine"),
    "OsnapResult":       (".snap_engine",       "OsnapResult"),
    # Math / utilities
    "CAD_Math":          (".cad_math",          "CAD_Math"),
    # Constraints
    "Constraint":        (".constraints",       "Constraint"),
    # Hydraulics
    "HydraulicSolver":   (".hydraulic_solver",  "HydraulicSolver"),
    "HydraulicResult":   (".hydraulic_solver",  "HydraulicResult"),
    "SprinklerDatabase": (".sprinkler_db",      "SprinklerDatabase"),
    "SprinklerRecord":   (".sprinkler_db",      "SprinklerRecord"),
    # Paper space
    "PaperSpaceScene":   (".paper_space",       "PaperSpaceScene"),
    # Theme
    "Theme":             (".theme",             "Theme"),
}

__all__ = list(_LAZY.keys())


def __getattr__(name: str):
    spec = _LAZY.get(name)
    if spec is not None:
        module_path, attr = spec
        import importlib
        mod = importlib.import_module(module_path, __package__)
        val = getattr(mod, attr)
        globals()[name] = val  # cache for subsequent access
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
