"""Tree model over ``Model_Space.underlays`` for the Underlay Manager.

The model is a :class:`QAbstractItemModel` **tree** bound live to the app's
``scene.underlays`` list (the single source of truth — a list of
``(Underlay, QGraphicsItem)`` pairs).  Top-level rows are underlays; child
rows are that underlay's source layers (empty for a raster PDF).  Every edit
mutates the shared ``Underlay`` record and then calls the existing scene
methods (``repen_underlay`` / ``level_mgr.apply_to_scene`` /
``set_underlay_layer_hidden``) — never a private copy.

This module also owns the shared :class:`Col` enum and the item-data roles
that the delegates and the dialog import.
"""
from __future__ import annotations

import os
from enum import IntEnum

from PyQt6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PyQt6.QtWidgets import QGraphicsPixmapItem


# ---------------------------------------------------------------------------
# Shared column enum + roles (imported by the delegates and the dialog)
# ---------------------------------------------------------------------------
class Col(IntEnum):
    NAME = 0
    SOURCE = 1
    TYPE = 2
    VIS = 3
    SNAP = 4
    COLOUR = 5
    WEIGHT = 6
    LEVELS = 7


TITLES = ["NAME", "SOURCE", "TYPE", "VISIBILITY", "SNAP", "COLOUR", "WEIGHT", "LEVELS"]

UnderlayRole = Qt.ItemDataRole.UserRole + 1   # -> Underlay record (both row kinds)
SearchRole = Qt.ItemDataRole.UserRole + 2     # -> combined lowercase text for filtering
SortRole = Qt.ItemDataRole.UserRole + 3       # -> per-column sort key
LayerRole = Qt.ItemDataRole.UserRole + 4      # -> layer name (child row) / None (underlay row)
AppearanceEditableRole = Qt.ItemDataRole.UserRole + 5  # -> bool: colour/weight/snap editable (False for raster PDF)
LayerListRole = Qt.ItemDataRole.UserRole + 6  # -> list[str]: all source-layer names of the underlay (both row kinds)


# ---------------------------------------------------------------------------
# Node identity — stable internalPointer per (record, layer)
# ---------------------------------------------------------------------------
class _Node:
    """Cached identity object handed to ``createIndex`` as internalPointer.

    ``layer is None`` -> underlay (top-level) row; ``layer`` a str -> that
    underlay's layer-child row.
    """

    __slots__ = ("record", "layer")

    def __init__(self, record, layer=None):
        self.record = record
        self.layer = layer


# ---------------------------------------------------------------------------
# Record-access helpers (tolerant of both the real Underlay and test stand-ins)
# ---------------------------------------------------------------------------
def _record_type_label(record) -> str:
    fn = getattr(record, "type_label", None)
    if callable(fn):
        try:
            return fn()
        except Exception:
            pass
    return str(getattr(record, "type", "") or "").upper()


def _record_name(record) -> str:
    """Display name for an underlay: user-authored name, else file basename.

    Falls back to ``"(untitled)"`` when both the name and path are blank so a
    row is never empty.
    """
    name = (getattr(record, "name", "") or "").strip()
    if name:
        return name
    return os.path.basename(getattr(record, "path", "") or "") or "(untitled)"


def _record_source(record) -> str:
    src = getattr(record, "source", None)
    if src:
        return str(src)
    return str(getattr(record, "path", "") or "")


def _record_missing(record) -> bool:
    if getattr(record, "missing", False):
        return True
    path = getattr(record, "path", None)
    if path:
        try:
            return not os.path.exists(path)
        except Exception:
            return False
    return False


def _record_levels_text(record) -> str:
    levels = getattr(record, "levels", None) or []
    if levels == ["*"]:
        return "All Levels"
    return ", ".join(str(x) for x in levels)


# ---------------------------------------------------------------------------
# The tree model
# ---------------------------------------------------------------------------
class UnderlayTreeModel(QAbstractItemModel):
    """Live tree over ``scene.underlays``.

    Args:
        scene: the ``Model_Space`` (or a QObject fake exposing ``underlays``,
            ``underlaysChanged``, ``repen_underlay``, ``level_mgr``,
            ``active_level``).
        theme: an Underlay-Manager :class:`Theme` (for optional ForegroundRole).
        known_levels: callable ``() -> list[str]`` of level names.
    """

    def __init__(self, scene, theme, known_levels, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._theme = theme
        self._known_levels = known_levels
        self._node_cache: dict = {}
        sig = getattr(scene, "underlaysChanged", None)
        if sig is not None:
            sig.connect(self._on_underlays_changed)

    # -- data access -------------------------------------------------------
    def _underlays(self):
        return getattr(self._scene, "underlays", [])

    def _group_for(self, record):
        """Return the QGraphicsItem paired with *record* (or None)."""
        for data, group in self._underlays():
            if data is record:
                return group
        return None

    def _layers_of(self, record) -> list[str]:
        """Return the sorted layer-name list from the paired scene group.

        Reads ``group.data(2)`` (the canonical layer list cached on the item)
        with a ``child.data(1)`` fallback for groups built before the cache
        was populated.  Returns ``[]`` for raster-PDF groups (no layers) and
        when no paired group exists.
        """
        group = self._group_for(record)
        if group is None:
            return []
        layers = group.data(2)
        if not layers:
            layers = sorted(
                {c.data(1) for c in group.childItems() if c.data(1) is not None}
            )
        return list(layers)

    def _node(self, record, layer=None) -> _Node:
        key = (id(record), layer)
        node = self._node_cache.get(key)
        if node is None:
            node = _Node(record, layer)
            self._node_cache[key] = node
        return node

    def _underlay_row(self, record) -> int:
        for i, (data, _group) in enumerate(self._underlays()):
            if data is record:
                return i
        return -1

    # -- reset on external change -----------------------------------------
    def _on_underlays_changed(self):
        self.beginResetModel()
        self._node_cache.clear()
        self.endResetModel()

    # -- tree structure ----------------------------------------------------
    def index(self, row, column, parent=QModelIndex()):
        if row < 0 or column < 0 or column >= len(Col):
            return QModelIndex()
        if not parent.isValid():
            rows = self._underlays()
            if row >= len(rows):
                return QModelIndex()
            record = rows[row][0]
            return self.createIndex(row, column, self._node(record))
        parent_node = parent.internalPointer()
        if parent_node is None or parent_node.layer is not None:
            return QModelIndex()  # layer rows have no children
        layers = self._layers_of(parent_node.record)
        if row >= len(layers):
            return QModelIndex()
        return self.createIndex(
            row, column, self._node(parent_node.record, layers[row]))

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if node is None or node.layer is None:
            return QModelIndex()
        urow = self._underlay_row(node.record)
        if urow < 0:
            return QModelIndex()
        return self.createIndex(urow, 0, self._node(node.record))

    def rowCount(self, parent=QModelIndex()):
        if not parent.isValid():
            return len(self._underlays())
        node = parent.internalPointer()
        if node is None or node.layer is not None:
            return 0
        return len(self._layers_of(node.record))

    def columnCount(self, parent=QModelIndex()):
        return len(Col)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole and 0 <= section < len(TITLES):
                return TITLES[section]
            if (role == Qt.ItemDataRole.TextAlignmentRole
                    and section in (Col.VIS, Col.SNAP, Col.TYPE)):
                return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    # -- data --------------------------------------------------------------
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if node is None:
            return None
        record = node.record
        col = index.column()

        if role == Qt.ItemDataRole.TextAlignmentRole:
            # Centre the TYPE cell text (VIS/SNAP are delegate-painted/centred;
            # other text columns keep default left alignment).
            if col == Col.TYPE:
                return int(Qt.AlignmentFlag.AlignCenter)
            return None
        if role == UnderlayRole:
            return record
        if role == LayerRole:
            return node.layer
        if role == AppearanceEditableRole:
            # Layer child rows are always editable (vector by definition).
            # An underlay node is editable unless its paired group is a raster
            # PDF pixmap (no vector pens to recolour / reweight / snap).
            if node.layer is not None:
                return True
            return not isinstance(self._group_for(record), QGraphicsPixmapItem)
        if role == LayerListRole:
            # All source-layer names for this underlay (same on both row kinds).
            # Lets the VIS delegate tell "some layers hidden" (partial) from
            # "all layers hidden" on the parent eye glyph.
            return self._layers_of(record)

        if node.layer is not None:
            return self._layer_data(node, col, role)
        return self._underlay_data(node, col, role)

    def _underlay_data(self, node, col, role):
        record = node.record

        if role == SearchRole:
            name = _record_name(record)
            src = _record_source(record)
            typ = _record_type_label(record)
            levels = _record_levels_text(record)
            return " ".join([name, src, typ, levels]).lower()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == Col.NAME:
                name = _record_name(record)
                if _record_missing(record):
                    name += " ⚠"
                return name
            if col == Col.SOURCE:
                return _record_source(record)
            if col == Col.TYPE:
                return _record_type_label(record)
            # VIS/SNAP/COLOUR/WEIGHT/LEVELS painted by delegates
            return None

        if role == SortRole:
            if col == Col.NAME:
                return _record_name(record).lower()
            if col == Col.SOURCE:
                return _record_source(record).lower()
            if col == Col.LEVELS:
                return _record_levels_text(record).lower()
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            if not getattr(record, "visible", True) and self._theme is not None:
                try:
                    return self._theme.color("faint")
                except Exception:
                    return None
            return None

        return None

    def _layer_data(self, node, col, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if col == Col.NAME:
                return node.layer
            return None
        if role == SortRole:
            if col == Col.NAME:
                return str(node.layer).lower()
            return None
        return None

    # -- edits -------------------------------------------------------------
    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        node = index.internalPointer()
        if node is None:
            return False
        if node.layer is not None:
            ok = self._set_layer_data(node, index.column(), value)
        else:
            ok = self._set_underlay_data(node, index.column(), value)
        if ok:
            row = index.row()
            parent = index.parent()
            left = self.index(row, 0, parent)
            right = self.index(row, len(Col) - 1, parent)
            self.dataChanged.emit(left, right)
        return ok

    def _set_underlay_data(self, node, col, value) -> bool:
        record = node.record
        if col == Col.VIS:
            # VIS setData value is 'visible' for both underlay and layer rows.
            record.visible = bool(value)
            self._apply_visibility()
            return True
        if col == Col.SNAP:
            record.snap = bool(value)
            return True
        if col == Col.COLOUR:
            record.colour = value
            self._repen(record)
            return True
        if col == Col.WEIGHT:
            record.line_weight_name = value
            self._repen(record)
            return True
        if col == Col.LEVELS:
            record.levels = list(value)
            self._apply_visibility()
            return True
        return False

    def _set_layer_data(self, node, col, value) -> bool:
        record = node.record
        layer = node.layer
        if col == Col.VIS:
            # VIS setData value is 'visible' for both underlay and layer rows.
            hidden = not bool(value)
            group = self._group_for(record)
            done = False
            fn = getattr(self._scene, "set_underlay_layer_hidden", None)
            if callable(fn):
                try:
                    fn(record, group, layer, hidden)
                    done = True
                except (AttributeError, TypeError):
                    done = False
            if not done:
                # Fallback: mutate the record + repen directly.
                if hidden and layer not in record.hidden_layers:
                    record.hidden_layers.append(layer)
                elif not hidden and layer in record.hidden_layers:
                    record.hidden_layers.remove(layer)
                self._repen(record)
            return True
        if col == Col.COLOUR:
            record.layer_overrides.setdefault(layer, {})["colour"] = value
            self._repen(record)
            return True
        if col == Col.WEIGHT:
            record.layer_overrides.setdefault(layer, {})["line_weight"] = value
            self._repen(record)
            return True
        return False

    # -- scene bridges (tolerant of minimal fake scenes) -------------------
    def _repen(self, record):
        fn = getattr(self._scene, "repen_underlay", None)
        if callable(fn):
            try:
                fn(record)
            except AttributeError:
                pass

    def _apply_visibility(self):
        # The real Model_Space exposes the level manager as ``_level_manager``
        # (main.py sets ``scene._level_manager``); test fakes use ``level_mgr``.
        # Honour both — otherwise the master (underlay-level) VIS toggle is a
        # silent no-op on the live canvas, because ``apply_to_scene`` is the
        # only path that gates the whole group on ``record.visible``.
        lm = (getattr(self._scene, "level_mgr", None)
              or getattr(self._scene, "_level_manager", None))
        if lm is None:
            return
        active = getattr(self._scene, "active_level", None)
        try:
            lm.apply_to_scene(self._scene, active)
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# Filter / sort proxy
# ---------------------------------------------------------------------------
class UnderlayFilterProxy(QSortFilterProxyModel):
    """Sort by :data:`SortRole`; filter only top-level rows by search text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ""
        self.setSortRole(SortRole)
        self.setDynamicSortFilter(False)
        self.setRecursiveFilteringEnabled(True)

    def set_filter_text(self, text: str):
        self._needle = (text or "").strip().lower()
        self.invalidateRowsFilter()

    def filterAcceptsRow(self, row, parent):
        if not self._needle:
            return True
        # Only filter top-level (underlay) rows; child rows ride along.
        if parent.isValid():
            return True
        src = self.sourceModel()
        idx = src.index(row, 0, parent)
        hay = src.data(idx, SearchRole) or ""
        return self._needle in hay
