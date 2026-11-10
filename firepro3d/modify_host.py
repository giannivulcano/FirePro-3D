"""Modify-tool host contract (elevation-parity design D2; scene-tools.md I1).

``ModifyHostMixin`` is what a ``QGraphicsScene`` subclass needs to mount one
``ModifyToolsController`` (``self._modify_ctl``): the modify-mode state, the
modify slice of the press / move / preview / typed-input dispatch, the
``set_mode`` refusal gates, the status / instruction signals, the clipboard
read, the generic Move commit and the scene shells the dispatch rows name.
``Model_Space`` (plan, detail, Block Editor, schematic) and ``SectionScene``
mix it in. A host sets ``scene_role`` and ``constraint_ctl``, defines every
method in :data:`REQUIRED_HOST_METHODS`, then calls :meth:`_init_modify_host`.

The methods were moved verbatim from ``model_space.py`` / ``model_view.py``
(behaviour-neutral for every Model_Space host). The generic entry points
(``set_mode``, ``modify_mouse_press``, ``modify_mouse_move``,
``modify_key_press``) serve hosts without Model_Space's event pipeline;
``Model_Space`` overrides ``set_mode`` and keeps its own mouse / key handlers,
which dispatch through the same tables.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import QPointF, pyqtSignal
from PyQt6.QtWidgets import QApplication

from .constants import ARRAY_DEFAULT_MEMORY
from .modify_tools_controller import ModifyToolsController


class _NullPreview:
    """No-op stand-in for Model_Space's ``preview_node`` / ``preview_pipe``
    scene items on a host that has none (the modify tools only hide / place
    them)."""

    def hide(self):
        pass

    def show(self):
        pass

    def setPos(self, *_args):
        pass

    def isVisible(self):
        return False


_NULL_PREVIEW = _NullPreview()

#: Methods every modify host defines itself. Not given mixin defaults on
#: purpose: scene items duck-type ``push_undo_state`` with ``hasattr``
#: (geometry_2d, gridline, roof, text_item, wall_opening, section_marker),
#: so a raising default would turn their check into a crash.
REQUIRED_HOST_METHODS = ("push_undo_state", "_clipboard_item_dicts",
                         "paste_items", "_paste_accepts", "_add_from_dict",
                         "_bulk_delete", "select_items")


class ModifyHostMixin:
    """Host contract of ``ModifyToolsController`` (see module docstring)."""

    instructionChanged = pyqtSignal(str)  # emits step-by-step instruction text
    modeChanged = pyqtSignal(str)      # emits mode name for status bar instructions

    # ── Class defaults (instance assignments in a host win) ──────────────
    mode = None
    view_available = True          # False while the canvas shows no view (view-3d.md I5)
    _last_scene_pos = None         # last cursor position (paste ghost start)
    # Snap hook (D3 supplies a SnapEngine on SectionScene): None = no snap.
    _snap_engine = None
    _snap_enabled = False
    _snap_result = None
    _align_result = None
    _align_track_ray = None
    preview_node = _NULL_PREVIEW
    preview_pipe = _NULL_PREVIEW
    # Paste D13 gates read the 2D-geometry registry (Model_Space has one).
    _GEOM_TYPE_REGISTRY: dict = {}

    def _init_modify_host(self) -> None:
        """Compose the host's ModifyToolsController and set every modify
        transient (moved from Model_Space.__init__).

        Call once from the host's ``__init__``, after ``scene_role`` and
        ``constraint_ctl`` exist.

        Raises:
            TypeError: The host lacks a method in REQUIRED_HOST_METHODS.
        """
        missing = [n for n in REQUIRED_HOST_METHODS
                   if not callable(getattr(self, n, None))]
        if missing:
            raise TypeError(f"{type(self).__name__} is not a modify host: "
                            f"missing {', '.join(missing)}")
        # model_space.py:244-246
        self._modify_ctl = ModifyToolsController(self)  # modify-tool concern (scene-tools.md I1)
        self._copy_is_cut = False   # set by ModifyToolsController.start(): Cut vs Copy
        self._paste_payload = None  # armed clipboard payload while in "paste" (D5)
        # model_space.py:272, 275
        self.pick_base_pos = None     # QPointF: move / paste / duplicate base
        self._selected_items = None
        # model_space.py:458-461
        self._move_ghost: list = []          # list[QPainterPath] in scene coords
        self._move_ghost_base: list = []      # base paths captured at first click
        self._ghost_dimmed: list = []         # [(item, prior opacity)] dimmed originals (D11)
        self._move_handle_session = None      # S2 HandleSnapSession (Move tool)
        # model_space.py:519-526
        # Offset (scene-tools.md D9) — behaviour in ModifyToolsController; the
        # ghost is the candidate item's trace in _move_ghost.
        self._offset_source = None              # armed source item
        self._offset_dist: float = 0.0          # offset magnitude (mm)
        self._offset_side: float = 1.0          # +1 outward / left normal, -1 otherwise
        self._offset_typed: bool = False        # distance locked by the HUD
        self._offset_sticky = None              # last committed distance (D9 step 5)
        self._offset_sticky_locked: bool = False  # sticky distance was typed
        # model_space.py:538-578
        # Interactive transforms (Rotate, Scale, Mirror)
        # Rotate (scene-tools.md D8; behaviour in ModifyToolsController):
        # pivot, start-ray heading (Y-up deg) and the painted pivot->cursor ray.
        self._rotate_pivot: "QPointF | None" = None
        self._rotate_start_deg: "float | None" = None
        self._rotate_ray = None
        # Array (scene-tools.md D10 + P1 DD5; behaviour in
        # ModifyToolsController). Transient — cleared by
        # ModifyToolsController.clear() on leaving "array": base point
        # (Polar: centre), unit direction, cursor spacing (mm).
        self._array_base: "QPointF | None" = None
        self._array_dir: "QPointF | None" = None
        self._array_spacing: float = 0.0
        self._array_row_spacing: float = 0.0     # 2D: signed row pitch (mm)
        self._array_total: "float | None" = None      # Polar: swept fill (deg)
        self._array_start_deg: "float | None" = None  # Polar: start-ray heading
        # Session-sticky per canvas tab (never cleared by clear()): the ←/→
        # variant and the last typed non-cursor HUD fields per variant.
        self._array_variant: str = "linear"
        # Typed Angle lock (Y-up CCW+ degrees) — None = the cursor aims;
        # dropped when Array ends or restarts (DS2.2).
        self._array_angle_locked: "float | None" = None
        self._array_memory: dict = {v: dict(f) for v, f
                                    in ARRAY_DEFAULT_MEMORY.items()}
        # Scale (P1 DD4; behaviour in ModifyToolsController): base point and
        # reference point (|ref - base| = 1x); both None outside the tool.
        self._scale_base: "QPointF | None" = None
        self._scale_ref: "QPointF | None" = None
        # DS1: which field the post-reference Scale HUD types — "length"
        # (default; reset on every set_mode by ModifyToolsController.clear) or
        # "factor" (←/→). Per run, never session-sticky.
        self._scale_variant: str = "length"
        # Flip / Mirror (P1 batch DD2-DD4; behaviour in ModifyToolsController):
        # the hovered axis_picker.AxisPick painted by Model_View, or None.
        self._mirror_axis = None
        # Flip (DS3): bbox centre of the reflectable selection (set at entry,
        # None outside Flip), the two toggles, and the last quadrant ("UL" ..).
        self._flip_center = None
        self._flip_lr = False
        self._flip_ud = False
        self._flip_quad = None

    # ── Host hooks with defaults (Model_Space overrides several) ─────────
    def _visible_view(self):
        """The first visible attached view, else None (Model_Space routes
        this through its PlacementInputCoordinator, same rule)."""
        return next((v for v in self.views() if v.isVisible()), None)

    def get_effective_position(self, scene_pos):
        """Snap hook: the point a press / move resolves to. Default: raw."""
        return QPointF(scene_pos)

    def is_input_mode(self) -> bool:
        """Typed-input hook: True while a Dynamic Input field has focus."""
        return False

    def publish_placement_state(self, anchor, point) -> None:
        """Typed-input hook: seed the HUD (no HUD -> no-op)."""

    def clear_placement_state(self) -> None:
        """Typed-input hook: drop the published seed (no HUD -> no-op)."""

    def get_resolved_point(self):
        """Typed-input hook: the HUD's resolved point (no HUD -> None)."""
        return None

    # ── Moved verbatim from model_space.py:902-913 ───────────────────────
    def _show_status(self, message: str, timeout: int = 5000):
        """Show a message on the main window's status bar.

        The first registered view is the hidden startup ``Model_View`` (its
        ``window()`` is itself, with no status bar), so the first view whose
        window has one wins.
        """
        for view in self.views():
            window = view.window()
            if window is not None and hasattr(window, 'statusBar'):
                window.statusBar().showMessage(message, timeout)
                return

    # ── Moved verbatim from model_space.py:5055-5076 ─────────────────────
    def _snap_view(self):
        """The view whose zoom (``transform().m11()``) drives snap/scale reads.

        Prefers the on-screen plan view (:meth:`_visible_view`); falls back to
        the LAST-attached view so headless tests (which attach a view without
        ``show()``) still resolve a real transform. ``views()[0]`` is
        deliberately *not* the fallback: in the running app that is the
        vestigial, never-shown ``MainWindow.view`` frozen at ``m11 == 1.0`` —
        reading it made every zoom-dependent tolerance (snap aperture,
        design-area pick, ALIGN band, …) collapse to a fixed *scene*
        distance regardless of zoom.
        """
        v = self._visible_view()
        if v is not None:
            return v
        views = self.views()
        return views[-1] if views else None

    def _active_view_scale(self) -> float:
        """Current on-screen zoom (px per scene-unit) from the active plan view."""
        v = self._snap_view()
        return v.transform().m11() if v is not None else 1.0

    # ── Moved verbatim from model_space.py:5586-5591 ─────────────────────
    def update_preview_node(self, pos: QPointF):
        self.preview_node.setPos(pos)
        if getattr(self, "_suppress_preview_node", False):
            self.preview_node.hide()
        else:
            self.preview_node.show()

    # ── Moved verbatim from model_space.py:5957-5974 (move rows) ─────────
    def _move_preview_node(self, event, snapped):
        self.update_preview_node(snapped)
        self.preview_pipe.hide()

    def _preview_from_move(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._preview_from_move(*args, **kwargs)

    def _move_paste_move(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._move_paste_move(*args, **kwargs)

    def _move_rotate(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md D8)
        return self._modify_ctl.move_rotate(*args, **kwargs)

    def _move_array(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md D10)
        return self._modify_ctl.move_array(*args, **kwargs)

    def _move_reflect(self, *args, **kwargs):  # shell → ModifyToolsController (P1 DD4)
        return self._modify_ctl.move_reflect(*args, **kwargs)

    # ── Moved verbatim from model_space.py:7296-7315 ─────────────────────
    def _press_copy_base(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md D4)
        return self._modify_ctl.press_copy_base(*args, **kwargs)

    def _press_paste_move(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._press_paste_move(*args, **kwargs)

    def begin_move_from(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl.begin_move_from(*args, **kwargs)

    def _begin_move_handle_snap(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._begin_move_handle_snap(*args, **kwargs)

    def _move_handle_snap(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._move_handle_snap(*args, **kwargs)

    def _apply_move_displacement(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._apply_move_displacement(*args, **kwargs)

    def _apply_paste_displacement(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md D5)
        return self._modify_ctl._apply_paste_displacement(*args, **kwargs)

    # ── Moved verbatim from model_space.py:7330-7357 ─────────────────────
    # ── Interactive Rotate (D8) ───────────────────────────────────────
    def _press_rotate(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md D8)
        return self._modify_ctl.press_rotate(*args, **kwargs)

    def _apply_rotate_by(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md D8)
        return self._modify_ctl.apply_rotate_by(*args, **kwargs)

    # ── Array (D10 + P1 DD5) ──────────────────────────────────────────
    def _press_array(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md D10)
        return self._modify_ctl.press_array(*args, **kwargs)

    def _apply_array_dynamic_input(self, *args, **kwargs):  # shell → ModifyToolsController (P1 DD5 router)
        return self._modify_ctl.apply_array(*args, **kwargs)

    # ── Scale (P1 DD4) ────────────────────────────────────────────────
    def _press_scale(self, *args, **kwargs):  # shell → ModifyToolsController (P1 DD4)
        return self._modify_ctl.press_scale(*args, **kwargs)

    def _move_scale(self, *args, **kwargs):  # shell → ModifyToolsController (P1 DD4)
        return self._modify_ctl.move_scale(*args, **kwargs)

    def _apply_scale_factor(self, *args, **kwargs):  # shell → ModifyToolsController (P1 DD4)
        return self._modify_ctl.apply_scale_factor(*args, **kwargs)

    # ── Flip / Mirror (P1 DD4) ────────────────────────────────────────
    def _press_reflect(self, *args, **kwargs):  # shell → ModifyToolsController (P1 DD4)
        return self._modify_ctl.press_reflect(*args, **kwargs)

    # ── Moved verbatim from model_space.py:9835-9918 ─────────────────────
    def _shape_paths_for_move(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._shape_paths_for_move(*args, **kwargs)

    def _clipboard_ghost_paths(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._clipboard_ghost_paths(*args, **kwargs)

    def _build_move_ghost_base(self, *args, **kwargs):  # shell → ModifyToolsController (scene-tools.md I1)
        return self._modify_ctl._build_move_ghost_base(*args, **kwargs)

    def move_items(self, offset):
        """Translate the selection by *offset* (the Move tool commit).

        Returns:
            False when D17 refused it (a fully defined item -- nothing moved,
            the caller pushes no undo step); None with an empty selection;
            True otherwise.
        """
        # The one change from model_space.py:9844-9884: these three were
        # model_space module imports.
        from .floor_opening import drop_carried_voids
        from .node import Node
        from .sprinkler import Sprinkler
        if not self._selected_items:
            return
        # Resolve any Sprinkler items to their parent Node
        resolved = []
        seen = set()
        for item in self._selected_items:
            if isinstance(item, Sprinkler) and item.node is not None:
                item = item.node
            if getattr(item, "MANIP_ANCHORED", False):
                continue                   # anchored overlay (tile frame)
            if id(item) not in seen:
                seen.add(id(item))
                resolved.append(item)
        resolved = drop_carried_voids(resolved)   # a slab carries its voids (floor-opening A2)
        if self.constraint_ctl.refuse_grounded(resolved):     # D17 (CS3)
            self._selected_items = None
            return False
        # §8: the moved set's handles become drag goals; the controller
        # re-solves on exit (before the caller's undo push).
        with self.constraint_ctl.edit(resolved):
            for item in resolved:
                if isinstance(item, Node):
                    item.moveBy(offset.x(), offset.y())
                    item.setSelected(True)
                    item.fitting.update()
                elif hasattr(item, "translate"):
                    item.translate(offset.x(), offset.y())
                    item.setSelected(True)
                elif hasattr(item, "manip_translate"):   # Text (D7)
                    item.manip_translate(offset.x(), offset.y())
                    item.setSelected(True)
        self._selected_items = None   # clear after use
        return True

    def clipboard_payload(self):
        """The versioned FirePro3D clipboard payload (scene-tools.md I1).

        Returns:
            ``{"fp3d_clipboard", "base", "scene_role", "items",
            "constraints"}`` (``constraints`` = the copied set's internal
            constraint records; absent on an older payload), or None when
            the clipboard is empty, not JSON, or lacks the current
            ``CLIPBOARD_FORMAT_VERSION`` key (foreign).
        """
        from .constants import CLIPBOARD_FORMAT_VERSION
        text = QApplication.clipboard().text()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if (not isinstance(payload, dict)
                or payload.get("fp3d_clipboard") != CLIPBOARD_FORMAT_VERSION
                or not isinstance(payload.get("items"), list)):
            return None
        return payload

    def clipboard_data(self):
        """The clipboard payload's item records, or None.

        Only the versioned payload is ever read from the OS clipboard (I1);
        internal copy paths pass records to ``paste_items(data=...)``.
        """
        payload = self.clipboard_payload()
        return payload["items"] if payload is not None else None
