"""Block Editor capability panel rows (hatch D-A32 tile, linetypes LT4,
end types LT5 Q12).

One home for the rows both the nothing-selected ``BlockPropertiesInfo`` and
a selected capability frame show, and for their write-back.
"""
from __future__ import annotations

_TILE_TIP = ("Make this block a hatch pattern: it repeats on a tile and fills "
             "regions instead of being placed as a symbol")
_LT_TIP = ("Make this block a linetype: it repeats along lines and is applied "
           "from a line's Linetype row instead of being placed as a symbol")
_OVERLAP_NOTE = "Dashes overlap — edit on the canvas"
_END_TOGGLE_TIP = ("Make this block an end type: it draws on the free ends of open "
            "lines (picked from a line's Start End / Finish End rows) instead "
            "of being placed as a symbol")
_TOGGLES = {"Pattern tile": "tile", "Linetype": "repeat", "End type": "end"}
# LT5 mockup strings (R4).
_END_SIZE_TIP = ("Fixed: 1 mm drawn = 1 mm printed (Drafting rule). "
                 "Weight-relative: 1 mm drawn = 1 × the line's weight.")
_END_TRIM_TIP = ("The line stops this far back from its endpoint, measured "
                 "along the path. Same units as Size.")
_END_PREVIEW_TIP = "This end on a sample line at a thin and a heavy weight."
_WR_SUFFIX = "× line weight"
_END_TRIM_WR_TIP = (_END_TRIM_TIP + " Weight-relative: a plain number "
                    "× line weight (e.g. 1.5).")


def _wr_multiple(value) -> float | None:
    """A Weight-relative Trim entry -> its plain multiple of the weight
    (``"1.5"`` / ``"1.5 × line weight"``), or None if unreadable."""
    s = str(value).replace(_WR_SUFFIX, "").replace("×", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _weight_rows(scene, rows_ok: bool) -> dict:
    """The Weight row (LT4-3): the dashes' shared weight, or ``< mixed >``.

    A dots-only pattern (no dash) shows By Category -- nothing is mixed --
    and the row is disabled (a pick would stamp no dash; review G5 R-N1). A
    dash weight that is not a current weight name is offered as its own
    option (shown, never silently replaced -- as ``stroke_rows`` keeps an
    unresolvable value).
    """
    from . import paper_display as pd
    from . import stroke_style as ss
    from .linetype_authoring import axis_items, pattern_weight
    by_cat = f"By Category ({pd.picker_weight_name(pd.model_blocks_weight())})"
    w = pattern_weight(scene)
    has_dash = any(r[0] == "dash" for _, r in axis_items(scene))
    if w is None:
        value = "< mixed >" if has_dash else by_cat
    else:
        value = by_cat if w == ss.BY_LINETYPE else pd.picker_weight_name(w)
    options = [by_cat, *pd.weight_names()]
    if value not in options:
        options = [value] + options
    tip = ("Weight of every dash — what By Linetype lines draw at"
           if has_dash else "Add a dash to set the linetype's Weight")
    return {"Weight": {"type": "enum", "options": options, "value": value,
                       "disabled": not rows_ok or not has_dash,
                       "tooltip": tip}}


def _default_end_rows(scene) -> dict:
    """Linetype Start End / Finish End rows (LT5 Q11): None | end types."""
    from . import stroke_style as ss
    from .capabilities import end_choices
    from .hatch_patterns import picker_exclude
    reg = getattr(scene, "block_registry", None)
    choices = end_choices(reg, picker_exclude(scene))
    ends = (scene.block_repeat or {}).get("ends") or {}
    rows = {}
    for which, key in zip(ss.ENDS, ("Start End", "Finish End")):
        ref = ends.get(which)
        options = [n for n, _ in choices]
        value = (ss.END_NONE_LABEL if ref is None
                 else next((n for n, r in choices if r == ref), None))
        if value is None:
            value = ss.end_label(ref, ss.CONTINUOUS, reg)
            options = [value] + options
        rows[key] = {"type": "enum", "options": options, "value": value,
                     "tooltip": f"End type every By Linetype line using this "
                                f"linetype draws at its {which}; None draws a "
                                f"plain end"}
    return rows


def capability_rows(scene) -> dict:
    """Ordered panel rows for the editor's capability.

    Args:
        scene: The Block Editor ``Model_Space``.

    Returns:
        Ordered property dict for ``PropertyManager``: the Repeat header and
        the three capability toggles, then the tile rows, the linetype rows
        (Length / Size / Weight / Start End / Finish End, Pattern list,
        Preview swatch) or the end-type rows (Size / Trim, Preview swatch).
    """
    from .tile_frame import tile_properties
    cap = scene.block_capability
    kind = cap[0] if cap else None
    props = {"Repeat": {"type": "header", "value": ""},
             "Pattern tile": {"type": "bool", "value": kind == "tile",
                              "tooltip": _TILE_TIP},
             "Linetype": {"type": "bool", "value": kind == "repeat",
                          "tooltip": _LT_TIP},
             "End type": {"type": "bool", "value": kind == "end",
                          "tooltip": _END_TOGGLE_TIP}}
    if kind == "tile":
        tp = tile_properties(scene)
        tp.pop("Pattern tile", None)
        props.update(tp)
    elif kind == "repeat":
        from .constants import PATTERN_PREVIEW_H_PX
        from .linetype_authoring import (_axis_end, _plain_lines, current_rows,
                                         preview_painter)
        from .tile_frame import _fmt
        rep = scene.block_repeat
        rows = current_rows(scene)
        # H4-f: minimum = the content end. DimensionEdit's minimum is strict
        # (value > minimum), so back off 1e-6 to accept Length == end; the
        # setter's revert (set_repeat_field) stays the second line of defence.
        end = _axis_end(_plain_lines(scene))
        props["Length"] = {"type": "dimension", "value": _fmt(scene, rep["length"]),
                           "value_mm": rep["length"],
                           "minimum": max(end - 1e-6, 0.0),
                           "tooltip": "Period = the sum of the pattern rows; "
                                      "typing a longer value adds a trailing gap"}
        props["Size"] = {"type": "enum", "options": ["Drafting", "Model"],
                         "value": "Model" if rep["size"] == "model" else "Drafting",
                         "tooltip": "Drafting: lengths are printed mm (scale with "
                                    "the view). Model: lengths are real size"}
        props["On screen"] = {
            "type": "enum", "options": ["Fixed size", "Scale with zoom"],
            "value": "Fixed size" if rep.get("screen") == "fixed" else "Scale with zoom",
            "tooltip": "Fixed size: dashes keep the same size on screen at any "
                       "zoom (model views and the Block Editor). Scale with "
                       "zoom: dashes zoom with the drawing. Sheets and PDF "
                       "always print true size"}
        props.update(_weight_rows(scene, rows is not None))
        props.update(_default_end_rows(scene))           # LT5 Q11
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
    elif kind == "end":
        from .constants import PATTERN_PREVIEW_H_PX
        from .end_authoring import SIZE_LABELS
        from .end_authoring import preview_painter as end_preview
        from .end_render import WEIGHT_RELATIVE
        from .tile_frame import _fmt
        end = scene.block_end
        props["Size"] = {"type": "enum", "options": list(SIZE_LABELS.values()),
                         "value": SIZE_LABELS.get(end["size"], "Fixed"),
                         "tooltip": _END_SIZE_TIP}
        if end["size"] == WEIGHT_RELATIVE:
            # A plain multiple of the line's weight -- never a project length
            # (no feet-inches formatting / parsing).
            props["Trim"] = {"type": "string", "value": f"{end['trim']:g}",
                             "suffix": _WR_SUFFIX, "tooltip": _END_TRIM_WR_TIP}
        else:
            props["Trim"] = {"type": "dimension",
                             "value": _fmt(scene, end["trim"]),
                             "value_mm": end["trim"], "minimum": -1e-6,
                             "tooltip": _END_TRIM_TIP}
        props["Preview"] = {"type": "header", "value": ""}
        props["Preview swatch"] = {"type": "stroke_preview", "value": None,
                                   "paint": end_preview(scene),
                                   "height": PATTERN_PREVIEW_H_PX,
                                   "tooltip": _END_PREVIEW_TIP}
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
    if key in _TOGGLES:
        want = _TOGGLES[key]
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
        elif key in ("Size", "On screen"):
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
        elif key in ("Start End", "Finish End"):
            la.set_default_end_from_label(
                scene, "start" if key == "Start End" else "finish", str(value))
    elif kind == "end":
        from . import end_authoring as ea
        if key == "Trim":
            from .end_render import WEIGHT_RELATIVE
            if (scene.block_end or {}).get("size") == WEIGHT_RELATIVE:
                mm = _wr_multiple(value)          # x line weight, plain decimal
            else:
                mm = _to_mm(scene, value)
            if mm is not None:
                ea.set_end_field(scene, "Trim", mm)
        elif key == "Size":
            ea.set_end_field(scene, "Size", value)
