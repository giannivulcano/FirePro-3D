"""Block Editor capability panel rows (hatch D-A32 tile, linetypes LT4).

One home for the rows both the nothing-selected ``BlockPropertiesInfo`` and
a selected capability frame show, and for their write-back.
"""
from __future__ import annotations

_TILE_TIP = ("Make this block a hatch pattern: it repeats on a tile and fills "
             "regions instead of being placed as a symbol")
_LT_TIP = ("Make this block a linetype: it repeats along lines and is applied "
           "from a line's Linetype row instead of being placed as a symbol")
_OVERLAP_NOTE = "Dashes overlap — edit on the canvas"


def _weight_rows(scene, rows_ok: bool) -> dict:
    """The Weight row (LT4-3): the dashes' shared weight, or ``< mixed >``."""
    from . import paper_display as pd
    from . import stroke_style as ss
    from .linetype_authoring import pattern_weight
    by_cat = f"By Category ({pd.model_blocks_weight()})"
    w = pattern_weight(scene)
    value = "< mixed >" if w is None else (by_cat if w == ss.BY_LINETYPE else w)
    options = [by_cat, *pd.weight_names()]
    if value == "< mixed >":
        options = [value] + options
    return {"Weight": {"type": "enum", "options": options, "value": value,
                       "disabled": not rows_ok,
                       "tooltip": "Weight of every dash — what By Linetype "
                                  "lines draw at"}}


def capability_rows(scene) -> dict:
    """Ordered panel rows for the editor's capability.

    Args:
        scene: The Block Editor ``Model_Space``.

    Returns:
        Ordered property dict for ``PropertyManager``: the Repeat header and
        the two capability toggles, then the tile rows or the linetype rows
        (Length / Size / Weight, Pattern list, Preview swatch).
    """
    from .tile_frame import tile_properties
    cap = scene.block_capability
    kind = cap[0] if cap else None
    props = {"Repeat": {"type": "header", "value": ""},
             "Pattern tile": {"type": "bool", "value": kind == "tile",
                              "tooltip": _TILE_TIP},
             "Linetype": {"type": "bool", "value": kind == "repeat",
                          "tooltip": _LT_TIP}}
    if kind == "tile":
        tp = tile_properties(scene)
        tp.pop("Pattern tile", None)
        props.update(tp)
    elif kind == "repeat":
        from .constants import PATTERN_PREVIEW_H_PX
        from .linetype_authoring import current_rows, preview_painter
        from .tile_frame import _fmt
        rep = scene.block_repeat
        rows = current_rows(scene)
        props["Length"] = {"type": "dimension", "value": _fmt(scene, rep["length"]),
                           "value_mm": rep["length"], "minimum": 0.0,
                           "tooltip": "Period = the sum of the pattern rows; "
                                      "typing a longer value adds a trailing gap"}
        props["Size"] = {"type": "enum", "options": ["Drafting", "Model"],
                         "value": "Model" if rep["size"] == "model" else "Drafting",
                         "tooltip": "Drafting: lengths are printed mm (scale with "
                                    "the view). Model: lengths are real size"}
        props.update(_weight_rows(scene, rows is not None))
        props["Pattern"] = {"type": "header", "value": ""}
        props["Pattern rows"] = {"type": "pattern_list", "value": rows,
                                 "note": "" if rows is not None else _OVERLAP_NOTE,
                                 "tooltip": "Dashes, gaps and dots in order "
                                            "along the line"}
        props["Preview"] = {"type": "header", "value": ""}
        props["Preview swatch"] = {"type": "stroke_preview", "value": None,
                                   "paint": preview_painter(scene),
                                   "height": PATTERN_PREVIEW_H_PX,
                                   "tooltip": "A sample line and an L-shaped "
                                              "polyline drawn with this linetype"}
    return props


def set_capability_property(scene, editor, key, value) -> None:
    """Apply one capability row edit (each is one undo step).

    Args:
        scene: The Block Editor ``Model_Space``.
        editor: The owning ``BlockEditorWidget`` (the toggles run its refusals).
        key: Panel row key.
        value: The edited value.
    """
    from . import linetype_authoring as la
    from .tile_frame import _to_mm, set_tile_property

    def _on(v):
        from PyQt6.QtCore import Qt
        return v in (True, "true", "True", 1, Qt.CheckState.Checked)

    cap = scene.block_capability
    kind = cap[0] if cap else None
    if key in ("Pattern tile", "Linetype"):
        want = "tile" if key == "Pattern tile" else "repeat"
        if _on(value) != (kind == want):
            editor.toggle_capability(want)
        return
    if kind == "tile":
        set_tile_property(scene, editor, key, value)
    elif kind == "repeat":
        if key == "Length":
            mm = _to_mm(scene, value)
            if mm is not None:
                la.set_repeat_field(scene, key, mm)
        elif key == "Size":
            la.set_repeat_field(scene, key, value)
        elif key == "Weight":
            from . import stroke_style as ss
            v = str(value)
            if v == "< mixed >":
                return
            la.set_pattern_weight(scene, ss.BY_LINETYPE if v.startswith("By Category")
                                  else v)
        elif key == "Pattern rows":
            la.apply_pattern_rows(scene, value)
