# Text Annotation Panel + Fill Model — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the property panel the editing surface for annotation text (model / Block-Editor `TextItem`): a grouped form (Text / Format / Frame / Fill) with new render types, and evolve `opaque_bg` into a real fill (colour + 0–100% opacity).

**Architecture:** The panel wiring already exists and is generic (`PropertyManager._show_properties_inner` renders any item's `get_properties()`; `_apply_property` → `set_property` per target + `sceneModified` — so model-scene edits inherit the same apply-back/undo as geom2d panel edits). Work is: (1) fill data+render+migration, (2) new `property_manager` render types, (3) grouped `TextItem.get_properties()`.

**Branch:** `feat/text-annotation-frame` (continues). **Governing spec:** `docs/specs/text-annotation-system.md` (Property-panel section + Fill fields). **Mock:** `docs/mockups/property-panel-text.html`.

**Watch:** `opaque_bg` has 12 call-sites (grep) across `text_item.py` + `paper_space.py` — migrate all. Fill render dodges headless only for live edit; use the pixel-differential render test pattern from Phase 1. New panel widgets must be **widget-driven** in tests (not slot-level).

---

## Task 8: Fill model (data + render + migration)

Replace `opaque_bg: bool` with `fill_color: str` + `fill_opacity: float`, migrating legacy data, and fill the box with colour+alpha in `paint`.

**Files:** Modify `firepro3d/text_item.py`, `firepro3d/paper_space.py`. Test: `tests/test_text_frame.py` (append).

- [ ] **Step 1: Failing tests** — append to `tests/test_text_frame.py`:
```python
def test_fill_fields_default_none():
    d = TextAnnotationData()
    assert d.fill_color == "" and d.fill_opacity == 100.0
    assert not hasattr(d, "opaque_bg")


def test_fill_roundtrip():
    d = TextAnnotationData(fill_color="#d19a26", fill_opacity=35.0)
    d2 = TextAnnotationData.from_dict(d.to_dict())
    assert d2.fill_color == "#d19a26" and d2.fill_opacity == 35.0
    assert "opaque_bg" not in d.to_dict()


def test_opaque_bg_migration():
    on = TextAnnotationData.from_dict({"type": "text", "opaque_bg": True})
    off = TextAnnotationData.from_dict({"type": "text", "opaque_bg": False})
    assert on.fill_color == "#ffffff" and on.fill_opacity == 100.0
    assert off.fill_color == ""


def test_fill_renders_pixels(qapp):
    # reuse _render_nonwhite_count from the Phase-1 frame tests
    item = TextItem(TextAnnotationData(text="AB", height_mm=4.0))
    off = _render_nonwhite_count(item)
    item.set_property("Fill Color", "#c0392b")
    on = _render_nonwhite_count(item)
    assert on > off + 50    # a red fill adds many non-white pixels
```

- [ ] **Step 2: Run → FAIL**: `python -m pytest tests/test_text_frame.py -k "fill or opaque or migration" -q > _t.txt 2>&1; echo EXIT=$?`

- [ ] **Step 3: Data fields** — in `firepro3d/text_item.py` `TextAnnotationData`, REPLACE `opaque_bg: bool = False` with:
```python
    fill_color: str = ""                          # box fill hex; "" = no fill
    fill_opacity: float = 100.0                   # fill alpha percentage 0-100
```
Update the docstring `Fields` block (replace the `opaque_bg` entry with `fill_color`/`fill_opacity`).

- [ ] **Step 4: to_dict / from_dict** — in `to_dict`, replace `"opaque_bg": self.opaque_bg,` with:
```python
            "fill_color": self.fill_color, "fill_opacity": self.fill_opacity,
```
In `from_dict`, replace `opaque_bg=bool(d.get("opaque_bg", False)),` with a migration:
```python
            fill_color=(d.get("fill_color")
                        if d.get("fill_color") is not None
                        else ("#ffffff" if bool(d.get("opaque_bg", False)) else "")),
            fill_opacity=float(d.get("fill_opacity", 100.0)),
```

- [ ] **Step 5: paint** — in `TextItem.paint`, replace:
```python
        if self._data.opaque_bg:
            painter.fillRect(box, QColor("#ffffff"))
```
with:
```python
        if self._data.fill_color:
            c = QColor(self._data.fill_color)
            c.setAlphaF(max(0.0, min(1.0, self._data.fill_opacity / 100.0)))
            painter.fillRect(box, c)
```
Update the paint docstring line and the `get_closed_path` comment (mention `fill_color`, not `opaque_bg`).

- [ ] **Step 6: model set_property + get_properties** — in `set_property` (model branch), replace the `opaque_bg` branch with:
```python
        elif key == "Fill Color":
            self._data.fill_color = str(value)
        elif key == "Fill Opacity":
            self._data.fill_opacity = float(value)
```
In `get_properties` (model branch), replace the `"Opaque Background"` row with:
```python
            "Fill Color":   {"type": "color", "value": self._data.fill_color or "#ffffff"},
            "Fill Opacity": {"type": "percent", "value": float(self._data.fill_opacity)},
```
(The `percent` type is added in Task 9; until then the panel falls back to string — acceptable, Task 10 finalizes ordering.)

- [ ] **Step 7: paper_space sites** — update all `opaque_bg` references in `firepro3d/paper_space.py`:
  - `_text_panel_properties`: replace the `"Opaque Background"` row with `"Fill Color": {"type": "color", "value": data.fill_color or "#ffffff"}` and `"Fill Opacity": {"type": "percent", "value": float(data.fill_opacity)}`.
  - `_text_panel_change`: replace the `opaque_bg` branch with:
    ```python
    elif key == "Fill Color":
        field, new = "fill_color", str(value)
    elif key == "Fill Opacity":
        field, new = "fill_opacity", float(value)
    ```
  - `_TEMPLATE_FIELDS` tuple: replace `"opaque_bg"` with `"fill_color", "fill_opacity"`.
  - The load migration (`if "opaque_bg" in raw:` block): change to set `data.fill_color = "#ffffff" if _b(raw["opaque_bg"]) else ""` (keep reading legacy). Also read `fill_color`/`fill_opacity` if present.
  - The `data.opaque_bg = t.opaque_bg` copy (~line 3546): change to `data.fill_color = t.fill_color; data.fill_opacity = t.fill_opacity`.

- [ ] **Step 8: Run → PASS + no leftover refs**: `python -m pytest tests/test_text_frame.py -q > _t.txt 2>&1; echo EXIT=$?` then `grep -rn "opaque_bg" firepro3d/` — expect **zero** hits. Also `python -m pytest tests/ -k "text or paper" -q > _t2.txt 2>&1; echo EXIT=$?` (report failures; `test_default_template_paints` is a known pre-existing headless failure).

- [ ] **Step 9: Prove the fill guard RED** — comment the Step-5 fill block, run `-k fill_renders`, confirm FAIL, restore.

- [ ] **Step 10: Commit** — `git add firepro3d/text_item.py firepro3d/paper_space.py tests/test_text_frame.py` then `git commit -m "feat(text): evolve opaque_bg into fill_color + fill_opacity"`. Delete `_t.txt`/`_t2.txt`.

---

## Task 9: New property_manager render types

Add the panel render types the grouped annotation form needs: `icon_enum` (segmented icon buttons), a bool **button group**, `number` (bare integer), and `percent` (0–100 slider).

**Files:** Modify `firepro3d/property_manager.py`. Test: `tests/test_property_types.py` (create).

- [ ] **Step 1: Failing tests** — create `tests/test_property_types.py`:
```python
from PyQt6.QtWidgets import QComboBox, QSlider, QLineEdit, QAbstractButton
from firepro3d.property_manager import PropertyManager


class _Item:
    """Minimal target exposing get_properties/set_property for panel tests."""
    def __init__(self, props):
        self._p = props; self.applied = {}
    def get_properties(self): return self._p
    def set_property(self, k, v): self.applied[k] = v; self._p[k]["value"] = v
    def scene(self): return None


def _find(pm, cls):
    return pm._form.parentWidget().findChildren(cls)


def test_icon_enum_renders_buttons_and_commits(qapp):
    pm = PropertyManager()
    it = _Item({"Corner": {"type": "icon_enum", "value": "square",
                           "options": [("square", "corner_square.svg"),
                                       ("round", "corner_fillet.svg"),
                                       ("chamfer", "corner_chamfer.svg")]}})
    pm.show_properties(it)
    btns = [b for b in _find(pm, QAbstractButton) if b.property("icon_enum_val")]
    assert len(btns) == 3
    chamfer = next(b for b in btns if b.property("icon_enum_val") == "chamfer")
    chamfer.click()
    assert it.applied["Corner"] == "chamfer"


def test_number_type_bare_value(qapp):
    pm = PropertyManager()
    it = _Item({"Height": {"type": "number", "value": 48}})
    pm.show_properties(it)
    edits = [e for e in _find(pm, QLineEdit) if e.property("number_key") == "Height"]
    assert edits and edits[0].text() == "48"
    edits[0].setText("60"); edits[0].editingFinished.emit()
    assert it.applied["Height"] == 60


def test_percent_slider_commits(qapp):
    pm = PropertyManager()
    it = _Item({"Fill Opacity": {"type": "percent", "value": 35.0}})
    pm.show_properties(it)
    sliders = _find(pm, QSlider)
    assert sliders and sliders[0].value() == 35
    sliders[0].setValue(80)
    assert it.applied["Fill Opacity"] == 80
```

- [ ] **Step 2: Run → FAIL**: `python -m pytest tests/test_property_types.py -q > _t.txt 2>&1; echo EXIT=$?` (types unknown → rows skipped → asserts fail).

- [ ] **Step 3: Implement the render types** — in `property_manager.py` `_show_properties_inner`, add branches alongside the existing `enum`/`toggle` ones (before the final `string` fallback). Import `QSlider`, `QAbstractButton`, `QHBoxLayout`, `QWidget`, `QButtonGroup`, `QToolButton` as needed; reuse the icon loader `themed_icon` from `firepro3d.icons`.

```python
            # ── icon_enum (segmented icon buttons, exactly-one-active) ──────
            elif prop_type == "icon_enum":
                from .icons import themed_icon
                from . import theme as _th
                cont = QWidget(); lay = QHBoxLayout(cont)
                lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
                grp = QButtonGroup(cont); grp.setExclusive(True)
                for val, icon_name in meta.get("options", []):
                    b = QToolButton(); b.setCheckable(True)
                    b.setIcon(themed_icon(icon_name, _th.detect_name()))
                    b.setToolTip(str(val).capitalize())
                    b.setProperty("icon_enum_val", val)
                    b.setChecked(val == meta.get("value"))
                    b.clicked.connect(lambda _c, k=key, v=val: self._apply_property(k, v))
                    grp.addButton(b); lay.addWidget(b)
                lay.addStretch(1)
                widget = cont

            # ── bool_group (several bool keys as pressable buttons) ────────
            elif prop_type == "bool_group":
                cont = QWidget(); lay = QHBoxLayout(cont)
                lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
                for sub_key, label in meta.get("keys", []):
                    b = QToolButton(); b.setCheckable(True); b.setText(label)
                    b.setChecked(bool(meta.get("values", {}).get(sub_key)))
                    b.setToolTip(label)
                    b.clicked.connect(lambda ch, k=sub_key: self._apply_property(k, bool(ch)))
                    lay.addWidget(b)
                lay.addStretch(1)
                widget = cont

            # ── number (bare integer, no unit) ─────────────────────────────
            elif prop_type == "number":
                edit = QLineEdit(str(int(meta.get("value", 0))))
                edit.setProperty("number_key", key)
                edit.editingFinished.connect(
                    lambda k=key, e=edit: self._apply_property(k, int(float(e.text() or 0))))
                widget = edit

            # ── percent (0-100 slider with % readout) ──────────────────────
            elif prop_type == "percent":
                cont = QWidget(); lay = QHBoxLayout(cont)
                lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
                sl = QSlider(Qt.Orientation.Horizontal)
                sl.setRange(0, 100); sl.setValue(int(meta.get("value", 100)))
                lbl = QLabel(f"{sl.value()}%")
                sl.valueChanged.connect(lambda v, l=lbl: l.setText(f"{v}%"))
                sl.valueChanged.connect(lambda v, k=key: self._apply_property(k, v))
                lay.addWidget(sl); lay.addWidget(lbl)
                widget = cont
```
If `theme.detect_name()` does not exist, use the existing theme→name accessor (check `theme.py`; e.g. `"dark" if theme.detect() is theme.DARK else "light"`), matching how `themed_icon(name, theme_str)` is called elsewhere.

- [ ] **Step 4: Run → PASS**: `python -m pytest tests/test_property_types.py -q > _t.txt 2>&1; echo EXIT=$?`. Expected: 3 passed. Fix the `findChildren`/property hooks in tests only if the widget structure differs (keep the observable-commit assertions).

- [ ] **Step 5: Regression** — `python -m pytest tests/ -k "panel or propert or geo2d or floor" -q > _t2.txt 2>&1; echo EXIT=$?` (existing panel tests must stay green).

- [ ] **Step 6: Commit** — `git add firepro3d/property_manager.py tests/test_property_types.py` then `git commit -m "feat(panel): add icon_enum/bool_group/number/percent render types"`.

---

## Task 10: Grouped annotation-text panel form

Rebuild `TextItem.get_properties()` (model branch) into the grouped form using the new types.

**Files:** Modify `firepro3d/text_item.py`. Test: `tests/test_text_frame.py` (append).

- [ ] **Step 1: Failing test** — append:
```python
def test_annotation_panel_grouped_form(qapp):
    item = TextItem(TextAnnotationData(text="A", border=True, fill_color="#d19a26"))
    p = item.get_properties()
    keys = list(p.keys())
    # section headers present and ordered
    assert keys.index("Text") < keys.index("Format") < keys.index("Frame") < keys.index("Fill")
    assert p["Text"]["type"] == "header" and p["Format"]["type"] == "header"
    # Font + Height live under Format; Height is a bare number
    assert keys.index("Font") > keys.index("Format")
    assert p["Height"]["type"] == "number"
    # Corner is an icon_enum with the three frame icons
    assert p["Corner"]["type"] == "icon_enum"
    assert [o[0] for o in p["Corner"]["options"]] == ["square", "round", "chamfer"]
    # B/I/U as a bool_group; colours + opacity present
    assert p["Style"]["type"] == "bool_group"
    assert p["Font Color"]["type"] == "color"
    assert p["Fill Color"]["type"] == "color"
    assert p["Fill Opacity"]["type"] == "percent"
```

- [ ] **Step 2: Run → FAIL**: `python -m pytest tests/test_text_frame.py -k grouped_form -q > _t.txt 2>&1; echo EXIT=$?`

- [ ] **Step 3: Rebuild the model `get_properties()` branch** — replace the model-branch `props` dict (the non-paper path) with the grouped form (keep the geom2d merge tail, still stripping Level rows):
```python
        d = self._data
        props = {
            "Text":    {"type": "header", "value": "Text"},
            "Content": {"type": "string", "value": d.text},
            "Format":  {"type": "header", "value": "Format"},
            "Font":    {"type": "font", "value": d.font_family or "Arial"},
            "Height":  {"type": "number", "value": int(round(self._font_px()))},
            "Style":   {"type": "bool_group",
                        "keys": [("Bold", "B"), ("Italic", "I"), ("Underline", "U")],
                        "values": {"Bold": d.bold, "Italic": d.italic, "Underline": d.underline}},
            "Alignment": {"type": "enum", "options": ["L", "C", "R"], "value": d.align},
            "Font Color": {"type": "color", "value": d.color or "#000000"},
            "Frame":   {"type": "header", "value": "Frame"},
            "Border":  {"type": "toggle", "value": bool(d.border)},
            "Corner":  {"type": "icon_enum", "value": d.border_corner,
                        "options": [("square", "corner_square.svg"),
                                    ("round", "corner_fillet.svg"),
                                    ("chamfer", "corner_chamfer.svg")]},
            "Line Type": {"type": "enum", "options": ["solid", "dashed", "dotted", "dashdot"],
                          "value": d.border_line_type},
            "Border Weight": {"type": "enum",
                              "options": ["Very Light", "Light", "Medium", "Heavy", "Very Heavy"],
                              "value": d.border_weight},
            "Fill":    {"type": "header", "value": "Fill"},
            "Fill Color":   {"type": "color", "value": d.fill_color or "#ffffff"},
            "Fill Opacity": {"type": "percent", "value": float(d.fill_opacity)},
        }
        geom2d = self._geom2d_properties()
        for key in ("Level", "Level Offset", "Elevation"):
            geom2d.pop(key, None)
        props.update(geom2d)
        return props
```

- [ ] **Step 4: Add `set_property` keys `Content` + `Font Color` + `_font_px()` helper** — in `set_property` (model branch) add:
```python
        elif key == "Content":
            self._data.text = str(value)
            self.setPlainText(self._data.text)
        elif key == "Font Color":
            self._data.color = str(value)
```
(Keep the existing `"Text"` key handler too for back-compat.) Add a helper:
```python
    def _font_px(self) -> float:
        """Panel Height as a bare pixel number (cap height in local px units)."""
        from .constants import TEXT_METRIC_REF_PX
        from PyQt6.QtGui import QFontMetricsF
        cap = QFontMetricsF(self.font()).capHeight()
        return cap if cap > 0 else self._data.height_mm
```
And handle Height (number) commits — the panel sends an int px; map it back to `height_mm`. In `set_property`, update the `"Height"` branch (model) so an int px value sets the font: if the value looks like a bare number (from the panel `number` type), set `self._data.height_mm` via the inverse of `_font_px` (simplest: treat the number as the new cap px and set `height_mm` so the rendered cap matches — reuse the existing height→font path by assigning `self._data.height_mm = float(value)` in scene-mm and letting `_apply_format` rebuild, since model scene-mm cap == height_mm). Confirm by test that editing Height changes the rendered size.

- [ ] **Step 5: Run → PASS**: `python -m pytest tests/test_text_frame.py -q > _t.txt 2>&1; echo EXIT=$?`

- [ ] **Step 6: Widget-level integration** — add one test driving the real panel end-to-end:
```python
def test_panel_renders_textitem_and_commits_border(qapp):
    from firepro3d.property_manager import PropertyManager
    item = TextItem(TextAnnotationData(text="A"))
    pm = PropertyManager()
    pm.show_properties(item)
    # the grouped form built without error and Border toggled through set_property
    item.set_property("Border", True)
    assert item._data.border is True
```
Run the file; expect green.

- [ ] **Step 7: Commit** — `git add firepro3d/text_item.py tests/test_text_frame.py` then `git commit -m "feat(text): grouped annotation-text property panel form"`.

---

## Self-Review Notes (author checklist)

- **Spec coverage:** fill data+render+migration (T8) · icon_enum/bool_group/number/percent render types (T9) · grouped Text/Format/Frame/Fill form with Font+Height in Format, bare Height, icon Corner, B/I/U buttons, font+fill colour, opacity (T10). Ribbon-stays-paper (D6) needs no code.
- **Type consistency:** keys `Fill Color`/`Fill Opacity`/`Corner`/`Content`/`Font Color`/`Border` identical across `set_property`, `_text_panel_change`, `get_properties`, and the panel render types. `icon_enum` option shape is `(value, icon_name)` in both T9 and T10.
- **Apply-back/undo:** inherits the existing geom2d panel path (`_apply_property` → `set_property` + `sceneModified`); no new undo code. Verify the block-editor scene snapshots on `sceneModified` the same way geom2d edits do (it does — same signal).
- **Height semantics:** the panel `number` is a bare px cap height; confirm the round-trip (edit → render size changes) in T10 Step 4. If the px↔mm mapping proves lossy, keep `height_mm` authoritative and show `round()` — a 1px display rounding is acceptable (no unit shown).
