"""Placement-input coordination — Slice 7 of the Model_Space decomposition.

Owns the Dynamic-Input HUD lifecycle, placement-variant cycling, seed/publish/
resolve, schema selection, template getters, and placement-anchor accessors.
A plain object that back-references the scene (self._scene) for scene-graph
mutation, signal emission, and reads of stay-scene-side state (incl. the ALIGN
tracking scratch, which is irreducible core snap-plumbing — see
docs/specs/model-space-architecture.md §5/§6).
"""
from __future__ import annotations


class PlacementInputCoordinator:
    def __init__(self, scene):
        self._scene = scene
        self.dynamic_input = None          # DynamicInputHud | None (lazily created)
        self._pipe_hud_reference = None    # Pipe | None
        self._resolved_point = None        # QPointF | None (HUD seed source)
        self._variant_index: dict[str, int] = {}
        self._PLACEMENT_VARIANTS: dict[str, list] = {}
        self._init_placement_variants()

    # -------------------------------------------------------------------------
    # Placement-variant registry (moved from Model_Space._init_placement_variants)

    def _init_placement_variants(self):
        """Build the placement-variant registry + the sticky per-mode index.

        Called from ``__init__``.  Each variant is
        ``(label, first-point instruction, apply_fn(s))``; ``apply_fn`` sets
        the tool's variant flag so entry and ←/→ both drive geometry through the
        same state.  The lambdas receive the scene (``s``) at cycle time so they
        can call scene methods directly.
        """
        from firepro3d.model_space import _ARC_VARIANT_CENTER, _ARC_VARIANT_START

        self._PLACEMENT_VARIANTS = {
            "draw_arc": [
                ("Center Point Arc", "Select center point to begin",
                 lambda s: setattr(s, "_arc_variant", _ARC_VARIANT_CENTER)),
                ("Start Point Arc", "Select start point to begin",
                 lambda s: setattr(s, "_arc_variant", _ARC_VARIANT_START)),
            ],
            "draw_rectangle": [
                ("Corner Rectangle", "Pick first corner",
                 lambda s: setattr(s, "_draw_rect_from_center", False)),
                ("Center Rectangle", "Pick center point",
                 lambda s: setattr(s, "_draw_rect_from_center", True)),
            ],
            "wall": [
                ("Wall (Line)", "Pick wall start point",
                 lambda s: s._set_wall_primitive("line")),
                ("Wall (Polyline)", "Pick wall start point",
                 lambda s: s._set_wall_primitive("polyline")),
                ("Wall (Corner Rectangle)", "Pick first corner",
                 lambda s: s._set_wall_primitive("rect", from_center=False)),
                ("Wall (Center Rectangle)", "Pick centre point",
                 lambda s: s._set_wall_primitive("rect", from_center=True)),
            ],
            "floor": [
                ("Floor (Corner Rectangle)", "Pick first corner",
                 lambda s: s._set_floor_primitive("rect", from_center=False)),
                ("Floor (Center Rectangle)", "Pick centre point",
                 lambda s: s._set_floor_primitive("rect", from_center=True)),
                ("Floor (Polygon)", "Pick first boundary point",
                 lambda s: s._set_floor_primitive("polygon")),
            ],
        }
        self._variant_index = {m: 0 for m in self._PLACEMENT_VARIANTS}
