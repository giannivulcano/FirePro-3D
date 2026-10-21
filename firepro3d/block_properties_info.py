"""Property-panel adapter for the Block Editor with nothing selected.

parametric-constraint-system.md D40: the block's name, read-only facts and
the sketch constraint status. Block attributes join this view with SB1a.
Deliberately has no ``scene()`` -- the panel's Constraints section is for a
selected entity only.
"""
from __future__ import annotations

_SCALE_LABELS = {"real_size": "Real size", "annotative": "Annotative"}
_SCALE_MODES = {v: k for k, v in _SCALE_LABELS.items()}


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
        schematic = getattr(self._editor, "kind", "block") == "schematic"
        props = {
            ("Schematic" if schematic else "Block"): {"type": "header", "value": ""},
            "Name": {"type": "string", "value": self._name, "readonly": True},
            "Primitives": {"type": "string", "value": str(len(ctl.primitive_uids())),
                           "readonly": True},
            "Constraints": {"type": "string", "value": str(len(ctl.constraints)),
                            "readonly": True},
            "Status": {"type": "status", "value": text, "state": state},
        }
        # Capability (hatch D-A32 tile / linetypes LT4 repeat / LT5 end): the
        # same rows the selected capability frame shows -- none for a
        # schematic (schematics.md D-S14).
        if not schematic:
            from .capability_panel import capability_rows
            props.update(capability_rows(self._scene))
            meta = self._scene.block_meta
            props["Attributes"] = {"type": "header", "value": "Attributes"}
            props["Count"] = {"type": "string", "value": str(len(meta["attributes"])),
                              "readonly": True}
            props["Edit attributes"] = {
                "type": "button", "value": "Edit attributes\u2026",
                "callback": self._open_attributes_editor,
                "enabled": self._editor is not None}
            props["Host category"] = {"type": "string", "value": meta["host_category"]}
            props["Scale mode"] = {"type": "enum", "options": ["Real size", "Annotative"],
                                   "value": _SCALE_LABELS.get(meta["scale_mode"], "Real size")}
            props["Sample values"] = {"type": "bool",
                                      "value": self._scene.show_sample_values}
        return props

    def _open_attributes_editor(self) -> None:
        if self._editor is not None:
            self._editor.open_attributes_editor()

    def set_property(self, key, value) -> None:
        """Block facts are read-only; the capability rows edit the capability."""
        if key == "Host category":
            self._scene.set_block_meta({**self._scene.block_meta,
                                        "host_category": str(value)})
            return
        if key == "Sample values":
            self._scene.set_show_sample_values(bool(value))    # view toggle, no undo
            return
        if key == "Scale mode":
            self._scene.set_block_meta({**self._scene.block_meta,
                                        "scale_mode": _SCALE_MODES.get(str(value), "real_size")})
            return
        if self._editor is not None:
            from .capability_panel import set_capability_property
            set_capability_property(self._scene, self._editor, key, value)
