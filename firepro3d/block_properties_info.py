"""Property-panel adapter for the Block Editor with nothing selected.

parametric-constraint-system.md D40: the block's name, read-only facts and
the sketch constraint status. Block attributes join this view with SB1a.
Deliberately has no ``scene()`` -- the panel's Constraints section is for a
selected entity only.
"""
from __future__ import annotations


class BlockPropertiesInfo:
    """``get_properties`` view of one Block Editor scene."""

    def __init__(self, scene, name: str, editor=None):
        """Bind the view to one editor scene.

        Args:
            scene: The Block Editor ``Model_Space``.
            name: The block's display name.
            editor: The owning ``BlockEditorWidget`` (Pattern tile rows edit
                through it); None = tile rows read-only.
        """
        self._scene = scene
        self._name = name
        self._editor = editor

    def get_properties(self) -> dict:
        ctl = self._scene.constraint_ctl
        text, state = ctl.sketch_state()
        props = {
            "Block": {"type": "header", "value": ""},
            "Name": {"type": "string", "value": self._name, "readonly": True},
            "Primitives": {"type": "string", "value": str(len(ctl.primitive_uids())),
                           "readonly": True},
            "Constraints": {"type": "string", "value": str(len(ctl.constraints)),
                            "readonly": True},
            "Status": {"type": "status", "value": text, "state": state},
        }
        # Pattern tile (hatch D-A32): the same rows the selected frame shows.
        from .tile_frame import tile_properties
        props["Pattern"] = {"type": "header", "value": ""}
        props.update(tile_properties(self._scene))
        return props

    def set_property(self, key, value) -> None:
        """Block facts are read-only; the Pattern tile rows edit the tile."""
        if self._editor is not None:
            from .tile_frame import set_tile_property
            set_tile_property(self._scene, self._editor, key, value)
