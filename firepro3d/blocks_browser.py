"""BlocksBrowser — left-dock tree of the block library + the project's blocks.

Library > Series > block. The tree is the on-disk block library (every
Library/Series folder, even empty, and every indexed ``.fpdb``) merged with
the project's embedded definitions: a block already in the project shows in
regular weight, a library-only block in italic/dimmed. Activating a project
block emits ``blockActivated(id)`` (the app routes it into place_block mode);
activating a library-only block first loads it into the project (one undoable
batch via ``Model_Space.load_blocks_from_files``) and then emits the same.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import QByteArray, QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (QAbstractItemView, QWidget, QVBoxLayout, QTreeWidget,
                             QTreeWidgetItem, QFrame, QMenu)

from . import block_library
from .mime_types import MIME_BLOCK

_ROLE_ID = Qt.ItemDataRole.UserRole          # block id (project or library)
_ROLE_PATH = Qt.ItemDataRole.UserRole + 1    # .fpdb path for library-only leaves


_BADGE_PX = 14                               # capability badge size (logical px)
_BADGE_CACHE: dict = {}                      # (kind, muted colour, dpr) -> QIcon

# Capability leaf tooltips (hatch D-A34, linetypes LT4-10).
_PAT_LEAF_TIP = "Pattern block — used by hatch fills; it can't be placed"
_LT_LEAF_TIP = ("Linetype — apply it from a line's Linetype row; "
                "it can't be placed")
_END_LEAF_TIP = ("End type — apply it from a line's Start End / Finish End "
                 "rows; it can't be placed")


def _pattern_badge(dpr: float = 1.0):
    """Small hatch glyph for tiled (pattern) blocks (D-A34).

    Cached per (kind, theme muted colour, device pixel ratio) — the tree rebuilds
    on every library change, so a fresh swatch per leaf would repeat work.

    Args:
        dpr: The browser widget's ``devicePixelRatioF()`` (crisp on HiDPI).

    Returns:
        The badge ``QIcon``.
    """
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QIcon, QPainter, QPixmap
    from .hatch_render import paint_swatch
    from . import theme as th
    muted = th.detect().muted
    key = ("pattern", muted, float(dpr))
    icon = _BADGE_CACHE.get(key)
    if icon is not None:
        return icon
    side = max(1, round(_BADGE_PX * dpr))
    pix = QPixmap(side, side)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    paint_swatch(p, QRectF(0, 0, side, side), "diagonal", QColor(muted))
    p.end()
    pix.setDevicePixelRatio(dpr)
    icon = QIcon(pix)
    _BADGE_CACHE[key] = icon
    return icon


def _linetype_badge(dpr: float = 1.0):
    """Small dash-dot glyph for linetype (repeat) blocks (linetypes LT4-10).

    Shares :data:`_BADGE_CACHE` with :func:`_pattern_badge` (keyed by kind).

    Args:
        dpr: The browser widget's ``devicePixelRatioF()`` (crisp on HiDPI).

    Returns:
        The badge ``QIcon``.
    """
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QIcon, QPainter, QPen, QPixmap
    from . import theme as th
    muted = th.detect().muted
    key = ("linetype", muted, float(dpr))
    icon = _BADGE_CACHE.get(key)
    if icon is not None:
        return icon
    side = max(1, round(_BADGE_PX * dpr))
    pix = QPixmap(side, side)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(muted), max(1.0, 1.5 * dpr))
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    y = side / 2.0
    p.drawLine(QPointF(0.5, y), QPointF(side * 0.45, y))
    p.drawLine(QPointF(side * 0.6, y), QPointF(side * 0.72, y))
    p.setBrush(QColor(muted))
    p.setPen(Qt.PenStyle.NoPen)
    r = max(1.0, 1.1 * dpr)
    p.drawEllipse(QPointF(side * 0.88, y), r, r)
    p.end()
    pix.setDevicePixelRatio(dpr)
    icon = QIcon(pix)
    _BADGE_CACHE[key] = icon
    return icon


def _end_badge(dpr: float = 1.0):
    """Small line + filled arrowhead glyph for end-type blocks (LT5 Q12).

    Shares :data:`_BADGE_CACHE` with the other badges (keyed by kind).

    Args:
        dpr: The browser widget's ``devicePixelRatioF()`` (crisp on HiDPI).

    Returns:
        The badge ``QIcon``.
    """
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QIcon, QPainter, QPen, QPixmap, QPolygonF
    from . import theme as th
    muted = th.detect().muted
    key = ("end", muted, float(dpr))
    icon = _BADGE_CACHE.get(key)
    if icon is not None:
        return icon
    side = max(1, round(_BADGE_PX * dpr))
    pix = QPixmap(side, side)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(muted), max(1.0, 1.5 * dpr))
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    y = side / 2.0
    p.drawLine(QPointF(0.5, y), QPointF(side * 0.55, y))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(muted))
    p.drawPolygon(QPolygonF([QPointF(side * 0.95, y),
                             QPointF(side * 0.5, y - side * 0.3),
                             QPointF(side * 0.5, y + side * 0.3)]))
    p.end()
    pix.setDevicePixelRatio(dpr)
    icon = QIcon(pix)
    _BADGE_CACHE[key] = icon
    return icon


_BADGES = {"pattern": (_pattern_badge, _PAT_LEAF_TIP),
           "linetype": (_linetype_badge, _LT_LEAF_TIP),
           "end": (_end_badge, _END_LEAF_TIP)}


def _capability_badge(kind, dpr: float):
    """``(icon, tooltip)`` for a capability leaf (``capabilities.CAP_INFO``
    kind: tile / repeat / end), else None."""
    from .capabilities import CAP_INFO
    cap = CAP_INFO.get(kind)
    if cap is None:
        return None
    make, tip = _BADGES[cap.badge_name]
    return make(dpr), tip


def library_only_entries(scene, root: str | None = None, *,
                         entries: list[dict] | None = None
                         ) -> list[tuple[str, str, str, str, str]]:
    """Library blocks NOT already in the project.

    The "Library" half of the Blocks browser tree and of the Block Editor's
    Open picker (one implementation, two callers).

    Args:
        scene: The project ``Model_Space`` (its ``_block_definitions`` registry).
        root: Block-library root override (None = the configured library).
        entries: An already-read ``block_library.list_library(root)`` result
            (one index read per Blocks-browser refresh); None reads it here.

    Returns:
        ``(library, series, name, block_id, path)`` tuples — on-disk index
        entries whose id is not a project definition.
    """
    seen = set(scene._block_definitions)
    out = []
    if entries is None:
        entries = block_library.list_library(root)
    for e in entries:
        if e.get("id") in seen:
            continue
        if e.get("kind") == "schematic":
            continue      # never a block-library citizen (schematics.md D-S4/D-S5)
        out.append((e["library"], e["series"], e.get("name") or e["filename"],
                    e.get("id", ""), block_library.entry_path(e, root)))
    return out


def ensure_block_loaded(scene, block_id: str, path: str | None, name: str,
                        root: str | None = None, parent=None) -> bool:
    """Make *block_id* a project definition, loading it from *path* if needed.

    A library-only block is loaded as one undoable batch via
    ``Model_Space.load_blocks_from_files``; on a failed load the shared
    load-failure message is shown (parented to *parent*).

    Args:
        scene: The project ``Model_Space``.
        block_id: The block's id.
        path: The library ``.fpdb`` path (None/empty for a project block).
        name: The block's display name (for the failure message).
        root: Block-library root override (None = the configured library).
        parent: Parent widget for the failure message.

    Returns:
        True when the id resolves in the project afterwards.
    """
    if block_id in scene._block_definitions:
        return True
    if not path:
        return False
    summary = scene.load_blocks_from_files([path], root=root)
    if block_id in scene._block_definitions:
        return True
    from .themed_message import themed_info
    themed_info(parent, "Load block",
                block_library.load_failure_message(name, summary))
    return False


class _BlocksTree(QTreeWidget):
    """Tree whose block leaves drag out as ``MIME_BLOCK`` (folders don't).

    The payload is ``{"id": block_id, "path": .fpdb path | None}`` — a
    library-only leaf carries its file so the drop target can load it.
    """

    def mimeData(self, items):  # noqa: N802 (Qt API)
        mime = QMimeData()
        for item in items:
            block_id = item.data(0, _ROLE_ID)
            if isinstance(block_id, str) and block_id:
                payload = {"id": block_id, "path": item.data(0, _ROLE_PATH)}
                mime.setData(MIME_BLOCK,
                             QByteArray(json.dumps(payload).encode("utf-8")))
                break
        return mime

    def mimeTypes(self):  # noqa: N802 (Qt API)
        return [MIME_BLOCK]


class BlocksBrowser(QWidget):
    """Tree browser of the block library + project blocks (Library > Series > block).

    Same tree chrome as the sibling browsers (feature/model/project): 16px
    indentation with decorated root chevrons, no frame, 4px margins, and bold
    grouping (folder) rows over regular-weight leaves.

    Args:
        scene: The project ``Model_Space`` (block registry + loader).
        parent: Optional Qt parent.
        root: Block-library root override (None = the configured library).
    """

    blockActivated = pyqtSignal(str)
    editRequested = pyqtSignal(str)       # block id (project definition)

    def __init__(self, scene, parent: QWidget | None = None, *,
                 root: str | None = None) -> None:
        super().__init__(parent)
        self._scene = scene
        self._lib_root = root
        # Optional ``(block_id, path | None) -> refusal reason | None`` consulted
        # before a leaf is loaded/activated; the owner surfaces the reason.
        self.activation_guard = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self._tree = _BlocksTree()
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._tree.setHeaderHidden(True)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        from firepro3d.ui_kit import browser_tree_qss
        self._tree.setStyleSheet(browser_tree_qss())
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)
        layout.addWidget(self._tree)
        if hasattr(scene, "blockDefinitionsChanged"):
            scene.blockDefinitionsChanged.connect(self.refresh)
        block_library.add_change_listener(self.refresh)
        self.refresh()

    def showEvent(self, event):  # noqa: N802 (Qt API)
        # Re-read on show: the library root is a preference that can change
        # (System Settings) and other processes may write the folder.
        super().showEvent(event)
        self.refresh()

    # ── data ──────────────────────────────────────────────────────────────

    def _grouped(self, entries: list[dict] | None = None) -> dict:
        """``{library: {series: [(name, id, path|None), ...]}}`` — the on-disk
        folders + indexed blocks merged with the project's definitions (a
        library entry whose id is in the project is listed once, as project).
        *entries* is the refresh's one ``list_library`` read (None reads it)."""
        registry = self._scene._block_definitions
        tree: dict = {}
        for lib, series in block_library.list_folders(self._lib_root).items():
            node = tree.setdefault(lib, {})
            for ser in series:
                node.setdefault(ser, [])
        for b in registry.values():
            if b.kind == "schematic":
                continue          # Project Browser only (schematics.md D-S4)
            tree.setdefault(b.library, {}).setdefault(b.series, []).append(
                (b.name, b.id, None))
        for lib, ser, name, block_id, path in library_only_entries(
                self._scene, self._lib_root, entries=entries):
            tree.setdefault(lib, {}).setdefault(ser, []).append(
                (name, block_id, path))
        return tree

    def _collapsed_paths(self) -> set:
        """``(library,)`` / ``(library, series)`` keys the user has collapsed."""
        out = set()
        for i in range(self._tree.topLevelItemCount()):
            lib = self._tree.topLevelItem(i)
            if not lib.isExpanded():
                out.add((lib.text(0),))
            for j in range(lib.childCount()):
                ser = lib.child(j)
                if not ser.isExpanded():
                    out.add((lib.text(0), ser.text(0)))
        return out

    def refresh(self) -> None:
        """Rebuild the tree, keeping the user's collapsed folders collapsed
        (new folders open by default)."""
        collapsed = self._collapsed_paths()
        self._tree.clear()
        f_bold = QFont()
        f_bold.setBold(True)
        f_lib = QFont()
        f_lib.setItalic(True)
        from . import theme as th
        dim = QBrush(QColor(th.detect().muted))
        entries = block_library.list_library(self._lib_root)   # read once
        grouped = self._grouped(entries)
        # Library rows read the index ``tile`` / ``repeat`` / ``end`` flags
        # (LT4-10, LT5 Q12).
        from .capabilities import kind_of
        lib_caps = {e.get("id"): kind_of(e) for e in entries}
        dpr = self.devicePixelRatioF()
        for library in sorted(grouped):
            lib_item = QTreeWidgetItem(self._tree, [library])
            lib_item.setFont(0, f_bold)
            for series in sorted(grouped[library]):
                s_item = QTreeWidgetItem(lib_item, [series])
                s_item.setFont(0, f_bold)
                for name, block_id, path in sorted(grouped[library][series],
                                                   key=lambda x: x[0].lower()):
                    leaf = QTreeWidgetItem(s_item, [name])
                    leaf.setData(0, _ROLE_ID, block_id)
                    if path is None:
                        d = self._scene.get_block_definition(block_id)
                        kind = kind_of(d)
                        tip = ("Drag onto a canvas or double-click "
                               "to place")
                    else:
                        leaf.setData(0, _ROLE_PATH, path)
                        leaf.setFont(0, f_lib)
                        leaf.setForeground(0, dim)
                        kind = lib_caps.get(block_id)
                        tip = ("In the library — drag or double-click "
                               "to load into the project and place")
                    badge = _capability_badge(kind, dpr)
                    if badge is not None:
                        icon, tip = badge
                        leaf.setIcon(0, icon)
                    leaf.setToolTip(0, tip)
                s_item.setExpanded((library, series) not in collapsed)
            lib_item.setExpanded((library,) not in collapsed)

    # ── activation ────────────────────────────────────────────────────────

    def _on_item_activated(self, item: QTreeWidgetItem, col: int) -> None:
        """Place a block leaf; a library-only leaf is loaded first."""
        block_id = item.data(0, _ROLE_ID)
        if not isinstance(block_id, str) or not block_id:
            return                                   # folder row
        path = item.data(0, _ROLE_PATH)
        # Refusal (e.g. a block that would contain the edited one) is checked
        # BEFORE any load, exactly like a canvas drag (nested-blocks D7).
        guard = self.activation_guard
        if guard is not None and guard(block_id, path) is not None:
            return
        if path and not ensure_block_loaded(self._scene, block_id, path,
                                            item.text(0), self._lib_root, self):
            return
        self.blockActivated.emit(block_id)

    # ── context menu ──────────────────────────────────────────────────────

    def _build_context_menu(self, item: QTreeWidgetItem | None) -> QMenu | None:
        """Right-click menu for a block leaf (``Edit Block``); None for folders.

        Args:
            item: The tree item under the cursor (None = empty space).

        Returns:
            The ``QMenu``, or None when *item* is not a block leaf.
        """
        if item is None:
            return None
        block_id = item.data(0, _ROLE_ID)
        if not isinstance(block_id, str) or not block_id:
            return None                              # folder row
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        act = menu.addAction("Edit Block")
        tip = "Open this block in a Block Editor tab"
        act.setToolTip(tip)
        act.setStatusTip(tip)
        act.triggered.connect(lambda _=False, it=item: self._edit_item(it))
        return menu

    def _on_context_menu(self, pos) -> None:
        menu = self._build_context_menu(self._tree.itemAt(pos))
        if menu is not None:
            menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _edit_item(self, item: QTreeWidgetItem) -> None:
        """Make the leaf a project definition (loading a library-only one),
        then emit ``editRequested``. No placement guard: editing never places."""
        block_id = item.data(0, _ROLE_ID)
        path = item.data(0, _ROLE_PATH)
        if not ensure_block_loaded(self._scene, block_id, path, item.text(0),
                                   self._lib_root, self):
            return
        self.editRequested.emit(block_id)
