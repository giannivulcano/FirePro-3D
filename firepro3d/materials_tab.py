"""Materials tab of the Display Manager (materials.md M16).

Default for Wall / Floor pickers above a list + editor, the Fill Types tab's
layout. Edits land on a **working copy**: the Display Manager installs it on
OK and drops it on Cancel. Built from ``ui_kit`` widgets and theme tokens only
(docs/specs/ui-design-system.md).
"""
from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from . import fill_types, materials
from .constants import MATERIAL_NONE_ID
from .fill_layers import FillLayers
from .fill_types_tab import look_pixmap
from .theme import M
from .ui_kit import PaintSwatch, Section, Selector

NO_HATCH_LABEL = "No hatch"
_NEW_NAME = "New Material"
_LIST_ICON = QSize(32, 16)
_NONE_TIP = "None is permanent: it cannot be renamed or deleted."


class MaterialsTab(QWidget):
    """Editor over a working copy of the project Materials table.

    Args:
        scene: The project ``Model_Space`` (pattern registry, "Used by").
        parent: Dialog parent.
        fill_table: Callable returning the Fill Type table to list (the Fill
            Types tab's working copy); None lists the project table.

    Signals:
        edited: The working copy changed.
    """

    edited = pyqtSignal()

    def __init__(self, scene, parent=None, fill_table=None):
        super().__init__(parent)
        self._scene = scene
        self._work = materials.project_table().copy()
        self._fill_table = fill_table or fill_types.project_table
        self.dirty = False
        self._sel: str | None = None
        self._loading = False
        self._users: dict[str, list[str]] = {}
        self._build()
        self.refresh_fill_types()
        self._rebuild_list()

    # -- build ---------------------------------------------------------------
    def _registry(self):
        return getattr(self._scene, "block_registry", None)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(M.MD, M.MD, M.MD, M.MD)
        root.setSpacing(M.LG)

        defaults_box = QWidget()
        db = QVBoxLayout(defaults_box)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(M.SM)
        self._default_sel: dict[str, Selector] = {}
        for cat in materials.CATEGORIES:
            sel = Selector()
            sel.setToolTip(f"The material a new {cat.lower()} starts with")
            sel.currentIndexChanged.connect(lambda _i, c=cat: self._on_default(c))
            self._default_sel[cat] = sel
            db.addLayout(self._row(f"{cat}", sel))
        root.addWidget(Section("Default for new elements", defaults_box))

        body = QHBoxLayout()
        body.setSpacing(M.LG)
        left = QVBoxLayout()
        left.setSpacing(M.SM)
        self._list = QListWidget()
        self._list.setIconSize(_LIST_ICON)
        self._list.setMinimumWidth(190)
        self._list.setToolTip("The project's Materials")
        self._list.currentRowChanged.connect(self._on_row)
        left.addWidget(self._list, 1)
        btns = QHBoxLayout()
        btns.setSpacing(M.SM)
        self._add_btn = QPushButton("Add")
        self._add_btn.setToolTip("Add a new Material")
        self._add_btn.clicked.connect(lambda: self.add_material())
        self._dup_btn = QPushButton("Duplicate")
        self._dup_btn.setToolTip("Duplicate the selected Material")
        self._dup_btn.clicked.connect(lambda: self.duplicate_material())
        self._del_btn = QPushButton("Delete")
        self._del_btn.clicked.connect(self._on_delete)
        for b in (self._add_btn, self._dup_btn, self._del_btn):
            btns.addWidget(b)
        left.addLayout(btns)
        body.addLayout(left, 0)

        self._editor = QWidget()
        ed = QVBoxLayout(self._editor)
        ed.setContentsMargins(0, 0, 0, 0)
        ed.setSpacing(M.MD)
        name_box = QWidget()
        nb = QVBoxLayout(name_box)
        nb.setContentsMargins(0, 0, 0, 0)
        nb.setSpacing(M.XS)
        self._name = QLineEdit()
        self._name.setFixedHeight(M.PROP_FIELD_H)
        self._name.setToolTip("The Material's name (unique in the project)")
        self._name.editingFinished.connect(lambda: self.set_name(self._name.text()))
        self._status = QLabel("")
        self._status.setProperty("role", "muted")
        nb.addWidget(self._name)
        nb.addWidget(self._status)
        ed.addWidget(Section("Name", name_box))
        self._section = Selector()
        self._section.setShowIcon(True)
        self._section.setIconSize(QSize(40, 20))
        self._section.setToolTip("The Fill Type drawn where this material is cut")
        self._section.currentIndexChanged.connect(self._on_section)
        ed.addWidget(Section("Section", self._section))
        self._preview = PaintSwatch(self._paint_preview, height=72)
        self._preview.setToolTip("Live preview of the look")
        ed.addWidget(Section("Preview", self._preview))
        self._used = QLabel("")
        self._used.setProperty("role", "muted")
        self._used.setWordWrap(True)
        ed.addWidget(self._used)
        ed.addStretch(1)
        body.addWidget(self._editor, 1)
        root.addLayout(body, 1)

    @staticmethod
    def _row(label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(M.SM)
        lbl = QLabel(label)
        lbl.setProperty("role", "muted")
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    # -- public API ------------------------------------------------------------
    def table(self) -> materials.MaterialTable:
        """The working copy (installed by the Display Manager on OK)."""
        return self._work

    def names(self) -> list[str]:
        """The list's names, in order."""
        return [self._list.item(r).text() for r in range(self._list.count())]

    def current(self) -> materials.Material | None:
        """The selected working-copy material, or None."""
        return self._work.get(self._sel) if self._sel else None

    def delete_button(self) -> QPushButton:
        """The Delete button (disabled with the reason as its tooltip)."""
        return self._del_btn

    def section_selector(self) -> Selector:
        """The Section selector."""
        return self._section

    def name_field(self) -> QLineEdit:
        """The Name field (disabled on None)."""
        return self._name

    def used_label(self) -> QLabel:
        """The "Used by" line."""
        return self._used

    def select_name(self, name: str) -> bool:
        """Select the material called *name*; False when there is none."""
        m = self._work.by_name(name)
        if m is None:
            return False
        self._select(m.id)
        return True

    def add_material(self) -> materials.Material:
        """Add a material with no hatch and select it."""
        m = self._work.add(materials.Material(
            fill_types.new_id(), self._work.free_name(_NEW_NAME), None))
        self._touch(select=m.id, rebuild=True)
        return m

    def duplicate_material(self) -> materials.Material | None:
        """Duplicate the selected material (name + " Copy") and select the copy."""
        cur = self.current()
        if cur is None:
            return None
        m = self._work.add(materials.Material(
            fill_types.new_id(), self._work.free_name(f"{cur.name} Copy"), cur.fill_type))
        self._touch(select=m.id, rebuild=True)
        return m

    def set_name(self, name: str) -> bool:
        """Rename the selected material; a blank or clashing name is refused."""
        cur = self.current()
        if cur is None or cur.id == MATERIAL_NONE_ID:
            return False
        name = str(name).strip()
        if name == cur.name:
            self._say("")
            return True
        if not name:
            self._refuse(cur, "A material needs a name.")
            return False
        other = self._work.by_name(name)
        if other is not None and other.id != cur.id:
            self._refuse(cur, f"A Material called \"{other.name}\" already exists.")
            return False
        self._work.replace(replace(cur, name=name))
        self._say("")
        self._touch(select=cur.id, rebuild=True)
        return True

    def set_fill_type(self, type_id) -> None:
        """Point the selected material at *type_id* (None = no hatch)."""
        cur = self.current()
        if cur is None or cur.fill_type == type_id:
            return
        self._work.replace(replace(cur, fill_type=type_id))
        self._touch(select=cur.id, rebuild=False)
        self._load(self.current())

    def set_default(self, category: str, material_id: str) -> None:
        """Set a category default on the working copy."""
        self._work.set_default(category, material_id)
        self._users.clear()
        self._touch(rebuild=False)
        self._fill_defaults()

    def refresh_fill_types(self) -> None:
        """Re-list the Section selector (the Fill Types tab changed)."""
        self._loading = True
        try:
            cur = self.current()
            sel = self._section
            sel.clear()
            sel.addItem(NO_HATCH_LABEL, None)
            table = self._fill_table()
            for t in table.all():
                sel.addItem(QIcon(look_pixmap(t.layers, self._registry())), t.name, t.id)
            self._select_section(cur)
        finally:
            self._loading = False
        self._preview.update()

    # -- list ------------------------------------------------------------------
    def _select(self, material_id) -> None:
        for r in range(self._list.count()):
            if self._list.item(r).data(Qt.ItemDataRole.UserRole) == material_id:
                self._list.setCurrentRow(r)
                return
        self._list.setCurrentRow(-1)

    def _rebuild_list(self, select: str | None = None) -> None:
        keep = select or self._sel
        self._loading = True
        try:
            self._list.clear()
            for m in self._work.all():
                it = QListWidgetItem(self._icon(m), m.name)
                it.setData(Qt.ItemDataRole.UserRole, m.id)
                self._list.addItem(it)
        finally:
            self._loading = False
        if self._work.get(keep) is None:
            keep = MATERIAL_NONE_ID
        self._sel = None
        self._select(keep)
        self._fill_defaults()

    def _layers(self, m) -> FillLayers:
        t = self._fill_table().get(m.fill_type) if m is not None and m.fill_type else None
        return t.layers if t is not None else FillLayers()

    def _icon(self, m) -> QIcon:
        return QIcon(look_pixmap(self._layers(m), self._registry(),
                                 _LIST_ICON.width(), _LIST_ICON.height()))

    def _on_row(self, row: int) -> None:
        if self._loading:
            return
        it = self._list.item(row) if row >= 0 else None
        self._sel = it.data(Qt.ItemDataRole.UserRole) if it is not None else None
        self._load(self.current())

    def _fill_defaults(self) -> None:
        self._loading = True
        try:
            for cat, sel in self._default_sel.items():
                sel.clear()
                for m in self._work.all():
                    sel.addItem(m.name, m.id)
                sel.setCurrentIndex(sel.findData(self._work.default_for(cat)))
        finally:
            self._loading = False

    def _on_default(self, category: str) -> None:
        if not self._loading:
            self.set_default(category, self._default_sel[category].currentData())

    # -- editor ----------------------------------------------------------------
    def _select_section(self, m) -> None:
        tid = m.fill_type if m is not None else None
        sel = self._section
        idx = sel.findData(tid) if tid else 0
        if idx < 0:                # a type the table lacks stays visible, never swapped
            sel.addItem(fill_types.missing_type_label(tid), tid)
            idx = sel.count() - 1
        sel.setCurrentIndex(idx)

    def _load(self, m) -> None:
        self._loading = True
        try:
            self._editor.setEnabled(m is not None)
            self._dup_btn.setEnabled(m is not None)
            self._name.setText(m.name if m is not None else "")
            self._name.setEnabled(m is not None and m.id != MATERIAL_NONE_ID)
            self._say("")
            self._select_section(m)
        finally:
            self._loading = False
        self._refresh_chrome()

    def _on_section(self, _index: int) -> None:
        if not self._loading:
            self.set_fill_type(self._section.currentData())

    # -- chrome ----------------------------------------------------------------
    def _touch(self, select: str | None = None, rebuild: bool = False) -> None:
        self.dirty = True
        if rebuild:
            self._rebuild_list(select)
        else:
            cur, it = self.current(), self._list.currentItem()
            if cur is not None and it is not None:
                it.setIcon(self._icon(cur))
        self._refresh_chrome()
        self.edited.emit()

    def _users_of(self, material_id: str) -> list[str]:
        if material_id not in self._users:
            self._users[material_id] = materials.material_users(
                material_id, self._scene, self._work)
        return self._users[material_id]

    def _refresh_chrome(self) -> None:
        cur = self.current()
        self._preview.update()
        users = self._users_of(cur.id) if cur is not None else []
        used = f"Used by {len(users)}: {', '.join(users)}" if users else "Not used"
        self._used.setText(used)
        none = cur is not None and cur.id == MATERIAL_NONE_ID
        self._del_btn.setEnabled(cur is not None and not none and not users)
        self._del_btn.setToolTip(_NONE_TIP if none else used if users else "Delete this Material")

    def showEvent(self, event):  # noqa: N802 (Qt API)
        """Re-scan on show: the plan may have changed who uses a material."""
        self._users.clear()
        self.refresh_fill_types()
        self._refresh_chrome()
        super().showEvent(event)

    def _paint_preview(self, painter: QPainter, rect) -> None:
        r = rect.toRect().adjusted(2, 2, -2, -2)
        if r.width() > 0 and r.height() > 0:
            painter.drawPixmap(r.topLeft(), look_pixmap(
                self._layers(self.current()), self._registry(), r.width(), r.height()))

    def _say(self, text: str) -> None:
        self._status.setText(text)

    def _refuse(self, cur, why: str) -> None:
        self._name.setText(cur.name)
        self._say(why)

    def _on_delete(self) -> None:
        cur = self.current()
        if cur is None or cur.id == MATERIAL_NONE_ID or self._users_of(cur.id):
            return
        row = self._list.currentRow()
        self._work.remove(cur.id)
        rest = self._work.all()
        nxt = rest[min(row, len(rest) - 1)].id
        self._sel = None
        self._users.clear()
        self._touch(select=nxt, rebuild=True)
