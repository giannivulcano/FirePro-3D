"""Fill Types tab of the Display Manager (HF5 R5, layout B).

A list of the project's Fill Types on the left and an editor for the selected
one on the right (name, background, pattern, live preview, "Used by"). Edits
land on a **working copy** of the project table; the Display Manager installs
it on OK (:func:`firepro3d.fill_types.set_project_table`) and drops it on
Cancel. Built from ``ui_kit`` widgets and theme tokens only
(docs/specs/ui-design-system.md); the pickers are the house colour picker
(:class:`ui_kit.Swatch`) and the shared pattern list (``tile_choices``).
"""
from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from . import fill_types
from .colour_tokens import resolve_colour
from .constants import FILL_TYPE_SOLID_BLACK, TOKEN_AUTO, TOKEN_ELEMENT
from .fill_layers import (BackgroundLayer, FillLayers, PatternLayer,
                          alpha as fill_alpha)
from .theme import M
from .ui_kit import PaintSwatch, Section, Selector, Stepper, Swatch, ToggleSwitch

_NEW_TYPE_NAME = "New Fill Type"
_LIST_ICON = QSize(32, 16)


def look_pixmap(layers: FillLayers, registry=None, w: int = 40, h: int = 20) -> QPixmap:
    """A *w* x *h* swatch of a Fill Type's look: the body behind the pattern.

    By element (R8) previews in Automatic (the element's colour is only known
    at paint). Shared by this tab and the Display Manager section selector.
    """
    from .hatch_render import pattern_preview
    bg = layers.background
    ground = None
    if bg is not None:
        ground = resolve_colour(bg.color)
        ground.setAlpha(fill_alpha(bg.opacity))
    pat = layers.pattern
    if pat is None:
        pix = QPixmap(w, h)
        pix.fill(ground if ground is not None else QColor(0, 0, 0, 0))
        return pix
    col = resolve_colour(TOKEN_AUTO if pat.color == TOKEN_ELEMENT else pat.color)
    col.setAlpha(fill_alpha(pat.opacity))
    return pattern_preview(pat.ref, col, w, h, registry, background=ground)


def _pct(fraction: float) -> int:
    return int(round(fraction * 100))


class FillTypesTab(QWidget):
    """Layout-B editor over a working copy of the project Fill Type table.

    Args:
        scene: The project ``Model_Space`` (pattern registry, "Used by").
        parent: Dialog parent.

    Signals:
        edited: The working copy changed (add / rename / restyle / delete).
    """

    edited = pyqtSignal()

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._work = fill_types.project_table().copy()
        self.dirty = False
        self._sel: str | None = None
        self._loading = False
        self._users: dict[str, list[str]] = {}   # type id -> users (scene scan, cached)
        self._last_bg = "#000000"
        self._last_pat = TOKEN_AUTO
        self._build()
        self._rebuild_list()

    # -- build ---------------------------------------------------------------
    def _registry(self):
        return getattr(self._scene, "block_registry", None)

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(M.MD, M.MD, M.MD, M.MD)
        root.setSpacing(M.LG)

        # left: the list + Add / Duplicate / Delete
        left = QVBoxLayout()
        left.setSpacing(M.SM)
        self._list = QListWidget()
        self._list.setIconSize(_LIST_ICON)
        self._list.setMinimumWidth(190)
        self._list.setToolTip("The project's Fill Types")
        self._list.currentRowChanged.connect(self._on_row)
        left.addWidget(self._list, 1)
        btns = QHBoxLayout()
        btns.setSpacing(M.SM)
        self._add_btn = QPushButton("Add")
        self._add_btn.setToolTip("Add a new Fill Type (a copy of Solid Black's look)")
        self._add_btn.clicked.connect(lambda: self.add_type())
        self._dup_btn = QPushButton("Duplicate")
        self._dup_btn.setToolTip("Duplicate the selected Fill Type")
        self._dup_btn.clicked.connect(lambda: self.duplicate_type())
        self._del_btn = QPushButton("Delete")
        self._del_btn.clicked.connect(self._on_delete)
        for b in (self._add_btn, self._dup_btn, self._del_btn):
            btns.addWidget(b)
        left.addLayout(btns)
        root.addLayout(left, 0)

        # right: the editor
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
        self._name.setToolTip("The Fill Type's name (unique in the project)")
        self._name.editingFinished.connect(lambda: self.set_name(self._name.text()))
        self._status = QLabel("")
        self._status.setProperty("role", "muted")
        nb.addWidget(self._name)
        nb.addWidget(self._status)
        ed.addWidget(Section("Name", name_box))

        bg_box = QWidget()
        bg = QVBoxLayout(bg_box)
        bg.setContentsMargins(0, 0, 0, 0)
        bg.setSpacing(M.SM)
        self._bg_on = ToggleSwitch("Show background")
        self._bg_on.setToolTip("Fill the body of the shape behind the pattern")
        self._bg_swatch = Swatch(self._last_bg, context="Background colour")
        self._bg_swatch.setToolTip("Background colour")
        self._bg_op = Stepper()
        self._bg_op.setRange(0, 100)
        self._bg_op.setToolTip("Background opacity (0-100 %)")
        bg.addWidget(self._bg_on)
        bg.addLayout(self._row("Colour", self._bg_swatch))
        bg.addLayout(self._row("Opacity %", self._bg_op))
        ed.addWidget(Section("Background", bg_box))
        self._bg_on.toggled.connect(lambda _on: self._on_bg("on"))
        self._bg_swatch.colorChanged.connect(self._on_bg_colour)
        self._bg_op.valueChanged.connect(lambda _v: self._on_bg("opacity"))

        pat_box = QWidget()
        pt = QVBoxLayout(pat_box)
        pt.setContentsMargins(0, 0, 0, 0)
        pt.setSpacing(M.SM)
        self._pat_on = ToggleSwitch("Show pattern")
        self._pat_on.setToolTip("Tile a pattern block over the shape")
        self._pat_sel = Selector()
        self._pat_sel.setToolTip("Pattern block (project tiles, then the Hatch patterns folder)")
        self._pat_swatch = Swatch(self._last_pat, context="Pattern colour")
        self._pat_swatch.setToolTip("Pattern colour")
        self._pat_elem = ToggleSwitch("By element")
        self._pat_elem.setToolTip("Draw the pattern in the line colour of the element "
                                  "that shows the fill (a cut wall, a region's own colour)")
        self._pat_scale = Stepper()
        self._pat_scale.setRange(1, 100000)
        self._pat_scale.setToolTip("Pattern scale (100 % = authored size)")
        self._pat_op = Stepper()
        self._pat_op.setRange(0, 100)
        self._pat_op.setToolTip("Pattern opacity (0-100 %)")
        pt.addWidget(self._pat_on)
        pt.addLayout(self._row("Pattern", self._pat_sel))
        pt.addLayout(self._row("Colour", self._pat_swatch))
        pt.addWidget(self._pat_elem)
        pt.addLayout(self._row("Scale %", self._pat_scale))
        pt.addLayout(self._row("Opacity %", self._pat_op))
        ed.addWidget(Section("Pattern", pat_box))
        self._pat_on.toggled.connect(lambda _on: self._on_pat("on"))
        self._pat_sel.currentIndexChanged.connect(lambda _i: self._on_pat("ref"))
        self._pat_swatch.colorChanged.connect(self._on_pat_colour)
        self._pat_elem.toggled.connect(lambda _on: self._on_pat("element"))
        self._pat_scale.valueChanged.connect(lambda _v: self._on_pat("scale"))
        self._pat_op.valueChanged.connect(lambda _v: self._on_pat("opacity"))

        self._preview = PaintSwatch(self._paint_preview, height=72)
        self._preview.setToolTip("Live preview of the look")
        ed.addWidget(Section("Preview", self._preview))
        self._used = QLabel("")
        self._used.setProperty("role", "muted")
        self._used.setWordWrap(True)
        ed.addWidget(self._used)
        ed.addStretch(1)
        root.addWidget(self._editor, 1)

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
    def table(self) -> fill_types.FillTypeTable:
        """The working copy (installed by the Display Manager on OK)."""
        return self._work

    def current_type(self) -> fill_types.FillType | None:
        """The selected working-copy type, or None."""
        return self._work.get(self._sel) if self._sel else None

    def delete_button(self) -> QPushButton:
        """The Delete button (disabled with a "Used by N" tooltip while used)."""
        return self._del_btn

    def add_type(self) -> fill_types.FillType:
        """Add "New Fill Type" with Solid Black's look and select it."""
        base = self._work.by_name(FILL_TYPE_SOLID_BLACK)
        layers = base.layers if base is not None else fill_types.FALLBACK_LAYERS
        t = self._work.add(fill_types.FillType(
            fill_types.new_id(), self._work.free_name(_NEW_TYPE_NAME), layers))
        self._touch(select=t.id, rebuild=True)
        self._name.setFocus()
        self._name.selectAll()
        return t

    def duplicate_type(self) -> fill_types.FillType | None:
        """Duplicate the selected type (name + " Copy") and select the copy."""
        cur = self.current_type()
        if cur is None:
            return None
        t = self._work.add(fill_types.FillType(
            fill_types.new_id(), self._work.free_name(f"{cur.name} Copy"), cur.layers))
        self._touch(select=t.id, rebuild=True)
        return t

    def select_name(self, name: str) -> bool:
        """Select the type called *name*; False when there is none."""
        t = self._work.by_name(name)
        if t is None:
            return False
        self._select(t.id)
        return True

    def set_name(self, name: str) -> bool:
        """Rename the selected type; a clash with another name, a reserved name
        ("(Custom)", "? ..." -- the region panel would shadow / mis-pick it) or a
        blank one is refused (the old name stays, the reason shows below)."""
        cur = self.current_type()
        if cur is None:
            return False
        name = str(name).strip()
        if name == cur.name:
            self._say("")
            return True
        if fill_types.reserved_name(name):
            self._refuse(cur, "That name is reserved: pick another.")
            return False
        other = self._work.by_name(name)
        if other is not None and other.id != cur.id:
            self._refuse(cur, f"A Fill Type called \"{other.name}\" already exists.")
            return False
        self._work.replace(replace(cur, name=name))
        self._say("")
        self._touch(select=cur.id, rebuild=True)
        return True

    def set_background(self, on: bool, colour: str, opacity: float) -> None:
        """Set the selected type's background layer (opacity a 0-1 fraction)."""
        cur = self.current_type()
        if cur is None:
            return
        layer = BackgroundLayer(colour, float(opacity)) if on else None
        self._commit(replace(cur.layers, background=layer))

    def set_pattern(self, on: bool, ref: str | None, colour: str,
                    scale: float, opacity: float) -> None:
        """Set the selected type's pattern layer (opacity a 0-1 fraction)."""
        cur = self.current_type()
        if cur is None:
            return
        layer = (PatternLayer(ref, colour, float(opacity), float(scale))
                 if on and ref else None)
        self._commit(replace(cur.layers, pattern=layer))

    # -- selection / list ------------------------------------------------------
    def _select(self, type_id: str | None) -> None:
        for r in range(self._list.count()):
            if self._list.item(r).data(Qt.ItemDataRole.UserRole) == type_id:
                self._list.setCurrentRow(r)
                return
        self._list.setCurrentRow(-1)

    def _rebuild_list(self, select: str | None = None) -> None:
        keep = select or self._sel
        self._loading = True
        try:
            self._list.clear()
            for t in self._work.all():
                it = QListWidgetItem(self._icon(t), t.name)
                it.setData(Qt.ItemDataRole.UserRole, t.id)
                self._list.addItem(it)
        finally:
            self._loading = False
        if self._work.get(keep) is None:
            keep = self._list.item(0).data(Qt.ItemDataRole.UserRole) if self._list.count() else None
        self._sel = None
        self._select(keep)
        if keep is None:
            self._load(None)

    def _icon(self, t) -> QIcon:
        return QIcon(look_pixmap(t.layers, self._registry(),
                                 _LIST_ICON.width(), _LIST_ICON.height()))

    def _on_row(self, row: int) -> None:
        if self._loading:
            return
        it = self._list.item(row) if row >= 0 else None
        self._sel = it.data(Qt.ItemDataRole.UserRole) if it is not None else None
        self._load(self.current_type())

    # -- editor <-> working copy -----------------------------------------------
    def _load(self, t) -> None:
        """Fill every control from *t* without writing back."""
        self._loading = True
        try:
            self._editor.setEnabled(t is not None)
            self._add_btn.setEnabled(True)
            self._dup_btn.setEnabled(t is not None)
            self._name.setText(t.name if t is not None else "")
            self._say("")
            layers = t.layers if t is not None else FillLayers()
            bg, pat = layers.background, layers.pattern
            if bg is not None:
                self._last_bg = bg.color
            self._bg_on.setChecked(bg is not None)
            self._bg_swatch.set_hex(self._last_bg)
            self._bg_swatch.setEnabled(bg is not None)
            self._bg_op.setValue(_pct(bg.opacity) if bg is not None else 100)
            self._bg_op.setEnabled(bg is not None)
            self._fill_pattern_selector(pat.ref if pat is not None else None)
            elem = pat is not None and pat.color == TOKEN_ELEMENT
            if pat is not None and not elem:
                self._last_pat = pat.color
            self._pat_on.setChecked(pat is not None)
            self._pat_sel.setEnabled(pat is not None)
            self._pat_swatch.set_hex(self._last_pat)
            self._pat_swatch.setEnabled(pat is not None and not elem)
            self._pat_elem.setChecked(elem)
            self._pat_elem.setEnabled(pat is not None)
            self._pat_scale.setValue(_pct(pat.scale) if pat is not None else 100)
            self._pat_scale.setEnabled(pat is not None)
            self._pat_op.setValue(_pct(pat.opacity) if pat is not None else 100)
            self._pat_op.setEnabled(pat is not None)
        finally:
            self._loading = False
        self._refresh_chrome()

    def _fill_pattern_selector(self, ref) -> None:
        from .hatch_patterns import MISSING_PATTERN_LABEL, canonical_ref, tile_choices
        choices = tile_choices(self._registry())
        sel = self._pat_sel
        sel.blockSignals(True)
        try:
            sel.clear()
            for label, r in choices:
                sel.addItem(label, r)
            ref = canonical_ref(ref)
            if ref:
                idx = sel.findData(ref)
                if idx < 0:        # an unresolvable ref stays visible (D-A36), never swapped
                    sel.addItem(MISSING_PATTERN_LABEL, ref)
                    idx = sel.count() - 1
                sel.setCurrentIndex(idx)
        finally:
            sel.blockSignals(False)

    def _commit(self, layers: FillLayers) -> None:
        cur = self.current_type()
        if cur is None or layers == cur.layers:
            return
        self._work.replace(replace(cur, layers=layers))
        self._touch(select=cur.id, rebuild=False)
        self._load(self.current_type())

    def _on_bg(self, source: str) -> None:
        cur = self.current_type()
        if self._loading or cur is None:
            return
        old = cur.layers.background
        if not self._bg_on.isChecked():
            self._commit(replace(cur.layers, background=None))
            return
        op = (self._bg_op.value() / 100.0 if source == "opacity" or old is None
              else old.opacity)
        col = old.color if old is not None else self._last_bg
        self._commit(replace(cur.layers, background=BackgroundLayer(col, op)))

    def _on_bg_colour(self, value: str) -> None:
        cur = self.current_type()
        if self._loading or cur is None:
            return
        if not value:                                   # No Fill = background off
            self._commit(replace(cur.layers, background=None))
            return
        self._last_bg = value
        old = cur.layers.background
        self._commit(replace(cur.layers, background=BackgroundLayer(
            value, old.opacity if old is not None else 1.0)))

    def _on_pat(self, source: str) -> None:
        cur = self.current_type()
        if self._loading or cur is None:
            return
        from .hatch_patterns import DEFAULT_TILE_REF
        old = cur.layers.pattern
        if not self._pat_on.isChecked():
            self._commit(replace(cur.layers, pattern=None))
            return
        ref = self._pat_sel.currentData() or DEFAULT_TILE_REF
        if source != "ref" and old is not None:
            ref = old.ref
        col = (TOKEN_ELEMENT if self._pat_elem.isChecked()
               else (old.color if old is not None and old.color != TOKEN_ELEMENT
                     else self._last_pat))
        scale = (max(self._pat_scale.value(), 1) / 100.0 if source == "scale" or old is None
                 else old.scale)
        op = self._pat_op.value() / 100.0 if source == "opacity" or old is None else old.opacity
        self._commit(replace(cur.layers, pattern=PatternLayer(ref, col, op, scale)))

    def _on_pat_colour(self, value: str) -> None:
        cur = self.current_type()
        if self._loading or cur is None or cur.layers.pattern is None:
            return
        if not value:                 # a pattern needs a colour: turn the pattern off instead
            self._load(cur)           # snap the swatch back, then say why
            self._say("A pattern needs a colour; use the Show pattern switch to turn it off.")
            return
        self._last_pat = value
        self._commit(replace(cur.layers, pattern=replace(cur.layers.pattern, color=value)))

    # -- chrome ----------------------------------------------------------------
    def _touch(self, select: str | None = None, rebuild: bool = False) -> None:
        self.dirty = True
        if rebuild:
            self._rebuild_list(select)
        else:
            cur = self.current_type()
            it = self._list.currentItem()
            if cur is not None and it is not None:
                it.setIcon(self._icon(cur))
        self._refresh_chrome()
        self.edited.emit()

    def _refresh_chrome(self) -> None:
        cur = self.current_type()
        self._preview.update()
        users = self._users_of(cur.id) if cur is not None else []
        self._used.setText(f"Used by {len(users)}: {', '.join(users)}" if users
                           else "Not used")
        self._del_btn.setEnabled(cur is not None and not users)
        self._del_btn.setToolTip(
            f"Used by {len(users)}: {', '.join(users)}" if users
            else "Delete this Fill Type")

    def _users_of(self, type_id: str) -> list[str]:
        """``type_users`` cached per type: restyling never changes who uses a
        type, so a look edit does not rescan the scene (cleared on show)."""
        if type_id not in self._users:
            self._users[type_id] = fill_types.type_users(type_id, self._scene)
        return self._users[type_id]

    def showEvent(self, event):  # noqa: N802 (Qt API)
        """Re-scan on show: other tabs may have changed who uses a type."""
        self._users.clear()
        self._refresh_chrome()
        super().showEvent(event)

    def _paint_preview(self, painter: QPainter, rect) -> None:
        cur = self.current_type()
        if cur is None:
            return
        r = rect.toRect().adjusted(2, 2, -2, -2)
        if r.width() > 0 and r.height() > 0:
            painter.drawPixmap(r.topLeft(), look_pixmap(
                cur.layers, self._registry(), r.width(), r.height()))

    def _say(self, text: str) -> None:
        self._status.setText(text)

    def _refuse(self, cur, why: str) -> None:
        self._name.setText(cur.name)
        self._say(why)

    def _on_delete(self) -> None:
        cur = self.current_type()
        if cur is None or self._users_of(cur.id):
            return
        row = self._list.currentRow()
        self._work.remove(cur.id)
        nxt = None
        rest = self._work.all()
        if rest:
            nxt = rest[min(row, len(rest) - 1)].id
        self._sel = None
        self._touch(select=nxt, rebuild=True)
