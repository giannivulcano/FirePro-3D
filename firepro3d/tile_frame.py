"""Block Editor pattern-tile frame (hatch D-A32, concept HD4a).

``TileFrame`` is the pattern-tile subclass of the shared Block Editor
capability frame (``capability_frame.CapabilityFrameItem`` owns the chrome:
overlay tag, dashed accent rect, HALO / pick shape, 35 % preview ring clip,
manipulator anchoring and the delete / snap / gather exclusions). It draws a
dashed rect (0,0)→(w,−h) with a W/H corner grip and a row-shift grip, plus a
live repeat preview of the 8 surrounding cells painted by the renderer's own
lattice builder (``hatch_render.stamp_lattice`` — preview ≡ render).

The tile state itself lives on the scene (``Model_Space.block_capability``,
read through the ``block_tile`` view, in the undo snapshot); this item only
draws and edits it.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt

from .capability_frame import CAPABILITY_FRAME_TAG, CapabilityFrameItem

TILE_FRAME_TAG = CAPABILITY_FRAME_TAG      # HF2 name (one shared overlay tag)

_MIN_TILE = 0.1             # mm — a grip / typed value can't collapse the tile
_EMPTY_TILE = 10.0          # mm — seeded W = H for an empty block (D-A32)
# The repeat preview shows the tile at its authored size so the cells abut the
# frame (ratified HF2 T7); D-A30's 1:100 applies to hatch FILLS in the editor.
_PREVIEW_SCALE = 1.0
_W_GRIP, _SHIFT_GRIP = 0, 1  # grip indices


def seed_tile(items) -> dict:
    """Initial tile (D-A32): lower-left at the origin, W×H = the content's
    extents from the origin; 10×10 when empty.

    Args:
        items: The block's real (non-scaffold) primitives / nested instances.

    Returns:
        A tile dict ``{"w", "h", "row_shift", "size"}`` (Model — D-A38: the
        tile is what you drew, in real mm; Drafting is an explicit choice).
    """
    from .geometry_import import geometric_bounds
    items = list(items)
    r = geometric_bounds(items) if items else None
    if r is None:
        w = h = _EMPTY_TILE
    else:
        w = r.right() if r.right() > 0 else r.width()
        h = -r.top() if r.top() < 0 else r.height()
        w, h = max(w, _MIN_TILE), max(h, _MIN_TILE)
    return {"w": float(w), "h": float(h), "row_shift": 0.0, "size": "model"}


def _fmt(scene, mm: float) -> str:
    sm = getattr(scene, "scale_manager", None)
    return sm.format_length(mm) if sm is not None else f"{mm:.1f}"


def tile_properties(scene) -> dict:
    """Pattern tile panel rows (shared by the frame and the nothing-selected view).

    Args:
        scene: The Block Editor ``Model_Space``.

    Returns:
        Ordered property dict for ``PropertyManager``.
    """
    t = scene.block_tile
    props = {"Pattern tile": {"type": "bool", "value": t is not None,
                              "tooltip": "Make this block a hatch pattern: it repeats "
                                         "on a tile and fills regions instead of "
                                         "being placed as a symbol"}}
    if t is None:
        return props
    props["Width"] = {"type": "dimension", "value": _fmt(scene, t["w"]),
                      "value_mm": t["w"], "minimum": _MIN_TILE,
                      "tooltip": "Tile repeat width"}
    props["Height"] = {"type": "dimension", "value": _fmt(scene, t["h"]),
                       "value_mm": t["h"], "minimum": _MIN_TILE,
                       "tooltip": "Tile repeat height"}
    props["Row shift"] = {"type": "dimension", "value": _fmt(scene, t["row_shift"]),
                          "value_mm": t["row_shift"], "minimum": 0.0,
                          "tooltip": "Horizontal offset of every other row "
                                     "(e.g. half a brick)"}
    props["Size"] = {"type": "enum", "options": ["Drafting", "Model"],
                     "value": "Model" if t["size"] == "model" else "Drafting",
                     "tooltip": "Drafting: tile is in printed mm (scales with the "
                                "view). Model: tile is real size"}
    return props


def _to_mm(scene, value) -> float | None:
    """Panel value → mm: a DimensionEdit hands mm floats; text is parsed."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    from .scale_manager import ScaleManager
    sm = getattr(scene, "scale_manager", None)
    unit = sm.bare_number_unit() if sm is not None else "mm"
    return ScaleManager.parse_dimension(str(value), unit)


def set_tile_property(scene, editor, key, value) -> None:
    """Apply one Pattern tile panel edit as one undo step.

    Args:
        scene: The Block Editor ``Model_Space``.
        editor: The owning ``BlockEditorWidget`` (the toggle runs its refusal).
        key: Panel row key.
        value: The edited value.
    """
    if key == "Pattern tile":
        on = value in (True, "true", "True", 1, Qt.CheckState.Checked)
        if on != (scene.block_tile is not None):
            editor.toggle_pattern_tile()
        return
    t = scene.block_tile
    if t is None:
        return
    t = dict(t)
    if key == "Size":
        t["size"] = "model" if str(value) == "Model" else "drafting"
    else:
        field = {"Width": "w", "Height": "h", "Row shift": "row_shift"}.get(key)
        if field is None:
            return
        mm = _to_mm(scene, value)
        if mm is None:
            return
        t[field] = max(mm, _MIN_TILE) if field in ("w", "h") else max(mm, 0.0)
    # 0 <= row shift <= W on every path (the shift grip clamps the same way).
    t["row_shift"] = min(t["row_shift"], t["w"])
    if t == scene.block_tile:
        return                          # re-committed value: no duplicate step
    scene.set_block_tile(t)


class TileFrame(CapabilityFrameItem):
    """Pattern-tile frame: W/H corner grip + row-shift grip, 8-cell ring.

    Args:
        scene: The Block Editor ``Model_Space`` whose tile this draws.
    """

    KIND = "tile"

    def _rect(self) -> QRectF:
        t = self._cap() or {"w": 0.0, "h": 0.0}
        return QRectF(0.0, -t["h"], t["w"], t["h"])

    def _ring_rect(self) -> QRectF:
        """The 3×3-cell block the preview ring occupies (frame = centre cell)."""
        r = self._rect()
        return r.adjusted(-r.width(), -r.height(), r.width(), r.height())

    def _circular_grips(self) -> set:
        return {_W_GRIP, _SHIFT_GRIP}

    def _paint_ring(self, painter, pen, col) -> None:
        from .hatch_patterns import tile_is_valid
        from .hatch_render import stamp_lattice
        tile = self.scratch_definition()
        if tile is not None and tile_is_valid(tile):
            stamp_lattice(painter, self._ring_rect(), tile, _PREVIEW_SCALE,
                          QPointF(0.0, 0.0), pen, col, tile.tile)

    def grip_points(self) -> list[QPointF]:
        """[W/H corner (top-right), row-shift (top edge)] in scene coords."""
        t = self._cap()
        if t is None:
            return []
        return [QPointF(t["w"], -t["h"]), QPointF(t["row_shift"], -t["h"])]

    def apply_grip(self, index: int, pos: QPointF) -> None:
        """Live grip apply; the manipulator's commit hook pushes the one undo."""
        t = self._cap()
        if t is None:
            return
        if index == _W_GRIP:
            t["w"], t["h"] = max(pos.x(), _MIN_TILE), max(-pos.y(), _MIN_TILE)
            t["row_shift"] = min(t["row_shift"], t["w"])
        elif index == _SHIFT_GRIP:
            t["row_shift"] = min(max(pos.x(), 0.0), t["w"])     # X only
        self._sc.set_block_capability(("tile", t), push_undo=False)


TileFrameItem = TileFrame                  # HF2 name
