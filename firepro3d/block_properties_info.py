"""Property-panel adapter for the Block Editor with nothing selected.

parametric-constraint-system.md D40: the block's name, read-only facts and
the sketch constraint status. Block attributes join this view with SB1a.
Deliberately has no ``scene()`` -- the panel's Constraints section is for a
selected entity only.
"""
from __future__ import annotations

from .element_params import NONE_LABEL, WARN_MARK, category_choice, unknown_label
from .system_blocks import SYMBOL_CATEGORIES

_SCALE_LABELS = {"real_size": "Real size", "annotative": "Annotative"}
_SCALE_MODES = {v: k for k, v in _SCALE_LABELS.items()}
_TEXT_SIZING_LABELS = ("Real size", "Printed")     # schematics, N11


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
        if schematic:
            props.update(self._text_rows())
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
            opts, cur, warn = category_choice(meta["host_category"])
            props["Host category"] = {"type": "enum", "options": opts, "value": cur,
                                      "warn_options": warn}
            props["Scale mode"] = {"type": "enum", "options": ["Real size", "Annotative"],
                                   "value": _SCALE_LABELS.get(meta["scale_mode"], "Real size")}
            if meta["scale_mode"] == "real_size":
                # SB4g R10: which element's symbol this block may draw.
                cur = meta.get("symbol_for", "")
                opts, warn = [NONE_LABEL, *SYMBOL_CATEGORIES], []
                if cur and cur not in SYMBOL_CATEGORIES:     # kept from a file (E9)
                    cur = unknown_label(cur, "symbol category")
                    opts, warn = opts + [cur], [cur]
                props["Symbol for"] = {"type": "enum", "options": opts,
                                       "value": cur or NONE_LABEL, "warn_options": warn}
            if meta["scale_mode"] == "annotative" and self._screen_row_free():
                from .end_render import SCREEN_FIXED
                from .linetype_render import SCREEN_LABELS
                # SB1c D8: the ET1 / LTS-1 On screen idiom, annotative only.
                props["On screen"] = {
                    "type": "enum", "options": list(SCREEN_LABELS),
                    "value": (SCREEN_LABELS[0] if meta.get("annotative_screen") == SCREEN_FIXED
                              else SCREEN_LABELS[1])}
            props["Sample values"] = {"type": "bool",
                                      "value": self._scene.show_sample_values}
        return props

    def _text_rows(self) -> dict:
        """A schematic's Text sizing row, plus Drawing scale while Printed (N11)."""
        from .annotative import editor_text_printed, editor_text_scale
        from .stroke_style import model_scale_label, model_scale_options
        printed = editor_text_printed(self._scene)
        rows = {"Text sizing": {"type": "enum", "options": list(_TEXT_SIZING_LABELS),
                                "value": _TEXT_SIZING_LABELS[1 if printed else 0]}}
        if printed:
            value = model_scale_label(editor_text_scale(self._scene))
            options = model_scale_options()
            if value not in options:
                options = [value, *options]
            rows["Drawing scale"] = {"type": "enum", "options": options, "value": value}
        return rows

    def _set_text_sizing(self, label: str) -> None:
        """Real size drops both keys; Printed starts at the project scale. Text
        keeps its stored size, so the editor looks the same (N13)."""
        meta = {k: v for k, v in self._scene.block_meta.items()
                if k not in ("text_sizing", "text_scale")}
        if label == _TEXT_SIZING_LABELS[1] and self._editor is not None:
            meta.update(text_sizing="printed", text_scale=self._editor.project_text_scale())
        self._scene.set_block_meta(meta)

    def _screen_row_free(self) -> bool:
        """True unless a linetype / end capability already owns the
        "On screen" row (capability_panel; one key, one meaning)."""
        cap = self._scene.block_capability
        return cap is None or cap[0] not in ("repeat", "end")

    def _open_attributes_editor(self) -> None:
        if self._editor is not None:
            self._editor.open_attributes_editor()

    def set_property(self, key, value) -> None:
        """Block facts are read-only; the capability rows edit the capability."""
        if key == "Host category":
            value = str(value)
            if value.startswith(WARN_MARK):         # the kept unknown entry (E9)
                return
            self._scene.set_block_meta({**self._scene.block_meta,
                                        "host_category": "" if value == NONE_LABEL else value})
            return
        if key == "Symbol for":
            value = str(value)
            if value.startswith(WARN_MARK):         # the kept unknown entry
                return
            self._scene.set_block_meta({**self._scene.block_meta,
                                        "symbol_for": "" if value == NONE_LABEL else value})
            return
        if key == "Sample values":
            self._scene.set_show_sample_values(bool(value))    # view toggle, no undo
            return
        if key == "Text sizing":
            self._set_text_sizing(str(value))
            return
        if key == "Drawing scale":
            from .stroke_style import model_scale_from_label
            n = model_scale_from_label(value)
            if n is not None and self._editor is not None:
                # A refusal needs no signal: PropertyManager._apply_property always
                # starts its refresh timer, which rebuilds the row from get_properties.
                self._editor.set_text_scale(n)
            return
        if key == "Scale mode":
            self._scene.set_block_meta({**self._scene.block_meta,
                                        "scale_mode": _SCALE_MODES.get(str(value), "real_size")})
            return
        if key == "On screen" and self._screen_row_free():
            from .end_render import SCREEN_FIXED, SCREEN_SCALE
            from .linetype_render import SCREEN_LABELS
            self._scene.set_block_meta({**self._scene.block_meta,
                                        "annotative_screen": (SCREEN_FIXED if str(value) == SCREEN_LABELS[0]
                                                              else SCREEN_SCALE)})
            return
        if self._editor is not None:
            from .capability_panel import set_capability_property
            set_capability_property(self._scene, self._editor, key, value)
