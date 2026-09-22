# Text Annotation Frame + FontSelect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a printed box-frame axis to text annotations (border visibility, named line-weight, line-type, corner style) and promote the font picker to a reusable `ui_kit.FontSelect` widget, surfaced as a new **Frame** ribbon group beside the existing **Text**/Font group.

**Architecture:** Frame state is four new fields on the existing `TextAnnotationData` (one unified `TextItem`, both surfaces). Rendering adds a stroked `QPainterPath` in `TextItem.paint`. All commits route through the existing `TextItem.set_property` → `FormatTextCommand` (paper) / geom2d-set (model) path — no new undo machinery. Weight reuses the named line-weight system (`paper_display.resolve_line_weight_mm`).

**Tech Stack:** Python 3 · PyQt6 · pytest (session-scoped `qapp` fixture, no pytest-qt) · offscreen QPA.

**Governing spec:** `docs/specs/text-annotation-system.md`. **Branch:** `feat/text-annotation-frame` (already created; spec+mockup committed `1b25825`).

**Ground rules from project memory:**
- Dual serialization already covered by `to_dict`/`from_dict` (verify, don't re-plumb).
- Live-only render bugs dodge headless — every render test drives the real `paint`; also launch-smoke at the end.
- No separate frame color — the border reads `data.color`.
- Offscreen QPA renders shapes correctly (fonts become tofu, shapes are fine) — safe for frame-pixel assertions.
- Run pytest to a file and check `$?`; never `| tail` (masks exit code).

---

## File Structure

- **Modify** `firepro3d/constants.py` — add `TEXT_FRAME_CORNER_FRAC`.
- **Modify** `firepro3d/text_item.py` — 4 data fields; `to_dict`/`from_dict`; `_frame_path()` + frame draw in `paint`; model `get_properties`/`set_property` frame keys.
- **Modify** `firepro3d/paper_space.py` — `_text_panel_properties` + `_text_panel_change` frame keys.
- **Create** `firepro3d/frame_group.py` — `FrameGroupController` (sibling to `FontGroupController`).
- **Modify** `firepro3d/ui_kit.py` — `FontSelect(QComboBox)` widget.
- **Modify** `firepro3d/font_group.py` — swap `QFontComboBox` → `FontSelect`.
- **Modify** `main.py` — add the **Frame** ribbon group; wire `FrameGroupController`.
- **Create** `firepro3d/graphics/Ribbon/text_border.svg`, `corner_square.svg`, `corner_fillet.svg`, `corner_chamfer.svg`.
- **Create** `tests/test_text_frame.py`, `tests/test_font_select.py`, `tests/test_frame_group.py`.

---

## Task 1: Frame data fields + serialization

**Files:**
- Modify: `firepro3d/constants.py` (near line 200, the `TEXT_*` block)
- Modify: `firepro3d/text_item.py:64-108` (`TextAnnotationData` fields + `to_dict`/`from_dict`)
- Test: `tests/test_text_frame.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_text_frame.py
from firepro3d.text_item import TextAnnotationData, TextItem


def test_frame_fields_default_off():
    d = TextAnnotationData()
    assert d.border is False
    assert d.border_weight == "Light"
    assert d.border_line_type == "solid"
    assert d.border_corner == "square"


def test_frame_roundtrip_to_from_dict():
    d = TextAnnotationData(text="N", border=True, border_weight="Heavy",
                           border_line_type="dashed", border_corner="chamfer")
    d2 = TextAnnotationData.from_dict(d.to_dict())
    assert (d2.border, d2.border_weight, d2.border_line_type, d2.border_corner) \
        == (True, "Heavy", "dashed", "chamfer")


def test_frame_from_dict_legacy_defaults_off():
    # A pre-frame record (no border keys) loads with the border off.
    legacy = {"type": "text", "text": "x", "height_mm": 4.0}
    d = TextAnnotationData.from_dict(legacy)
    assert d.border is False and d.border_corner == "square"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_text_frame.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: FAIL — `TextAnnotationData` has no attribute `border`.

- [ ] **Step 3: Add the constant**

In `firepro3d/constants.py`, after `TEXT_BOX_MARGIN_MM = 1.0`:

```python
TEXT_FRAME_CORNER_FRAC = 0.14  # fillet/chamfer size as a fraction of the shorter box side
```

- [ ] **Step 4: Add the four fields to `TextAnnotationData`**

In `firepro3d/text_item.py`, in the dataclass (after `opaque_bg: bool = False`, before `angle`):

```python
    border: bool = False                         # frame visibility
    border_weight: str = "Light"                 # named line-weight (resolve_line_weight_mm)
    border_line_type: str = "solid"              # 'solid'|'dashed'|'dotted'|'dashdot'
    border_corner: str = "square"                # 'square'|'round'|'chamfer'
```

Update the docstring `Fields` block to mention them (one line each).

- [ ] **Step 5: Extend `to_dict` and `from_dict`**

In `to_dict`, add before the closing brace of the returned dict:

```python
            "border": self.border, "border_weight": self.border_weight,
            "border_line_type": self.border_line_type, "border_corner": self.border_corner,
```

In `from_dict`, add to the `cls(...)` call (before `type=...`):

```python
            border=bool(d.get("border", False)),
            border_weight=d.get("border_weight", "Light"),
            border_line_type=d.get("border_line_type", "solid"),
            border_corner=d.get("border_corner", "square"),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_text_frame.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: PASS (3 passed).

- [ ] **Step 7: Verify dual-serialization parity (no code — a grep check)**

Run: `python -m pytest tests/test_text_frame.py -q; grep -n "to_dict\|from_dict" firepro3d/model_space.py | grep -i text`
Confirm the model undo path uses `TextItem.to_dict()`/`from_dict()` (it does: `_capture_network` `"texts": [t.to_dict() ...]` and restore `TextItem.from_dict(d)`), so the four fields propagate through undo automatically. If any code reads the individual border fields off a dict directly, add them there. (Expected: none.)

- [ ] **Step 8: Commit**

```bash
git add firepro3d/constants.py firepro3d/text_item.py tests/test_text_frame.py
git commit -m "feat(text): add frame data fields to TextAnnotationData"
```

---

## Task 2: Frame rendering in `TextItem.paint`

**Files:**
- Modify: `firepro3d/text_item.py` (`paint` at ~425; add `_frame_path` + `_frame_pen` helpers near `_box_rect_local`)
- Test: `tests/test_text_frame.py`

- [ ] **Step 1: Write the failing test (render-driven, both surfaces)**

Append to `tests/test_text_frame.py`:

```python
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter, QColor


class _PaperScene:
    """Minimal stand-in reporting device-independent (paper) sizing."""
    def device_independent_text(self):
        return True


def _render_item(item, w=200, h=120):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    # paint() works in the item's local frame; bake its scale so the box fits.
    p.scale(item.scale(), item.scale())
    item.paint(p, None, None)
    p.end()
    return img


def _has_dark_edge_pixels(img):
    dark = 0
    for x in range(img.width()):
        c = QColor(img.pixel(x, 4))
        if c.red() < 128 and c.green() < 128 and c.blue() < 128:
            dark += 1
    return dark > 3


def test_frame_renders_when_border_on_model():
    item = TextItem(TextAnnotationData(text="ABC", height_mm=4.0))
    assert not _has_dark_edge_pixels(_render_item(item))   # border OFF → no top edge
    item.set_property("Border", True)
    assert _has_dark_edge_pixels(_render_item(item))        # border ON → top edge drawn


def test_frame_path_corner_variants_nonempty():
    item = TextItem(TextAnnotationData(text="ABC", border=True))
    for corner in ("square", "round", "chamfer"):
        item._data.border_corner = corner
        assert not item._frame_path().isEmpty()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_text_frame.py -k frame_render -q > _t.txt 2>&1; echo EXIT=$?`
Expected: FAIL — `TextItem` has no attribute `_frame_path`; border ON does not draw an edge.

- [ ] **Step 3: Add the frame-path + pen helpers**

In `firepro3d/text_item.py`, after `_box_rect_local` (~line 317), add:

```python
    def _frame_path(self) -> "QPainterPath":
        """Border path for the box rect, honoring the corner style (local frame)."""
        from .constants import TEXT_FRAME_CORNER_FRAC
        r = self._box_rect_local()
        path = QPainterPath()
        if self._data.border_corner == "square":
            path.addRect(r)
            return path
        rad = TEXT_FRAME_CORNER_FRAC * min(r.width(), r.height())
        if self._data.border_corner == "round":
            path.addRoundedRect(r, rad, rad)
            return path
        # chamfer: 45-degree cut of size `rad` at each corner
        l, t, ri, b = r.left(), r.top(), r.right(), r.bottom()
        path.moveTo(l + rad, t)
        path.lineTo(ri - rad, t); path.lineTo(ri, t + rad)
        path.lineTo(ri, b - rad); path.lineTo(ri - rad, b)
        path.lineTo(l + rad, b); path.lineTo(l, b - rad)
        path.lineTo(l, t + rad); path.closeSubpath()
        return path

    def _frame_pen(self) -> "QPen":
        """Pen for the border: text color, named weight mapped into local units,
        line-type → Qt PenStyle. Width is lw_mm / scale so it plots at the true mm
        weight on paper (scale maps local→paper mm) and equals lw_mm on a model
        scene (scale == 1)."""
        from .paper_display import resolve_line_weight_mm
        lw_mm = resolve_line_weight_mm(self._data.border_weight)
        scale = self.scale() or 1.0
        pen = QPen(QColor(self._data.color))
        pen.setWidthF(max(lw_mm / scale, 1e-4))
        pen.setStyle({
            "solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine,
            "dotted": Qt.PenStyle.DotLine, "dashdot": Qt.PenStyle.DashDotLine,
        }.get(self._data.border_line_type, Qt.PenStyle.SolidLine))
        return pen
```

- [ ] **Step 4: Draw the frame in `paint`**

In `TextItem.paint`, inside the existing `painter.save()`/`restore()` block, AFTER the `super().paint(...)` call and BEFORE the `if self._editing:` block, insert:

```python
        if self._data.border:
            painter.setPen(self._frame_pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._frame_path())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_text_frame.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: PASS. (`set_property("Border", True)` lands in Task 3; for this task, the model `set_property` path already exists but does not yet know "Border" — so temporarily the test sets `item._data.border = True` if needed. **Note:** if Step 1's `set_property("Border", True)` errors, land Task 3 first, then this test. Reorder is acceptable since both commit together conceptually — but keep Task 2's `_frame_path` corner test, which is independent.)

- [ ] **Step 6: Verify the guard goes RED**

Comment out the three-line frame-draw block from Step 4; run `test_frame_renders_when_border_on_model`.
Expected: FAIL (border ON no longer draws an edge). Restore the block.

- [ ] **Step 7: Commit**

```bash
git add firepro3d/text_item.py tests/test_text_frame.py
git commit -m "feat(text): render box frame (corner/line-type/named-weight) in TextItem.paint"
```

---

## Task 3: `set_property` + panel dicts for frame keys

**Files:**
- Modify: `firepro3d/text_item.py` (`get_properties` model branch ~679; `set_property` model branch ~708)
- Modify: `firepro3d/paper_space.py` (`_text_panel_properties` ~1521; `_text_panel_change` ~1555)
- Test: `tests/test_text_frame.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_text_frame.py`:

```python
def test_set_property_frame_keys_model():
    item = TextItem(TextAnnotationData(text="A"))
    item.set_property("Border", True)
    item.set_property("Border Weight", "Heavy")
    item.set_property("Line Type", "dashed")
    item.set_property("Corner", "chamfer")
    d = item._data
    assert (d.border, d.border_weight, d.border_line_type, d.border_corner) \
        == (True, "Heavy", "dashed", "chamfer")


def test_model_get_properties_exposes_frame():
    item = TextItem(TextAnnotationData(text="A", border=True, border_corner="round"))
    props = item.get_properties()
    assert props["Border"]["value"] is True
    assert props["Corner"]["value"] == "round"
    assert set(props["Corner"]["options"]) == {"square", "round", "chamfer"}


def test_paper_panel_change_frame_keys():
    from firepro3d.paper_space import _text_panel_change, _text_panel_properties
    d = TextAnnotationData(text="A")
    assert _text_panel_change(d, "Border", True) == {"border": True}
    assert _text_panel_change(d, "Corner", "chamfer") == {"border_corner": "chamfer"}
    assert _text_panel_change(d, "Border", False) is None   # unchanged → no-op
    form = _text_panel_properties(TextAnnotationData(border=True))
    assert form["Border"]["value"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_text_frame.py -k "frame_keys or get_properties or panel_change" -q > _t.txt 2>&1; echo EXIT=$?`
Expected: FAIL — keys unknown.

- [ ] **Step 3: Model `get_properties` — add frame rows**

In `firepro3d/text_item.py` `get_properties`, in the model-branch dict (after `"Opaque Background"`):

```python
            "Border":       {"type": "toggle", "value": bool(self._data.border)},
            "Line Type":    {"type": "enum", "options": ["solid", "dashed", "dotted", "dashdot"],
                             "value": self._data.border_line_type},
            "Border Weight":{"type": "enum",
                             "options": ["Very Light", "Light", "Medium", "Heavy", "Very Heavy"],
                             "value": self._data.border_weight},
            "Corner":       {"type": "enum", "options": ["square", "round", "chamfer"],
                             "value": self._data.border_corner},
```

- [ ] **Step 4: Model `set_property` — handle frame keys**

In `firepro3d/text_item.py` `set_property`, before the `elif self._geom2d_set(...)` branch:

```python
        elif key == "Border":
            self._data.border = bool(value)
        elif key == "Border Weight":
            self._data.border_weight = str(value)
        elif key == "Line Type":
            self._data.border_line_type = str(value)
        elif key == "Corner":
            self._data.border_corner = str(value)
```

(The trailing `self.prepareGeometryChange(); self._apply_format()` already runs for all handled keys.)

- [ ] **Step 5: Paper `_text_panel_properties` — add frame rows**

In `firepro3d/paper_space.py` `_text_panel_properties`, before `"Leader"`:

```python
        "Border": {"type": "bool", "value": data.border},
        "Line Type": {"type": "enum", "value": data.border_line_type,
                      "options": ["solid", "dashed", "dotted", "dashdot"]},
        "Border Weight": {"type": "enum", "value": data.border_weight,
                          "options": ["Very Light", "Light", "Medium", "Heavy", "Very Heavy"]},
        "Corner": {"type": "enum", "value": data.border_corner,
                   "options": ["square", "round", "chamfer"]},
```

- [ ] **Step 6: Paper `_text_panel_change` — map frame keys**

In `firepro3d/paper_space.py` `_text_panel_change`, before the closing `else: return None`:

```python
    elif key == "Border":
        field, new = "border", bool(value)
    elif key == "Border Weight":
        field, new = "border_weight", str(value)
    elif key == "Line Type":
        field, new = "border_line_type", str(value)
    elif key == "Corner":
        field, new = "border_corner", str(value)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_text_frame.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: PASS (all frame tests, including Task 2's `set_property("Border", True)`).

- [ ] **Step 8: Commit**

```bash
git add firepro3d/text_item.py firepro3d/paper_space.py tests/test_text_frame.py
git commit -m "feat(text): route frame props through set_property + panel forms"
```

---

## Task 4: `FontSelect` ui_kit widget

**Files:**
- Modify: `firepro3d/ui_kit.py` (add `FontSelect`)
- Test: `tests/test_font_select.py`

- [ ] **Step 1: Write the failing test (widget-driven)**

```python
# tests/test_font_select.py
from PyQt6.QtGui import QFontDatabase
from firepro3d.ui_kit import FontSelect


def test_font_select_lists_truetype_families(qapp):
    w = FontSelect()
    fams = [w.itemText(i) for i in range(w.count()) if w.itemData(i, w.ROLE_FAMILY)]
    assert any(f in fams for f in QFontDatabase.families())


def test_font_select_emits_family_and_pins_recents(qapp):
    w = FontSelect()
    seen = []
    w.fontChanged.connect(seen.append)
    target = QFontDatabase.families()[0]
    w.set_current_family(target)
    w.commit_current()                      # simulate an activated selection
    assert seen and seen[-1] == target
    assert w.recent_families()[0] == target  # pinned at top, max 5


def test_font_select_current_family_roundtrip(qapp):
    w = FontSelect()
    fam = QFontDatabase.families()[1]
    w.set_current_family(fam)
    assert w.current_family() == fam
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_font_select.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: FAIL — cannot import `FontSelect`.

- [ ] **Step 3: Implement `FontSelect`**

Add to `firepro3d/ui_kit.py` (imports at top of file as needed):

```python
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QFontDatabase, QPainter
from PyQt6.QtWidgets import QComboBox, QStyledItemDelegate


class _FontPreviewDelegate(QStyledItemDelegate):
    """Paints the family name left and an 'AaBb 0123' preview in that face right."""
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        fam = index.data(FontSelect.ROLE_FAMILY)
        if not fam:
            return
        painter.save()
        f = QFont(fam); f.setPointSize(option.font.pointSize())
        painter.setFont(f)
        painter.setPen(option.palette.text().color())
        r = option.rect.adjusted(0, 0, -8, 0)
        painter.drawText(r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         "AaBb 0123")
        painter.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), 22))


class FontSelect(QComboBox):
    """Reusable font picker: TrueType families with an SHX-ready source seam,
    in-face previews, type-ahead, recently-used (max 5), current checkmark.

    Emits ``fontChanged(str family)`` on an activated selection. A raw
    QFontComboBox cannot carry section headers or (later) SHX entries — this is
    the standard replacement (ui-design-system.md).
    """
    fontChanged = pyqtSignal(str)
    ROLE_FAMILY = Qt.ItemDataRole.UserRole + 1
    MAX_RECENT = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recent: list[str] = []
        self.setEditable(True)                 # enables type-ahead
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setItemDelegate(_FontPreviewDelegate(self))
        self._sources = [("TrueType", QFontDatabase.families())]  # font-source seam
        self._rebuild()
        self.activated.connect(self._on_activated)

    def _add_header(self, text):
        self.addItem(text)
        i = self.count() - 1
        self.setItemData(i, 0, Qt.ItemDataRole.UserRole - 1)  # disable (non-selectable)

    def _add_family(self, fam):
        self.addItem(fam)
        self.setItemData(self.count() - 1, fam, self.ROLE_FAMILY)

    def _rebuild(self, current: str | None = None):
        current = current or self.current_family()
        self.blockSignals(True)
        self.clear()
        if self._recent:
            self._add_header("Recent")
            for fam in self._recent:
                self._add_family(fam)
        for label, fams in self._sources:
            self._add_header(label)
            for fam in fams:
                self._add_family(fam)
        self.blockSignals(False)
        if current:
            self.set_current_family(current)

    def current_family(self) -> str:
        return self.itemData(self.currentIndex(), self.ROLE_FAMILY) or self.currentText()

    def set_current_family(self, fam: str):
        for i in range(self.count()):
            if self.itemData(i, self.ROLE_FAMILY) == fam:
                self.setCurrentIndex(i)
                return
        self.setCurrentText(fam)   # missing font: show the name as typed

    def recent_families(self) -> list[str]:
        return list(self._recent)

    def _pin_recent(self, fam: str):
        if fam in self._recent:
            self._recent.remove(fam)
        self._recent.insert(0, fam)
        del self._recent[self.MAX_RECENT:]

    def commit_current(self):
        """Emit fontChanged for the current family and pin it (used by tests and
        by the activated path)."""
        fam = self.current_family()
        if not fam:
            return
        self._pin_recent(fam)
        self.fontChanged.emit(fam)

    def _on_activated(self, _index):
        fam = self.current_family()
        if not fam:
            return
        self._pin_recent(fam)
        self._rebuild(current=fam)
        self.fontChanged.emit(fam)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_font_select.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add firepro3d/ui_kit.py tests/test_font_select.py
git commit -m "feat(ui_kit): add FontSelect standard font picker widget"
```

---

## Task 5: Swap `font_group.py` onto `FontSelect`

**Files:**
- Modify: `firepro3d/font_group.py:11-14,74-78,334-338`
- Test: `tests/test_font_select.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_font_select.py`:

```python
def test_font_group_uses_fontselect(qapp):
    from firepro3d.font_group import FontGroupController
    from firepro3d.ui_kit import FontSelect
    fg = FontGroupController(get_targets=lambda: [])
    assert isinstance(fg.family_combo, FontSelect)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_font_select.py::test_font_group_uses_fontselect -q > _t.txt 2>&1; echo EXIT=$?`
Expected: FAIL — `family_combo` is a `QFontComboBox`.

- [ ] **Step 3: Replace the widget**

In `firepro3d/font_group.py`:
- Remove `QFontComboBox` from the `PyQt6.QtWidgets` import; add `from .ui_kit import FontSelect`.
- Replace the `family_combo` construction (currently `QFontComboBox()` + `activated` lambda reading `currentFont().family()`):

```python
        self.family_combo = FontSelect()
        self.family_combo.setMaximumWidth(160)
        self.family_combo.fontChanged.connect(lambda fam: self._commit("Font", fam))
        row1.addWidget(self.family_combo)
```

- In `sync()`, replace `self.family_combo.setCurrentFont(QFont(fam))` / `setCurrentIndex(-1)` with:

```python
            if fam is None:
                self.family_combo.setCurrentText("")
            else:
                self.family_combo.set_current_family(fam)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_font_select.py tests/test_text_frame.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: PASS (font group builds with `FontSelect`; no regressions).

- [ ] **Step 5: Commit**

```bash
git add firepro3d/font_group.py tests/test_font_select.py
git commit -m "feat(text): font group uses FontSelect widget"
```

---

## Task 6: `FrameGroupController` (ribbon Frame group)

**Files:**
- Create: `firepro3d/frame_group.py`
- Test: `tests/test_frame_group.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frame_group.py
from firepro3d.text_item import TextItem, TextAnnotationData
from firepro3d.frame_group import FrameGroupController


def _ctl_with_target(qapp):
    item = TextItem(TextAnnotationData(text="A"))
    return FrameGroupController(get_targets=lambda: [item]), item


def test_border_toggle_sets_data(qapp):
    ctl, item = _ctl_with_target(qapp)
    ctl.border_btn.setChecked(True)
    ctl.border_btn.clicked.emit(True)
    assert item._data.border is True


def test_corner_radio_is_exclusive(qapp):
    ctl, item = _ctl_with_target(qapp)
    ctl.commit_corner("chamfer")
    assert item._data.border_corner == "chamfer"
    assert ctl.corner_btns["chamfer"].isChecked()
    ctl.commit_corner("round")
    assert item._data.border_corner == "round"
    assert not ctl.corner_btns["chamfer"].isChecked()


def test_line_type_and_weight_commit(qapp):
    ctl, item = _ctl_with_target(qapp)
    ctl.commit_line_type("dashed")
    ctl.commit_weight("Heavy")
    assert item._data.border_line_type == "dashed"
    assert item._data.border_weight == "Heavy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frame_group.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: FAIL — cannot import `frame_group`.

- [ ] **Step 3: Implement `FrameGroupController`**

```python
# firepro3d/frame_group.py
"""Ribbon "Frame" group for the text box border (text-annotation-system.md).

Sibling to FontGroupController: every commit routes through TextItem.set_property
so paper targets get FormatTextCommand undo and model targets snapshot via the
scene, with multi-select wrapped in one macro. Border toggle + a 3-way corner
radio (Square/Fillet/Chamfer) + stacked Line-type/Line-weight combos, under a
vertical group label.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from . import theme as th
from .paper_space import _text_panel_change

_CORNERS = (("square", "corner_square.svg", "Square corner"),
            ("round", "corner_fillet.svg", "Fillet (rounded) corner"),
            ("chamfer", "corner_chamfer.svg", "Chamfer (cut) corner"))
_LINE_TYPES = ("solid", "dashed", "dotted", "dashdot")
_WEIGHTS = ("Very Light", "Light", "Medium", "Heavy", "Very Heavy")


class FrameGroupController(QObject):
    def __init__(self, get_targets, parent=None):
        super().__init__(parent)
        self._get_targets = get_targets
        self._syncing = False
        self._theme = th.detect()
        self._build_widgets()

    def _build_widgets(self):
        self.container = QWidget()
        col = QVBoxLayout(self.container)
        col.setContentsMargins(2, 4, 2, 0)
        col.setSpacing(2)

        row1 = QHBoxLayout(); row1.setSpacing(2)
        self.border_btn = QToolButton()
        self.border_btn.setText("▢"); self.border_btn.setToolTip("Border visibility")
        self.border_btn.setCheckable(True); self.border_btn.setFixedSize(28, 26)
        self.border_btn.clicked.connect(lambda on: self._commit("Border", bool(on)))
        row1.addWidget(self.border_btn)

        self.corner_btns = {}
        for key, _icon, tip in _CORNERS:
            b = QToolButton(); b.setText(key[0].upper()); b.setToolTip(tip)
            b.setCheckable(True); b.setFixedSize(28, 26)
            b.clicked.connect(lambda _c, k=key: self.commit_corner(k))
            self.corner_btns[key] = b
            row1.addWidget(b)
        col.addLayout(row1)

        self.line_type_combo = QComboBox(); self.line_type_combo.addItems(_LINE_TYPES)
        self.line_type_combo.activated.connect(
            lambda _i: self.commit_line_type(self.line_type_combo.currentText()))
        col.addWidget(self.line_type_combo)

        self.weight_combo = QComboBox(); self.weight_combo.addItems(_WEIGHTS)
        self.weight_combo.activated.connect(
            lambda _i: self.commit_weight(self.weight_combo.currentText()))
        col.addWidget(self.weight_combo)

    def _targets(self):
        return [t for t in self._get_targets() if t is not None]

    def _commit(self, key, value):
        if self._syncing:
            return
        targets = [t for t in self._targets()
                   if _text_panel_change(t.data, key, value) is not None]
        if not targets:
            self.sync(); return
        scene = targets[0].scene()
        stack = getattr(scene, "undo_stack", None) if scene is not None else None
        macro = stack is not None and len(targets) > 1
        if macro:
            stack.beginMacro(f"Frame ({key})")
        try:
            for t in targets:
                t.set_property(key, value)
        finally:
            if macro:
                stack.endMacro()
        self.sync()

    def commit_corner(self, key):
        for k, b in self.corner_btns.items():
            b.setChecked(k == key)
        self._commit("Corner", key)

    def commit_line_type(self, value):
        self._commit("Line Type", value)

    def commit_weight(self, value):
        self._commit("Border Weight", value)

    def set_enabled(self, on: bool):
        self.container.setEnabled(on)

    def sync(self):
        targets = self._targets()
        self._syncing = True
        try:
            if not targets:
                return

            def uniform(getter):
                vals = {getter(t.data) for t in targets}
                return vals.pop() if len(vals) == 1 else None

            self.border_btn.setChecked(uniform(lambda d: d.border) is True)
            corner = uniform(lambda d: d.border_corner)
            for k, b in self.corner_btns.items():
                b.setChecked(corner == k)
            lt = uniform(lambda d: d.border_line_type)
            if lt in _LINE_TYPES:
                self.line_type_combo.setCurrentText(lt)
            wt = uniform(lambda d: d.border_weight)
            if wt in _WEIGHTS:
                self.weight_combo.setCurrentText(wt)
            on = self.border_btn.isChecked()
            for w in (self.line_type_combo, self.weight_combo, *self.corner_btns.values()):
                w.setEnabled(on)
        finally:
            self._syncing = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_frame_group.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add firepro3d/frame_group.py tests/test_frame_group.py
git commit -m "feat(text): add FrameGroupController for the ribbon Frame group"
```

---

## Task 7: Author the 4 Frame icons + wire the ribbon group

**Files:**
- Create: `firepro3d/graphics/Ribbon/text_border.svg`, `corner_square.svg`, `corner_fillet.svg`, `corner_chamfer.svg`
- Modify: `main.py` (add the Frame group after the Font group, ~line 1672; wire `FrameGroupController`; add `_frame_group_targets` + context update)
- Modify: `firepro3d/frame_group.py` (load the icons onto the buttons)

- [ ] **Step 1: Author the 4 SVGs (mockup-gated)**

Create each icon as a two-token, loader-rendered SVG per `icon-style-guide.md`, matched to the 2D-geometry 40-unit icon metrics (project memory `2d-geometry-icons-40unit-legacy`). Use the mockup paths as the geometry source:
- `text_border.svg` — a rounded-less rectangle outline.
- `corner_square.svg` — an L with a sharp right-angle (`M4 2 L4 12 L14 12` at icon scale).
- `corner_fillet.svg` — an L with a quarter-arc corner.
- `corner_chamfer.svg` — an L with a 45° cut corner.

Render each through the loader at 54/27 px, light+dark, and gate with the user before wiring (per the icon authoring convention). Save the harness HTML under `docs/mockups/` if one is produced.

- [ ] **Step 2: Load the icons onto the Frame buttons**

In `firepro3d/frame_group.py` `_build_widgets`, replace each button's `setText(...)` with an icon. Import the app icon loader used elsewhere (match `font_group.py`/`main.py`'s `_I(...)` pattern — thread an icon-loader callable into the controller ctor to avoid a hard import, mirroring how `FontGroupController` stays loader-free):

```python
    def __init__(self, get_targets, icon_loader=None, parent=None):
        ...
        self._icon = icon_loader          # callable(name) -> QIcon, or None
```

For the border button and each corner button, when `self._icon` is set: `b.setIcon(self._icon("text_border.svg"))` etc., and drop the placeholder text.

- [ ] **Step 3: Wire the Frame group into the Draft tab**

In `main.py`, after the Font group block (~line 1672), add:

```python
        # --- Frame (text box border) ---
        from firepro3d.frame_group import FrameGroupController
        g_frame = draft_page.add_group("Frame")
        self.frame_group = FrameGroupController(
            get_targets=self._font_group_targets,   # same targets as the Text group
            icon_loader=_I, parent=self)
        g_frame.add_widget(self.frame_group.container)
        self.frame_group.set_enabled(False)
```

- [ ] **Step 4: Keep the Frame group in sync with selection**

In `main.py`, in `_update_font_group_context` (~line 4378), after the font-group sync, add:

```python
        fr = getattr(self, "frame_group", None)
        if fr is not None:
            targets = self._font_group_targets()
            fr.set_enabled(bool(targets))
            fr.sync()
```

- [ ] **Step 5: Launch-smoke (live — headless can't see this)**

Run: `python main.py`
Verify: Draft tab shows **Text** and **Frame** groups; selecting a sheet-text (and a model text) enables the Frame group; toggling Border draws/removes the box live; corner radio + line-type + weight update the live render; undo reverts each in one step. (Live-render classes dodge headless — `project_live_render_bugs_dodge_headless`.)

- [ ] **Step 6: Full-suite regression + commit**

Run: `python -m pytest tests/test_text_frame.py tests/test_font_select.py tests/test_frame_group.py -q > _t.txt 2>&1; echo EXIT=$?`
Expected: PASS.

```bash
git add firepro3d/graphics/Ribbon/*.svg firepro3d/frame_group.py main.py
git commit -m "feat(text): author Frame icons + wire Frame ribbon group"
```

---

## Self-Review Notes (author checklist — done)

- **Spec coverage:** data fields (T1) · rendering + named weight + corner + line-type (T2) · undo-routed commits + panel rows (T3) · FontSelect TrueType+seam+preview+recents+type-ahead+signal (T4/T5) · Frame group Border+3-way corner+stacked combos (T6) · 4 icons + vertical-label ribbon wiring (T7) · always-wrap (unchanged — no wrap control added). Paper-export weight-plot assertion → covered by the live smoke + the render pen mapping (a dedicated export test may be added if the render test proves insufficient at plot scale).
- **Type consistency:** keys `Border` / `Border Weight` / `Line Type` / `Corner` identical across `set_property`, `_text_panel_change`, panel dicts, and `FrameGroupController`. `ROLE_FAMILY`, `fontChanged`, `set_current_family`, `current_family`, `recent_families`, `commit_current` consistent across FontSelect tasks.
- **No separate frame color:** the pen reads `data.color` (T2).
- **Divergence D4 (always-wrap):** no wrap control is added; the existing wrap behavior is untouched by this plan. If placement ever emits `wrap_width_mm == 0`, address it as a separate follow-up (not in scope here).
