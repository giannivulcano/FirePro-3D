"""Block Editor pattern-tile frame (hatch D-A32, concept HD4a).

``TileFrameItem`` is a non-primitive overlay (``data(0) == "tile_frame"``):
a dashed accent rect (0,0)→(w,−h) with a W/H corner grip and a row-shift
grip, plus a live repeat preview of the 8 surrounding cells painted by the
renderer's own lattice builder (``hatch_render.stamp_lattice`` — preview ≡
render). It is selectable and HALO-pickable so the manipulator can show its
grips (U3); a no-op ``manip_translate`` keeps it anchored at the block
origin. It is excluded from ``gather_primitives`` (not in any tracking
list), snap targets (``snap_engine._NON_TARGET_TAGS``) and delete
(``Model_Space.delete_items``); a Block Editor scene never reaches paper.

The tile state itself lives on the scene (``Model_Space.block_tile``, in the
undo snapshot); this item only draws and edits it.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QGraphicsItem

from .constants import Z_BELOW_GEOMETRY

TILE_FRAME_TAG = "tile_frame"
_MIN_TILE = 0.1             # mm — a grip / typed value can't collapse the tile
_EMPTY_TILE = 10.0          # mm — seeded W = H for an empty block (D-A32)
_PREVIEW_OPACITY = 0.35     # repeat-preview opacity (mockup gate, variant A)
_PREVIEW_SCALE = 1.0        # preview cells are tile-local mm: they abut the frame
_FRAME_DASH = [5, 4]        # dash pattern in pen widths (= px at the 1 px cosmetic pen)
_FRAME_PEN_PX = 1.0         # cosmetic frame / preview pen width
_HIT_PX = 8.0               # frame pick stroke width, screen px
_W_GRIP, _SHIFT_GRIP = 0, 1  # grip indices


def seed_tile(items) -> dict:
    """Initial tile (D-A32): lower-left at the origin, W×H = the content's
    extents from the origin; 10×10 when empty.

    Args:
        items: The block's real (non-scaffold) primitives / nested instances.

    Returns:
        A tile dict ``{"w", "h", "row_shift", "size"}`` (Drafting).
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
    return {"w": float(w), "h": float(h), "row_shift": 0.0, "size": "drafting"}


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
    scene.set_block_tile(t)


class TileFrameItem(QGraphicsItem):
    """The editable tile frame + repeat preview of one Block Editor scene.

    Args:
        scene: The Block Editor ``Model_Space`` whose ``block_tile`` this draws.
    """

    def __init__(self, scene):
        super().__init__()
        self._sc = scene
        self.setData(0, TILE_FRAME_TAG)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(Z_BELOW_GEOMETRY + 1)
        self._preview = None            # scratch tile BlockDefinition, or None

    # ── geometry ──────────────────────────────────────────────────────────
    def _rect(self) -> QRectF:
        t = self._sc.block_tile or {"w": 0.0, "h": 0.0}
        return QRectF(0.0, -t["h"], t["w"], t["h"])

    def _ring_rect(self) -> QRectF:
        """The 3×3-cell block the preview ring occupies (frame = centre cell)."""
        r = self._rect()
        return r.adjusted(-r.width(), -r.height(), r.width(), r.height())

    def boundingRect(self) -> QRectF:
        return self._ring_rect().adjusted(-1.0, -1.0, 1.0, 1.0)

    def shape(self) -> QPainterPath:
        from .view_scale import scene_hit_width
        p = QPainterPath()
        p.addRect(self._rect())
        s = QPainterPathStroker()
        s.setWidth(scene_hit_width(self, _HIT_PX, 1.0))
        return s.createStroke(p)

    def halo_trace_path(self, scene_scale=None) -> QPainterPath:
        """HALO trace = the frame outline only (never an area: a click on the
        content inside the frame must pick the content)."""
        p = QPainterPath()
        p.addRect(self._rect())
        return p

    def manip_bounds(self) -> QRectF:
        """The manipulator wraps the tile rect, not the preview ring."""
        return self.mapRectToScene(self._rect())

    def manip_frame_redundant(self) -> bool:
        """The dashed tile rect is already the box — no second dashed frame."""
        return True

    def prepare_tile_change(self) -> None:
        """Call BEFORE the scene's tile changes: the bounds derive from it."""
        self.prepareGeometryChange()

    def invalidate_preview(self) -> None:
        """Content or tile changed: rebuild the scratch tile on next paint."""
        self._preview = None
        self.update()

    def _scratch_tile(self):
        """A throwaway tile definition compiled from the live editor content."""
        if self._preview is None and self._sc.block_tile:
            from .block_definition import BlockDefinition
            editor = getattr(self._sc, "_tile_editor", None)
            items = editor.gather_primitives() if editor is not None else []
            prims = [it.to_nested_dict() if hasattr(it, "to_nested_dict") else it.to_dict()
                     for it in items]
            d = BlockDefinition.new(name="preview", library="", series="",
                                    primitives=prims, origin=(0.0, 0.0),
                                    tile=self._sc.block_tile)
            d._resolve = self._sc.get_block_definition
            self._preview = d
        return self._preview

    # ── paint ─────────────────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        t = self._sc.block_tile
        if t is None:
            return
        from . import theme as th
        from .hatch_patterns import tile_is_valid
        tok = th.detect()
        tile = self._scratch_tile()
        if tile is not None and tile_is_valid(tile):
            from .hatch_render import stamp_lattice
            ring = QPainterPath()
            ring.addRect(self._ring_rect())
            inner = QPainterPath()
            inner.addRect(self._rect())
            col = QColor(tok.text_primary)
            pen = QPen(col, _FRAME_PEN_PX)
            pen.setCosmetic(True)
            painter.save()
            painter.setClipPath(ring.subtracted(inner), Qt.ClipOperation.IntersectClip)
            painter.setOpacity(painter.opacity() * _PREVIEW_OPACITY)
            stamp_lattice(painter, self._ring_rect(), tile, _PREVIEW_SCALE,
                          QPointF(0.0, 0.0), pen, col, tile.tile)
            painter.restore()
        pen = QPen(QColor(tok.accent_primary), _FRAME_PEN_PX)
        pen.setCosmetic(True)
        pen.setDashPattern(_FRAME_DASH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect())

    # ── manipulator / grip protocol (U3) ──────────────────────────────────
    def grip_points(self) -> list[QPointF]:
        """[W/H corner (top-right), row-shift (top edge)] in scene coords."""
        t = self._sc.block_tile
        if t is None:
            return []
        return [QPointF(t["w"], -t["h"]), QPointF(t["row_shift"], -t["h"])]

    def apply_grip(self, index: int, pos: QPointF) -> None:
        """Live grip apply; the manipulator's commit hook pushes the one undo."""
        t = self._sc.block_tile
        if t is None:
            return
        t = dict(t)
        if index == _W_GRIP:
            t["w"], t["h"] = max(pos.x(), _MIN_TILE), max(-pos.y(), _MIN_TILE)
            t["row_shift"] = min(t["row_shift"], t["w"])
        elif index == _SHIFT_GRIP:
            t["row_shift"] = min(max(pos.x(), 0.0), t["w"])     # X only
        self._sc.set_block_tile(t, push_undo=False)

    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={_W_GRIP, _SHIFT_GRIP})

    def manip_translate(self, dx: float, dy: float) -> None:
        """Parity-only (the manipulator wraps translate-capable items): the
        frame is anchored at the block origin (D-A32), so a body drag is inert."""

    def manip_capabilities(self) -> set:
        return {"translate"}

    # ── property panel ────────────────────────────────────────────────────
    def get_properties(self) -> dict:
        return tile_properties(self._sc)

    def set_property(self, key, value) -> None:
        editor = getattr(self._sc, "_tile_editor", None)
        if editor is not None:
            set_tile_property(self._sc, editor, key, value)
