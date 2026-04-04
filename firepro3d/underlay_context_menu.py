"""
Underlay Context Menu
=====================
Right-click context menu for underlay items (PDF / DXF) in the scene.
Provides: Scale, Rotate, Opacity, Change Layer, Lock/Unlock, Refresh from disk, Remove.
"""

from PyQt6.QtWidgets import (
    QMenu, QInputDialog, QGraphicsItem, QGraphicsItemGroup
)
from PyQt6.QtGui import QAction, QPen, QColor
from .underlay import Underlay
from .constants import DEFAULT_USER_LAYER


class UnderlayContextMenu:
    """
    Creates and shows a context menu for a given underlay (data, item) pair.
    `scene` must be the Model_Space that owns the underlay list.
    """

    @staticmethod
    def show(scene, underlay_data: Underlay, underlay_item: QGraphicsItem, screen_pos):
        """Build and exec the context menu at *screen_pos* (global coords)."""
        menu = QMenu()

        # ── Scale ────────────────────────────────────────────────────
        scale_action = QAction(f"Scale… (current: {underlay_data.scale:.3f})", menu)
        scale_action.triggered.connect(
            lambda: UnderlayContextMenu._set_scale(scene, underlay_data, underlay_item)
        )
        menu.addAction(scale_action)

        # ── Rotate ───────────────────────────────────────────────────
        rotate_action = QAction(f"Rotate… (current: {underlay_data.rotation:.1f}°)", menu)
        rotate_action.triggered.connect(
            lambda: UnderlayContextMenu._set_rotation(scene, underlay_data, underlay_item)
        )
        menu.addAction(rotate_action)

        # ── Opacity ──────────────────────────────────────────────────
        opacity_pct = int(underlay_data.opacity * 100)
        opacity_action = QAction(f"Opacity… (current: {opacity_pct}%)", menu)
        opacity_action.triggered.connect(
            lambda: UnderlayContextMenu._set_opacity(scene, underlay_data, underlay_item)
        )
        menu.addAction(opacity_action)

        # ── Change Layer ─────────────────────────────────────────────
        layer_action = QAction(
            f"Change Layer… (current: {underlay_data.user_layer})", menu)
        layer_action.triggered.connect(
            lambda: UnderlayContextMenu._change_layer(
                scene, underlay_data, underlay_item)
        )
        menu.addAction(layer_action)

        menu.addSeparator()

        # ── Reset Transform ────────────────────────────────────────
        reset_action = QAction("↩ Reset Transform", menu)
        reset_action.triggered.connect(
            lambda: UnderlayContextMenu._reset_transform(scene, underlay_data, underlay_item)
        )
        menu.addAction(reset_action)

        # ── Duplicate ──────────────────────────────────────────────
        dup_action = QAction("Duplicate", menu)
        dup_action.triggered.connect(
            lambda: UnderlayContextMenu._duplicate(scene, underlay_data, underlay_item)
        )
        menu.addAction(dup_action)

        menu.addSeparator()

        # ── Lock / Unlock ────────────────────────────────────────────
        if underlay_data.locked:
            lock_action = QAction("🔓 Unlock", menu)
        else:
            lock_action = QAction("🔒 Lock", menu)
        lock_action.triggered.connect(
            lambda: UnderlayContextMenu._toggle_lock(scene, underlay_data, underlay_item)
        )
        menu.addAction(lock_action)

        # ── Refresh from disk ────────────────────────────────────────
        refresh_action = QAction("🔄 Refresh from Disk", menu)
        refresh_action.triggered.connect(
            lambda: scene.refresh_underlay(underlay_data, underlay_item)
        )
        menu.addAction(refresh_action)

        menu.addSeparator()

        # ── Remove ───────────────────────────────────────────────────
        remove_action = QAction("❌ Remove Underlay", menu)
        remove_action.triggered.connect(
            lambda: scene.remove_underlay(underlay_data, underlay_item)
        )
        menu.addAction(remove_action)

        menu.exec(screen_pos)

    # ─── action handlers ─────────────────────────────────────────────

    @staticmethod
    def _set_scale(scene, data: Underlay, item: QGraphicsItem):
        val, ok = QInputDialog.getDouble(
            scene.views()[0] if scene.views() else None,
            "Set Underlay Scale",
            "Scale factor:",
            data.scale, 0.001, 1000.0, 4
        )
        if ok:
            data.scale = val
            item.setScale(val)
            scene.push_undo_state()

    @staticmethod
    def _set_rotation(scene, data: Underlay, item: QGraphicsItem):
        val, ok = QInputDialog.getDouble(
            scene.views()[0] if scene.views() else None,
            "Set Underlay Rotation",
            "Rotation (degrees):",
            data.rotation, -360.0, 360.0, 1
        )
        if ok:
            data.rotation = val
            item.setRotation(val)
            scene.push_undo_state()

    @staticmethod
    def _set_opacity(scene, data: Underlay, item: QGraphicsItem):
        val, ok = QInputDialog.getInt(
            scene.views()[0] if scene.views() else None,
            "Set Underlay Opacity",
            "Opacity (0–100%):",
            int(data.opacity * 100), 0, 100
        )
        if ok:
            data.opacity = val / 100.0
            item.setOpacity(data.opacity)
            scene.push_undo_state()

    @staticmethod
    def _change_layer(scene, data: Underlay, item: QGraphicsItem):
        """Let the user pick a new layer for this underlay."""
        # Gather layer names from UserLayerManager
        layer_names = [DEFAULT_USER_LAYER]
        if hasattr(scene, "_user_layer_manager") and scene._user_layer_manager:
            layer_names = [lyr.name for lyr in scene._user_layer_manager.layers]

        current_idx = 0
        if data.user_layer in layer_names:
            current_idx = layer_names.index(data.user_layer)

        parent = scene.views()[0] if scene.views() else None
        new_layer, ok = QInputDialog.getItem(
            parent,
            "Change Underlay Layer",
            "Select layer:",
            layer_names,
            current_idx,
            False,  # not editable
        )
        if ok and new_layer:
            data.user_layer = new_layer
            # Derive new colour/lineweight from the chosen layer
            color, lw = scene._underlay_color_lw(new_layer)
            data.colour = color.name()
            data.line_weight = lw
            # Update all child items in the group
            pen = QPen(color, lw)
            pen.setCosmetic(True)
            if isinstance(item, QGraphicsItemGroup):
                for child in item.childItems():
                    if hasattr(child, "setPen"):
                        child.setPen(pen)
                    if hasattr(child, "setDefaultTextColor"):
                        child.setDefaultTextColor(color)
            scene.push_undo_state()

    @staticmethod
    def _toggle_lock(scene, data: Underlay, item: QGraphicsItem):
        data.locked = not data.locked
        if data.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        else:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        scene.push_undo_state()

    @staticmethod
    def _reset_transform(scene, data: Underlay, item: QGraphicsItem):
        """Reset scale, rotation, and opacity to defaults."""
        data.scale = 1.0
        data.rotation = 0.0
        data.opacity = 1.0
        item.setScale(1.0)
        item.setRotation(0.0)
        item.setOpacity(1.0)
        scene.push_undo_state()

    @staticmethod
    def _duplicate(scene, data: Underlay, item: QGraphicsItem):
        """Duplicate the underlay with a small position offset."""
        new_data = Underlay(
            type=data.type, path=data.path,
            x=data.x + 50, y=data.y + 50,
            scale=data.scale, rotation=data.rotation,
            opacity=data.opacity, locked=False,
            page=data.page, dpi=data.dpi,
            colour=data.colour, line_weight=data.line_weight,
            user_layer=data.user_layer,
        )
        if data.type == "pdf":
            scene.import_pdf(
                data.path, dpi=data.dpi, page=data.page,
                x=new_data.x, y=new_data.y, _record=new_data,
            )
        elif data.type == "dxf":
            scene.import_dxf(
                data.path, color=QColor(data.colour),
                line_weight=data.line_weight,
                x=new_data.x, y=new_data.y,
                _record=new_data, user_layer=data.user_layer,
            )
        scene.push_undo_state()
