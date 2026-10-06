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
            editor: The owning ``BlockEditorWidget`` (the capability rows --
                Pattern tile / Linetype -- edit through it); None = those
                rows read-only.
        """
        self._scene = scene
        self._name = name
        self._editor = editor
        # The panel's ScaleManager source (PropertyManager._get_scale_manager):
        # dimension fields follow the project's display units. Deliberately
        # not a ``scene()`` method -- see the module docstring.
        self._scene_ref = scene

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
        # Capability (hatch D-A32 tile / linetypes LT4 repeat): the same rows
        # the selected capability frame shows.
        from .capability_panel import capability_rows
        props.update(capability_rows(self._scene))
        return props

    def set_property(self, key, value) -> None:
        """Block facts are read-only; the capability rows edit the capability."""
        if self._editor is not None:
            from .capability_panel import set_capability_property
            set_capability_property(self._scene, self._editor, key, value)
