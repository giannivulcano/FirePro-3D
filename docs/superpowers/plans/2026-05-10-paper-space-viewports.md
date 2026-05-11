# Paper Space Viewports & Title Block — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-viewport paper space with drag-from-browser placement, scale control, title block field overlay, and round-trip serialization.

**Architecture:** Option C (full separation) — `Sheet`/`SheetViewData` data classes own state, `SheetViewport` (`QGraphicsObject`) handles rendering with pixmap cache + resize grips, `ViewResolver` bridges source views to scenes, `PaperScene` composes viewports, `ModelBrowser` provides drag source. All new classes in `paper_space.py`.

**Tech Stack:** Python 3.x, PyQt6 (QGraphicsObject, QMimeData, drag-drop), ezdxf (existing DXF parsing), dataclasses.

**Design spec:** `docs/superpowers/specs/2026-05-10-paper-space-viewports-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `firepro3d/paper_space.py` | Modify | Add `SheetViewData`, `Sheet`, `ViewResolver`, `SheetViewport`, `TitleBlockFieldOverlay`, `SheetViewPropertiesDialog`, scale helpers. Refactor `PaperScene` and `PaperSpaceWidget`. |
| `firepro3d/model_browser.py` | Modify | Add "Views" group with drag support, italic placed indicator. |
| `firepro3d/scene_io.py` | Modify | Add `"sheets"` key to save/load payload. |
| `firepro3d/main.py` | Modify | Create `ViewResolver`, `Sheet`, wire new `PaperScene` args, connect "Go to View" navigation. |
| `tests/test_paper_space.py` | Modify | Add tests for scale helpers, data model serialization, title block auto-population, dirty flag, dangling refs. |

---

### Task 1: Scale Helper Functions

Pure functions with no dependencies — foundation for everything else.

**Files:**
- Modify: `firepro3d/paper_space.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Write failing tests for scale_to_float**

Add to `tests/test_paper_space.py`:

```python
class TestScaleHelpers:
    """Scale string ↔ float conversion."""

    def test_metric_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        assert scale_to_float("1:100") == pytest.approx(0.01)
        assert scale_to_float("1:50") == pytest.approx(0.02)
        assert scale_to_float("1:1") == pytest.approx(1.0)
        assert scale_to_float("1:200") == pytest.approx(0.005)

    def test_imperial_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        # 1/4" = 1'-0" means 0.25 inch represents 12 inches → ratio 0.25/12
        assert scale_to_float('1/4"=1\'-0"') == pytest.approx(1 / 48)
        assert scale_to_float('1/8"=1\'-0"') == pytest.approx(1 / 96)
        assert scale_to_float('1"=1\'-0"') == pytest.approx(1 / 12)
        assert scale_to_float('3/8"=1\'-0"') == pytest.approx(3 / 96)

    def test_custom_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        assert scale_to_float("1:125") == pytest.approx(1 / 125)

    def test_invalid_scale_to_float(self):
        from firepro3d.paper_space import scale_to_float
        with pytest.raises(ValueError):
            scale_to_float("not a scale")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_space.py::TestScaleHelpers -v`
Expected: FAIL — `scale_to_float` not found.

- [ ] **Step 3: Implement scale_to_float**

Add to `firepro3d/paper_space.py` after the imports and constants:

```python
import re

# ─────────────────────────────────────────────────────────────────────────────
# Scale presets and conversion
# ─────────────────────────────────────────────────────────────────────────────

SCALE_PRESETS: list[tuple[str, float]] = [
    # Metric
    ("1:200", 1 / 200),
    ("1:100", 1 / 100),
    ("1:75",  1 / 75),
    ("1:50",  1 / 50),
    ("1:25",  1 / 25),
    ("1:20",  1 / 20),
    ("1:10",  1 / 10),
    ("1:5",   1 / 5),
    ("1:1",   1.0),
    # Imperial (inches per foot)
    ('1/8"=1\'-0"',   1 / 96),
    ('3/16"=1\'-0"',  3 / 192),
    ('1/4"=1\'-0"',   1 / 48),
    ('3/8"=1\'-0"',   3 / 96),
    ('1/2"=1\'-0"',   1 / 24),
    ('3/4"=1\'-0"',   3 / 36),
    ('1"=1\'-0"',     1 / 12),
    ('1-1/2"=1\'-0"', 1.5 / 12),
    ('3"=1\'-0"',     3 / 12),
]

_PRESET_MAP: dict[str, float] = {label: ratio for label, ratio in SCALE_PRESETS}

# Regex patterns for scale string parsing
_RE_METRIC = re.compile(r"^1\s*:\s*(\d+(?:\.\d+)?)$")
_RE_IMPERIAL = re.compile(
    r'^(\d+(?:-\d+/\d+|\.\d+)?(?:/\d+)?)\s*"\s*=\s*1\'-0"$'
)


def _parse_imperial_inches(s: str) -> float:
    """Parse imperial inch value like '1/4', '1-1/2', '3'."""
    if "-" in s:
        whole, frac = s.split("-", 1)
        return float(whole) + _parse_imperial_inches(frac)
    if "/" in s:
        num, den = s.split("/", 1)
        return float(num) / float(den)
    return float(s)


def scale_to_float(s: str) -> float:
    """Convert a scale string to a float ratio.

    Accepts metric ('1:100'), imperial ('1/4\"=1\\'-0\"'), or preset names.
    Raises ValueError for unparseable strings.
    """
    s = s.strip()
    # Check preset map first
    if s in _PRESET_MAP:
        return _PRESET_MAP[s]
    # Metric: 1:N
    m = _RE_METRIC.match(s)
    if m:
        return 1.0 / float(m.group(1))
    # Imperial: X"=1'-0"
    m = _RE_IMPERIAL.match(s)
    if m:
        inches = _parse_imperial_inches(m.group(1))
        return inches / 12.0
    raise ValueError(f"Cannot parse scale string: {s!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paper_space.py::TestScaleHelpers -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for float_to_scale_str**

Add to `TestScaleHelpers`:

```python
    def test_float_to_known_preset(self):
        from firepro3d.paper_space import float_to_scale_str
        assert float_to_scale_str(0.01) == "1:100"
        assert float_to_scale_str(0.02) == "1:50"
        assert float_to_scale_str(1.0) == "1:1"

    def test_float_to_imperial_preset(self):
        from firepro3d.paper_space import float_to_scale_str
        assert float_to_scale_str(1 / 48) == '1/4"=1\'-0"'

    def test_float_to_custom(self):
        from firepro3d.paper_space import float_to_scale_str
        assert float_to_scale_str(1 / 125) == "1:125"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_paper_space.py::TestScaleHelpers::test_float_to_known_preset -v`
Expected: FAIL — `float_to_scale_str` not found.

- [ ] **Step 7: Implement float_to_scale_str**

Add below `scale_to_float` in `paper_space.py`:

```python
def float_to_scale_str(ratio: float) -> str:
    """Convert a float ratio to the best matching scale string.

    Matches to the nearest preset within 0.1% tolerance.
    Falls back to '1:N' format for unmatched ratios.
    """
    for label, preset_ratio in SCALE_PRESETS:
        if abs(ratio - preset_ratio) < preset_ratio * 0.001:
            return label
    # Fallback: 1:N
    n = round(1.0 / ratio)
    return f"1:{n}"
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_paper_space.py::TestScaleHelpers -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add firepro3d/paper_space.py tests/test_paper_space.py
git commit -m "feat(paper-space): add scale string ↔ float conversion helpers"
```

---

### Task 2: SheetViewData and Sheet Data Model

Pure dataclasses with serialization — no Qt dependency beyond what already exists.

**Files:**
- Modify: `firepro3d/paper_space.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Write failing tests for SheetViewData serialization**

Add to `tests/test_paper_space.py`:

```python
class TestSheetViewData:
    """SheetViewData dataclass and serialization."""

    def test_round_trip(self):
        from firepro3d.paper_space import SheetViewData
        svd = SheetViewData(
            source_view_type="plan",
            source_view_name="Level 1",
            title="Level 1 - Sprinkler Plan",
            scale=0.01,
            x=25.0, y=25.0, w=400.0, h=300.0,
        )
        d = svd.to_dict()
        restored = SheetViewData.from_dict(d)
        assert restored.source_view_type == "plan"
        assert restored.source_view_name == "Level 1"
        assert restored.title == "Level 1 - Sprinkler Plan"
        assert restored.scale == pytest.approx(0.01)
        assert restored.x == pytest.approx(25.0)
        assert restored.w == pytest.approx(400.0)

    def test_to_dict_keys(self):
        from firepro3d.paper_space import SheetViewData
        svd = SheetViewData("plan", "Level 1", "Level 1", 0.01, 0, 0, 100, 100)
        d = svd.to_dict()
        assert set(d.keys()) == {
            "source_view_type", "source_view_name", "title",
            "scale", "x", "y", "w", "h",
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_space.py::TestSheetViewData -v`
Expected: FAIL — `SheetViewData` not found.

- [ ] **Step 3: Implement SheetViewData**

Add to `paper_space.py` after the scale helpers, before the title block classes:

```python
from dataclasses import dataclass, field

@dataclass
class SheetViewData:
    """Data for one viewport placed on a sheet."""

    source_view_type: str
    source_view_name: str
    title: str
    scale: float
    x: float
    y: float
    w: float
    h: float

    def to_dict(self) -> dict:
        return {
            "source_view_type": self.source_view_type,
            "source_view_name": self.source_view_name,
            "title": self.title,
            "scale": self.scale,
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SheetViewData":
        return cls(
            source_view_type=d["source_view_type"],
            source_view_name=d["source_view_name"],
            title=d["title"],
            scale=d["scale"],
            x=d["x"], y=d["y"],
            w=d["w"], h=d["h"],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paper_space.py::TestSheetViewData -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for Sheet serialization**

Add to `tests/test_paper_space.py`:

```python
class TestSheet:
    """Sheet dataclass and serialization."""

    def _make_sheet(self):
        from firepro3d.paper_space import Sheet, SheetViewData
        return Sheet(
            number="FP-1.0",
            name="Fire Suppression Layout",
            paper_size="ANSI D",
            title_block_fields={
                "Company": "Test Corp",
                "Project": "Test Project",
                "Title": "Level 1 Plan",
                "Scale": "1:100",
                "Drawing No": "FP-001",
                "Rev": "A",
                "Date": "10 May 2026",
                "Drawn By": "GV",
                "Checked By": "",
            },
            sheet_views=[
                SheetViewData("plan", "Level 1", "Level 1", 0.01,
                              25, 25, 400, 300),
            ],
        )

    def test_round_trip(self):
        from firepro3d.paper_space import Sheet
        sheet = self._make_sheet()
        d = sheet.to_dict()
        restored = Sheet.from_dict(d)
        assert restored.number == "FP-1.0"
        assert restored.name == "Fire Suppression Layout"
        assert restored.paper_size == "ANSI D"
        assert restored.title_block_fields["Company"] == "Test Corp"
        assert len(restored.sheet_views) == 1
        assert restored.sheet_views[0].source_view_name == "Level 1"

    def test_empty_sheet_views(self):
        from firepro3d.paper_space import Sheet
        sheet = Sheet("FP-1", "Test", "ANSI D", {}, [])
        d = sheet.to_dict()
        restored = Sheet.from_dict(d)
        assert restored.sheet_views == []

    def test_default_fields(self):
        from firepro3d.paper_space import Sheet, DEFAULT_TITLE_BLOCK_FIELDS
        sheet = Sheet.create_default()
        assert sheet.paper_size == "ANSI D"
        assert "Company" in sheet.title_block_fields
        assert sheet.sheet_views == []
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_paper_space.py::TestSheet -v`
Expected: FAIL — `Sheet` not found.

- [ ] **Step 7: Implement Sheet**

Add below `SheetViewData` in `paper_space.py`:

```python
DEFAULT_TITLE_BLOCK_FIELDS: dict[str, str] = {
    "Company": "Celerity Engineering Limited",
    "Project": "",
    "Title": "Fire Suppression Layout",
    "Scale": "1:100",
    "Drawing No": "FP-001",
    "Rev": "A",
    "Date": datetime.date.today().strftime("%d %b %Y"),
    "Drawn By": "",
    "Checked By": "",
}


@dataclass
class Sheet:
    """Data model for one paper sheet."""

    number: str
    name: str
    paper_size: str
    title_block_fields: dict[str, str]
    sheet_views: list[SheetViewData]

    @classmethod
    def create_default(cls) -> "Sheet":
        return cls(
            number="FP-1.0",
            name="Fire Suppression Layout",
            paper_size="ANSI D",
            title_block_fields=dict(DEFAULT_TITLE_BLOCK_FIELDS),
            sheet_views=[],
        )

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "paper_size": self.paper_size,
            "title_block_fields": dict(self.title_block_fields),
            "sheet_views": [sv.to_dict() for sv in self.sheet_views],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Sheet":
        return cls(
            number=d["number"],
            name=d["name"],
            paper_size=d["paper_size"],
            title_block_fields=d.get("title_block_fields",
                                     dict(DEFAULT_TITLE_BLOCK_FIELDS)),
            sheet_views=[SheetViewData.from_dict(sv)
                         for sv in d.get("sheet_views", [])],
        )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_paper_space.py::TestSheet -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add firepro3d/paper_space.py tests/test_paper_space.py
git commit -m "feat(paper-space): add Sheet and SheetViewData data model with serialization"
```

---

### Task 3: ViewResolver

Bridges source view managers to `(scene, source_rect)` pairs.

**Files:**
- Modify: `firepro3d/paper_space.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Write failing tests for ViewResolver**

Add to `tests/test_paper_space.py`:

```python
from unittest.mock import MagicMock, PropertyMock
from PyQt6.QtCore import QRectF


class TestViewResolver:
    """ViewResolver resolves view type + name to scene + rect."""

    def _make_resolver(self):
        from firepro3d.paper_space import ViewResolver

        model_scene = QGraphicsScene()
        model_scene.addRect(0, 0, 10000, 8000)  # model content

        plan_mgr = MagicMock()
        plan_view = MagicMock()
        plan_view.view_height = 3000.0
        plan_view.view_depth = 0.0
        plan_mgr._views = {"Plan: Level 1": plan_view}

        detail_mgr = MagicMock()
        detail_mgr.detail_names = ["Detail 1"]
        marker = MagicMock()
        marker.crop_rect = QRectF(100, 100, 2000, 1500)
        detail_mgr.get_marker.return_value = marker

        elev_mgr = MagicMock()
        elev_scene = QGraphicsScene()
        elev_scene.addRect(0, 0, 5000, 3000)
        elev_mgr.get_scene.return_value = elev_scene
        elev_mgr.open_directions = ["north", "east"]

        return ViewResolver(model_scene, plan_mgr, detail_mgr, elev_mgr)

    def test_available_views(self):
        resolver = self._make_resolver()
        views = resolver.available_views()
        assert "Floor Plans" in views
        assert "Plan: Level 1" in views["Floor Plans"]
        assert "Details" in views
        assert "Detail 1" in views["Details"]
        assert "Elevations" in views

    def test_resolve_plan(self):
        resolver = self._make_resolver()
        result = resolver.resolve("plan", "Plan: Level 1")
        assert result is not None
        scene, rect = result
        assert scene is not None
        assert not rect.isEmpty()

    def test_resolve_detail(self):
        resolver = self._make_resolver()
        result = resolver.resolve("detail", "Detail 1")
        assert result is not None
        scene, rect = result
        assert rect == QRectF(100, 100, 2000, 1500)

    def test_resolve_elevation(self):
        resolver = self._make_resolver()
        result = resolver.resolve("elevation", "North")
        assert result is not None

    def test_resolve_missing_returns_none(self):
        resolver = self._make_resolver()
        assert resolver.resolve("plan", "Nonexistent") is None
        assert resolver.resolve("detail", "Nonexistent") is None
        assert resolver.resolve("elevation", "Nonexistent") is None
        assert resolver.resolve("unknown_type", "Foo") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_space.py::TestViewResolver -v`
Expected: FAIL — `ViewResolver` not found.

- [ ] **Step 3: Implement ViewResolver**

Add to `paper_space.py` after the `Sheet` class:

```python
class ViewResolver:
    """Resolves source view type + name → (QGraphicsScene, QRectF).

    Single bridge object decoupling SheetViewport from individual view
    managers.
    """

    def __init__(self, model_scene, plan_view_manager,
                 detail_manager, elevation_manager):
        self._scene = model_scene
        self._pvm = plan_view_manager
        self._dm = detail_manager
        self._em = elevation_manager

    def resolve(self, view_type: str, view_name: str
                ) -> "tuple[QGraphicsScene, QRectF] | None":
        """Return (source_scene, source_rect) or None if not found."""
        if view_type == "plan":
            return self._resolve_plan(view_name)
        if view_type == "detail":
            return self._resolve_detail(view_name)
        if view_type == "elevation":
            return self._resolve_elevation(view_name)
        return None

    def _resolve_plan(self, name: str):
        pv = self._pvm.get(name) if hasattr(self._pvm, 'get') else self._pvm._views.get(name)
        if pv is None:
            return None
        # Source rect: itemsBoundingRect of all visible items in the
        # plan view's Z-range.  For now, use the full scene items
        # bounding rect — Z-filtering is a rendering concern handled
        # by the level manager during scene.render().
        rect = self._scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            rect = QRectF(0, 0, 1000, 1000)
        return (self._scene, rect)

    def _resolve_detail(self, name: str):
        marker = self._dm.get_marker(name)
        if marker is None:
            return None
        return (self._scene, marker.crop_rect)

    def _resolve_elevation(self, name: str):
        direction = name.lower()
        scene = self._em.get_scene(direction)
        if scene is None:
            return None
        rect = scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            rect = QRectF(0, 0, 1000, 1000)
        return (scene, rect)

    def available_views(self) -> dict[str, list[str]]:
        """Return available views grouped by type."""
        result: dict[str, list[str]] = {}
        # Floor Plans
        plan_names = list(self._pvm._views.keys())
        if plan_names:
            result["Floor Plans"] = plan_names
        # Details
        detail_names = self._dm.detail_names
        if detail_names:
            result["Details"] = detail_names
        # Elevations — show all four cardinal directions
        directions = ["North", "South", "East", "West"]
        result["Elevations"] = directions
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paper_space.py::TestViewResolver -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add firepro3d/paper_space.py tests/test_paper_space.py
git commit -m "feat(paper-space): add ViewResolver for source view → scene resolution"
```

---

### Task 4: SheetViewport with Pixmap Cache and Resize Grips

The core rendering component. Replaces `PaperViewport`.

**Files:**
- Modify: `firepro3d/paper_space.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Write failing tests for SheetViewport**

Add to `tests/test_paper_space.py`:

```python
class TestSheetViewport:
    """SheetViewport rendering, interaction, and dirty flag."""

    def _make_viewport(self, model_scene):
        from firepro3d.paper_space import SheetViewData, SheetViewport, ViewResolver
        from unittest.mock import MagicMock

        data = SheetViewData("plan", "Level 1", "Level 1", 0.01,
                             50, 50, 400, 300)
        resolver = MagicMock()
        resolver.resolve.return_value = (model_scene,
                                         QRectF(0, 0, 40000, 30000))
        vp = SheetViewport(data, resolver)
        return vp, data, resolver

    def test_rect_matches_data(self, model_scene):
        vp, data, _ = self._make_viewport(model_scene)
        assert vp.boundingRect().width() == pytest.approx(400, abs=20)
        assert vp.boundingRect().height() == pytest.approx(300, abs=20)

    def test_movable_and_selectable(self, model_scene):
        vp, _, _ = self._make_viewport(model_scene)
        flags = vp.flags()
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        assert flags & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

    def test_dirty_flag_initial(self, model_scene):
        vp, _, _ = self._make_viewport(model_scene)
        assert vp._dirty is True

    def test_mark_dirty(self, model_scene):
        vp, _, _ = self._make_viewport(model_scene)
        vp._dirty = False
        vp.mark_dirty()
        assert vp._dirty is True

    def test_update_data_from_position(self, model_scene):
        vp, data, _ = self._make_viewport(model_scene)
        vp.setPos(100, 200)
        vp.sync_data_from_item()
        assert data.x == pytest.approx(100)
        assert data.y == pytest.approx(200)

    def test_placeholder_on_missing_view(self, model_scene):
        from firepro3d.paper_space import SheetViewData, SheetViewport
        from unittest.mock import MagicMock

        data = SheetViewData("plan", "Deleted View", "Deleted", 0.01,
                             50, 50, 400, 300)
        resolver = MagicMock()
        resolver.resolve.return_value = None
        vp = SheetViewport(data, resolver)
        assert vp._placeholder is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_space.py::TestSheetViewport -v`
Expected: FAIL — `SheetViewport` not found.

- [ ] **Step 3: Implement SheetViewport**

Add to `paper_space.py` after `ViewResolver`:

```python
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsSceneContextMenuEvent, QMenu
from PyQt6.QtCore import pyqtSignal


# Grip handle size in scene mm
_GRIP_SIZE = 4.0
_MIN_VIEWPORT_SIZE = 20.0


class SheetViewport(QGraphicsObject):
    """A viewport on a paper sheet that renders a source view at scale.

    Supports movable placement, 8-handle resize grips, pixmap caching
    with dirty-flag invalidation, and right-click context menu.
    """

    navigate_requested = pyqtSignal(str, str)  # view_type, view_name
    delete_requested = pyqtSignal(object)       # self
    properties_requested = pyqtSignal(object)   # self

    def __init__(self, data: SheetViewData, resolver: ViewResolver,
                 parent=None):
        super().__init__(parent)
        self._data = data
        self._resolver = resolver
        self._dirty = True
        self._cache: QPixmap | None = None
        self._placeholder = False
        self._resizing = False
        self._resize_handle: int = -1
        self._resize_origin = QPointF()

        self.setPos(data.x, data.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(5)

        # Resolve source and connect dirty signal
        self._source_scene = None
        self._source_rect = QRectF()
        self._reconnect_source()

    @property
    def data(self) -> SheetViewData:
        return self._data

    def _reconnect_source(self):
        """Resolve source view and connect to its changed signal."""
        # Disconnect old
        if self._source_scene is not None:
            try:
                self._source_scene.changed.disconnect(self._on_source_changed)
            except (TypeError, RuntimeError):
                pass
        result = self._resolver.resolve(
            self._data.source_view_type, self._data.source_view_name)
        if result is None:
            self._placeholder = True
            self._source_scene = None
            self._source_rect = QRectF()
            return
        self._placeholder = False
        self._source_scene, self._source_rect = result
        self._source_scene.changed.connect(self._on_source_changed)

    def _on_source_changed(self, rects=None):
        self.mark_dirty()

    def mark_dirty(self):
        self._dirty = True
        self._cache = None
        self.update()

    def sync_data_from_item(self):
        """Sync SheetViewData x/y from current scene position."""
        pos = self.pos()
        self._data.x = pos.x()
        self._data.y = pos.y()

    def boundingRect(self) -> QRectF:
        margin = _GRIP_SIZE if self.isSelected() else 0
        return QRectF(-margin, -margin,
                      self._data.w + 2 * margin,
                      self._data.h + 2 * margin)

    def paint(self, painter: QPainter, option, widget=None):
        w, h = self._data.w, self._data.h
        vp_rect = QRectF(0, 0, w, h)

        if self._placeholder:
            # Gray placeholder with warning text
            painter.fillRect(vp_rect, QColor("#e0e0e0"))
            painter.setPen(QPen(QColor("#888888"), 0.5))
            painter.drawRect(vp_rect)
            f = QFont("Arial", 3)
            painter.setFont(f)
            painter.setPen(Qt.GlobalColor.darkRed)
            painter.drawText(vp_rect, Qt.AlignmentFlag.AlignCenter,
                             f"View not found:\n{self._data.source_view_name}")
            return

        # Render from cache
        if self._dirty or self._cache is None:
            self._render_to_cache()

        if self._cache and not self._cache.isNull():
            painter.drawPixmap(vp_rect.toRect(), self._cache)
        else:
            painter.fillRect(vp_rect, Qt.GlobalColor.white)

        # Border
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.isSelected():
            painter.setPen(QPen(QColor("#0055ff"), 0.8,
                                Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(Qt.GlobalColor.black, 0.3))
        painter.drawRect(vp_rect)

        # Resize grips when selected
        if self.isSelected():
            self._draw_grips(painter)

    def _render_to_cache(self):
        """Render source scene into a cached QPixmap."""
        if self._source_scene is None:
            self._cache = None
            self._dirty = False
            return
        w, h = self._data.w, self._data.h
        # Render at 2x for quality
        dpr = 2
        px_w, px_h = int(w * dpr), int(h * dpr)
        if px_w <= 0 or px_h <= 0:
            self._cache = None
            self._dirty = False
            return
        pixmap = QPixmap(px_w, px_h)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.white)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = QRectF(0, 0, w, h)
        self._source_scene.render(p, target, self._source_rect)
        p.end()
        self._cache = pixmap
        self._dirty = False

    # ── Grip handles ──────────────────────────────────────────────────────

    def _grip_rects(self) -> list[QRectF]:
        """Return 8 grip handle rects: TL, TC, TR, ML, MR, BL, BC, BR."""
        w, h = self._data.w, self._data.h
        g = _GRIP_SIZE
        hg = g / 2
        return [
            QRectF(-hg, -hg, g, g),                      # TL
            QRectF(w / 2 - hg, -hg, g, g),               # TC
            QRectF(w - hg, -hg, g, g),                    # TR
            QRectF(-hg, h / 2 - hg, g, g),               # ML
            QRectF(w - hg, h / 2 - hg, g, g),            # MR
            QRectF(-hg, h - hg, g, g),                    # BL
            QRectF(w / 2 - hg, h - hg, g, g),            # BC
            QRectF(w - hg, h - hg, g, g),                 # BR
        ]

    def _draw_grips(self, painter: QPainter):
        painter.setPen(QPen(QColor("#0055ff"), 0.3))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        for r in self._grip_rects():
            painter.drawRect(r)

    def _hit_grip(self, pos: QPointF) -> int:
        """Return grip index at pos, or -1."""
        for i, r in enumerate(self._grip_rects()):
            if r.contains(pos):
                return i
        return -1

    def mousePressEvent(self, event):
        if (self.isSelected() and
                event.button() == Qt.MouseButton.LeftButton):
            grip = self._hit_grip(event.pos())
            if grip >= 0:
                self._resizing = True
                self._resize_handle = grip
                self._resize_origin = event.pos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.pos() - self._resize_origin
            self._apply_grip_resize(self._resize_handle, delta)
            self._resize_origin = event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_handle = -1
            self.sync_data_from_item()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_grip_resize(self, handle: int, delta: QPointF):
        """Resize viewport by moving a grip handle."""
        dx, dy = delta.x(), delta.y()
        x, y = self._data.x, self._data.y
        w, h = self._data.w, self._data.h

        # TL=0, TC=1, TR=2, ML=3, MR=4, BL=5, BC=6, BR=7
        if handle in (0, 3, 5):   # left edge
            new_w = max(w - dx, _MIN_VIEWPORT_SIZE)
            actual_dx = w - new_w
            self._data.x = x + actual_dx
            self._data.w = new_w
        if handle in (2, 4, 7):   # right edge
            self._data.w = max(w + dx, _MIN_VIEWPORT_SIZE)
        if handle in (0, 1, 2):   # top edge
            new_h = max(h - dy, _MIN_VIEWPORT_SIZE)
            actual_dy = h - new_h
            self._data.y = y + actual_dy
            self._data.h = new_h
        if handle in (5, 6, 7):   # bottom edge
            self._data.h = max(h + dy, _MIN_VIEWPORT_SIZE)

        self.setPos(self._data.x, self._data.y)
        self.mark_dirty()
        self.prepareGeometryChange()

    def mouseDoubleClickEvent(self, event):
        self.navigate_requested.emit(
            self._data.source_view_type, self._data.source_view_name)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent):
        menu = QMenu()
        props_action = menu.addAction("Properties...")
        goto_action = menu.addAction("Go to View")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(event.screenPos())
        if action == props_action:
            self.properties_requested.emit(self)
        elif action == goto_action:
            self.navigate_requested.emit(
                self._data.source_view_type, self._data.source_view_name)
        elif action == delete_action:
            self.delete_requested.emit(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.sync_data_from_item()
        return super().itemChange(change, value)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit(self)
        else:
            super().keyPressEvent(event)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paper_space.py::TestSheetViewport -v`
Expected: PASS

- [ ] **Step 5: Write dirty-flag integration test**

Add to `TestSheetViewport`:

```python
    def test_dirty_flag_on_source_change(self, model_scene):
        vp, _, _ = self._make_viewport(model_scene)
        vp._dirty = False
        # Simulate source scene change
        model_scene.addRect(500, 500, 100, 100)
        # The changed signal should have fired
        assert vp._dirty is True
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_paper_space.py::TestSheetViewport::test_dirty_flag_on_source_change -v`
Expected: PASS (the signal is connected in `_reconnect_source`)

- [ ] **Step 7: Commit**

```bash
git add firepro3d/paper_space.py tests/test_paper_space.py
git commit -m "feat(paper-space): add SheetViewport with pixmap cache, grips, and context menu"
```

---

### Task 5: SheetViewPropertiesDialog

Pre-placement and post-placement properties dialog.

**Files:**
- Modify: `firepro3d/paper_space.py`

- [ ] **Step 1: Implement SheetViewPropertiesDialog**

Add to `paper_space.py` after `SheetViewport`:

```python
class SheetViewPropertiesDialog(QDialog):
    """Properties dialog for a sheet viewport.

    Used both pre-placement (title + scale) and post-placement
    (adds position and size fields).
    """

    def __init__(self, source_view_name: str, data: SheetViewData | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sheet View Properties")
        self._data = data  # None = pre-placement mode

        layout = QFormLayout(self)

        # Title
        self._title_edit = QLineEdit(
            data.title if data else source_view_name)
        layout.addRow("Title:", self._title_edit)

        # Scale combo
        self._scale_combo = QComboBox()
        self._scale_combo.setEditable(True)
        for label, _ in SCALE_PRESETS:
            self._scale_combo.addItem(label)
        if data:
            self._scale_combo.setCurrentText(float_to_scale_str(data.scale))
        else:
            self._scale_combo.setCurrentText("1:100")
        layout.addRow("Scale:", self._scale_combo)

        # Post-placement: position and size
        if data:
            from .constants import format_length, parse_dimension
            self._x_edit = QLineEdit(format_length(data.x))
            self._y_edit = QLineEdit(format_length(data.y))
            self._w_edit = QLineEdit(format_length(data.w))
            self._h_edit = QLineEdit(format_length(data.h))
            layout.addRow("Position X:", self._x_edit)
            layout.addRow("Position Y:", self._y_edit)
            layout.addRow("Width:", self._w_edit)
            layout.addRow("Height:", self._h_edit)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_title(self) -> str:
        return self._title_edit.text()

    def get_scale(self) -> float:
        return scale_to_float(self._scale_combo.currentText())

    def get_position(self) -> tuple[float, float] | None:
        """Return (x, y) if in post-placement mode, else None."""
        if self._data is None:
            return None
        from .constants import parse_dimension
        x = parse_dimension(self._x_edit.text())
        y = parse_dimension(self._y_edit.text())
        if x is None or y is None:
            return (self._data.x, self._data.y)
        return (x, y)

    def get_size(self) -> tuple[float, float] | None:
        """Return (w, h) if in post-placement mode, else None."""
        if self._data is None:
            return None
        from .constants import parse_dimension
        w = parse_dimension(self._w_edit.text())
        h = parse_dimension(self._h_edit.text())
        if w is None or h is None:
            return (self._data.w, self._data.h)
        return (max(w, _MIN_VIEWPORT_SIZE), max(h, _MIN_VIEWPORT_SIZE))
```

- [ ] **Step 2: Commit**

```bash
git add firepro3d/paper_space.py
git commit -m "feat(paper-space): add SheetViewPropertiesDialog for pre/post-placement"
```

---

### Task 6: Title Block Scale Auto-Population

Test and implement the scale auto-population logic.

**Files:**
- Modify: `firepro3d/paper_space.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Write failing tests for scale auto-population**

Add to `tests/test_paper_space.py`:

```python
class TestScaleAutoPopulation:
    """Title block Scale field auto-populates from viewport scales."""

    def test_single_viewport_scale(self):
        from firepro3d.paper_space import Sheet, SheetViewData, \
            _compute_scale_field
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 0, 0, 100, 100),
        ]
        assert _compute_scale_field(sheet) == "1:100"

    def test_multiple_same_scale(self):
        from firepro3d.paper_space import Sheet, SheetViewData, \
            _compute_scale_field
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 0, 0, 100, 100),
            SheetViewData("detail", "D1", "D1", 0.01, 200, 0, 100, 100),
        ]
        assert _compute_scale_field(sheet) == "1:100"

    def test_multiple_different_scales(self):
        from firepro3d.paper_space import Sheet, SheetViewData, \
            _compute_scale_field
        sheet = Sheet.create_default()
        sheet.sheet_views = [
            SheetViewData("plan", "L1", "L1", 0.01, 0, 0, 100, 100),
            SheetViewData("detail", "D1", "D1", 0.02, 200, 0, 100, 100),
        ]
        assert _compute_scale_field(sheet) == "AS NOTED"

    def test_no_viewports(self):
        from firepro3d.paper_space import Sheet, _compute_scale_field
        sheet = Sheet.create_default()
        assert _compute_scale_field(sheet) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_space.py::TestScaleAutoPopulation -v`
Expected: FAIL — `_compute_scale_field` not found.

- [ ] **Step 3: Implement _compute_scale_field**

Add to `paper_space.py` after `float_to_scale_str`:

```python
def _compute_scale_field(sheet: "Sheet") -> str:
    """Compute the title block Scale field from viewport scales."""
    if not sheet.sheet_views:
        return ""
    scales = {sv.scale for sv in sheet.sheet_views}
    if len(scales) == 1:
        return float_to_scale_str(next(iter(scales)))
    return "AS NOTED"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paper_space.py::TestScaleAutoPopulation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add firepro3d/paper_space.py tests/test_paper_space.py
git commit -m "feat(paper-space): add title block Scale auto-population logic"
```

---

### Task 6b: TitleBlockFieldOverlay for DXF/PDF Title Blocks

When DXF artwork is active, the programmatic `TitleBlockItem` is hidden — field values vanish. This overlay draws field values on top of any title block background.

**Files:**
- Modify: `firepro3d/paper_space.py`

- [ ] **Step 1: Measure field cell positions from DXF geometry**

Run the app, open Paper Space with ANSI D, and visually identify where the field value cells are in the DXF title block artwork. Record approximate (x, y, w, h) in mm for each of the 9 fields. The DXF artwork spans the full paper (0,0 to 863.6, 558.8) with the title block in the lower-right area.

Alternatively, inspect the programmatic `TitleBlockItem` layout (which mirrors the DXF cell structure) and adapt those positions. The programmatic block uses: `c0=MARGIN+INNER_MARGIN`, `c1=c0+w*0.30`, `c2=c0+w*0.70`, `c3=c0+w*0.85`, with rows at `y`, `y+h*0.33`, `y+h*0.66`.

- [ ] **Step 2: Implement TitleBlockFieldOverlay**

Add to `paper_space.py`:

```python
class TitleBlockFieldOverlay(QGraphicsItem):
    """Draws editable title block field values on top of DXF/PDF artwork.

    Only used when an external (DXF/PDF) title block is active.
    The programmatic TitleBlockItem draws its own fields.
    """

    def __init__(self, paper_w: float, paper_h: float,
                 fields: dict[str, str], parent=None):
        super().__init__(parent)
        self._paper_w = paper_w
        self._paper_h = paper_h
        self._fields = fields
        self.setZValue(1)  # above DXF/PDF artwork (0.5), below border (2)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._paper_w, self._paper_h)

    def paint(self, painter: QPainter, option, widget=None):
        layout = _get_field_layout(self._paper_w, self._paper_h)
        if layout is None:
            return
        for field_name, (x, y, w, h, font_size) in layout.items():
            value = self._fields.get(field_name, "")
            if not value:
                continue
            f = QFont("Arial")
            f.setPointSizeF(font_size)
            f.setBold(True)
            painter.setFont(f)
            painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
            painter.drawText(
                QRectF(x + 1, y + h * 0.3, w - 2, h * 0.65),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                value,
            )


def _get_field_layout(paper_w: float, paper_h: float
                      ) -> dict[str, tuple[float, float, float, float, float]] | None:
    """Return field layout for the given paper size, or None if unknown.

    Returns {field_name: (x, y, w, h, font_size_pt)} in mm.
    Positions are measured from the DXF title block cell geometry.
    """
    # Title block occupies the bottom strip inside the border.
    # Cell layout mirrors the programmatic TitleBlockItem.
    bx = MARGIN + INNER_MARGIN
    by = paper_h - MARGIN - INNER_MARGIN - TITLE_H
    bw = paper_w - 2 * (MARGIN + INNER_MARGIN)
    bh = TITLE_H

    c0 = bx
    c1 = bx + bw * 0.30
    c2 = bx + bw * 0.70
    c3 = bx + bw * 0.85

    r0 = by
    r1 = by + bh * 0.33
    r2 = by + bh * 0.66
    r3 = by + bh

    row_h = (r3 - r0) / 3.0
    half_col1 = (c2 - c1) / 2.0

    return {
        "Company":    (c0, r0, c1 - c0, bh, 2.5),
        "Project":    (c1, r0, c2 - c1, row_h, 2.2),
        "Title":      (c1, r1, c2 - c1, row_h, 2.2),
        "Drawn By":   (c1, r2, half_col1, row_h, 2.0),
        "Checked By": (c1 + half_col1, r2, half_col1, row_h, 2.0),
        "Scale":      (c2, r0, c3 - c2, row_h, 2.2),
        "Drawing No": (c2, r1, c3 - c2, row_h, 2.2),
        "Rev":        (c3, r0, bx + bw - c3, row_h, 2.2),
        "Date":       (c3, r1, bx + bw - c3, row_h, 2.2),
    }
```

- [ ] **Step 3: Add overlay to PaperScene._setup()**

In `_setup()`, after adding the DXF/PDF title block and before `setSceneRect`, add:

```python
        # Field overlay for DXF/PDF title blocks
        self._field_overlay = None
        if use_external_title:
            self._field_overlay = TitleBlockFieldOverlay(
                w, h, self._sheet.title_block_fields)
            self.addItem(self._field_overlay)
```

- [ ] **Step 4: Commit**

```bash
git add firepro3d/paper_space.py
git commit -m "feat(paper-space): add TitleBlockFieldOverlay for DXF/PDF title blocks"
```

---

### Task 7: Refactor PaperScene for Multi-Viewport

Replace the single fixed viewport with `Sheet`-driven multi-viewport management.

**Files:**
- Modify: `firepro3d/paper_space.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Refactor PaperScene.__init__ and _setup**

Update the `PaperScene` class signature and `_setup()` method. The constructor now takes a `Sheet` and `ViewResolver` instead of `model_scene`:

```python
class PaperScene(QGraphicsScene):
    """QGraphicsScene representing one paper layout.

    Coordinate system: 1 scene unit = 1 mm.
    """

    def __init__(self, sheet: Sheet, resolver: ViewResolver):
        super().__init__()
        self._sheet = sheet
        self._resolver = resolver
        self._bg_item = None
        self._border_item = None
        self._title = None
        self._title_tb = None
        self._viewports: list[SheetViewport] = []
        self._setup()

    def _setup(self):
        """Build/rebuild all paper scene items."""
        self.clear()
        self._title_tb = None
        self._viewports = []

        w, h = PAPER_SIZES[self._sheet.paper_size]

        # White paper background
        self._bg_item = self.addRect(
            0, 0, w, h,
            QPen(Qt.GlobalColor.black, 0.3),
            QBrush(Qt.GlobalColor.white),
        )
        self._bg_item.setZValue(0)

        # Title block: try DXF (vector) → PDF (raster) → programmatic
        use_external_title = False

        dxf_path = TITLE_BLOCK_DXFS.get(self._sheet.paper_size)
        if dxf_path and os.path.isfile(dxf_path):
            tb_dxf = TitleBlockDxfItem(dxf_path, w, h)
            if tb_dxf.is_valid():
                self.addItem(tb_dxf)
                self._title_tb = tb_dxf
                use_external_title = True

        if not use_external_title:
            pdf_path = TITLE_BLOCK_PDFS.get(self._sheet.paper_size)
            if pdf_path:
                tb_pdf = TitleBlockPdfItem(pdf_path, w, h)
                if (tb_pdf.pixmap() is not None
                        and not tb_pdf.pixmap().isNull()):
                    self.addItem(tb_pdf)
                    self._title_tb = tb_pdf
                    use_external_title = True

        # Drawing border
        bx, by = MARGIN, MARGIN
        bw, bh = w - 2 * MARGIN, h - 2 * MARGIN
        border = self.addRect(
            bx, by, bw, bh,
            QPen(Qt.GlobalColor.black, 0.5),
            QBrush(Qt.BrushStyle.NoBrush),
        )
        border.setZValue(2)

        # Programmatic title block (fallback)
        self._title = TitleBlockItem(w, h)
        self._title.fields = self._sheet.title_block_fields
        self.addItem(self._title)
        if use_external_title:
            self._title.hide()

        self.setSceneRect(-20, -20, w + 40, h + 40)

        # Rebuild viewports from sheet data
        for sv_data in self._sheet.sheet_views:
            self._create_viewport(sv_data)
```

- [ ] **Step 2: Add viewport management methods to PaperScene**

Add after `_setup()`:

```python
    def _create_viewport(self, data: SheetViewData) -> SheetViewport:
        """Create a SheetViewport item and add to scene."""
        vp = SheetViewport(data, self._resolver)
        vp.navigate_requested.connect(self._on_navigate)
        vp.delete_requested.connect(self._on_delete_viewport)
        vp.properties_requested.connect(self._on_viewport_properties)
        self.addItem(vp)
        self._viewports.append(vp)
        return vp

    def add_viewport(self, data: SheetViewData) -> SheetViewport:
        """Add a new viewport to the sheet."""
        self._sheet.sheet_views.append(data)
        vp = self._create_viewport(data)
        self._update_scale_field()
        return vp

    def remove_viewport(self, viewport: SheetViewport):
        """Remove a viewport from the sheet."""
        if viewport in self._viewports:
            self._viewports.remove(viewport)
        if viewport.data in self._sheet.sheet_views:
            self._sheet.sheet_views.remove(viewport.data)
        self.removeItem(viewport)
        self._update_scale_field()

    def get_viewports(self) -> list[SheetViewport]:
        return list(self._viewports)

    def update_from_sheet(self, sheet: Sheet):
        """Rebuild the scene from a (possibly new) Sheet."""
        self._sheet = sheet
        self._setup()

    def _update_scale_field(self):
        """Update title block Scale field from viewport scales."""
        self._sheet.title_block_fields["Scale"] = _compute_scale_field(
            self._sheet)
        if self._title:
            self._title.update()

    def _on_navigate(self, view_type: str, view_name: str):
        # Propagated up — PaperSpaceWidget connects to this
        pass

    def _on_delete_viewport(self, viewport):
        self.remove_viewport(viewport)

    def _on_viewport_properties(self, viewport):
        dlg = SheetViewPropertiesDialog(
            viewport.data.source_view_name, viewport.data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            viewport.data.title = dlg.get_title()
            new_scale = dlg.get_scale()
            if new_scale != viewport.data.scale:
                viewport.data.scale = new_scale
                # Recompute viewport size from source at new scale
                result = self._resolver.resolve(
                    viewport.data.source_view_type,
                    viewport.data.source_view_name)
                if result:
                    _, src_rect = result
                    viewport.data.w = src_rect.width() * new_scale
                    viewport.data.h = src_rect.height() * new_scale
            pos = dlg.get_position()
            if pos:
                viewport.data.x, viewport.data.y = pos
            size = dlg.get_size()
            if size:
                viewport.data.w, viewport.data.h = size
            viewport.setPos(viewport.data.x, viewport.data.y)
            viewport.mark_dirty()
            viewport.prepareGeometryChange()
            self._update_scale_field()

    # ── Public API (preserved) ──────────────────────────────────────────

    @property
    def paper_size(self) -> str:
        return self._sheet.paper_size

    @paper_size.setter
    def paper_size(self, size: str):
        if size in PAPER_SIZES:
            self._sheet.paper_size = size
            self._setup()

    @property
    def sheet(self) -> Sheet:
        return self._sheet

    @property
    def title_block(self) -> TitleBlockItem:
        return self._title

    def refresh_viewport(self):
        """Force all viewports to repaint."""
        for vp in self._viewports:
            vp.mark_dirty()
```

- [ ] **Step 3: Update existing tests for new PaperScene signature**

Update the `model_scene` fixture usage in existing tests. Tests that create `PaperScene(model_scene, ...)` need to create a `Sheet` and `ViewResolver` instead. Add a helper fixture:

```python
@pytest.fixture
def paper_scene(model_scene):
    """PaperScene with default Sheet and mock ViewResolver."""
    from firepro3d.paper_space import Sheet, ViewResolver, PaperScene
    from unittest.mock import MagicMock

    sheet = Sheet.create_default()
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = (model_scene, QRectF(0, 0, 10000, 8000))
    return PaperScene(sheet, resolver)
```

Update all `TestPaperScene` tests to use this fixture instead of creating `PaperScene(model_scene, ...)` directly. The key changes:
- `PaperScene(model_scene, paper_size="ANSI D")` → `paper_scene` fixture (or create inline with `Sheet(paper_size=...)`)
- `ps._viewport` references → `ps.get_viewports()` or removed
- Add new test for multi-viewport:

```python
    def test_add_and_remove_viewport(self, model_scene):
        from firepro3d.paper_space import (Sheet, ViewResolver, PaperScene,
                                           SheetViewData)
        from unittest.mock import MagicMock

        sheet = Sheet.create_default()
        resolver = MagicMock(spec=ViewResolver)
        resolver.resolve.return_value = (model_scene, QRectF(0, 0, 10000, 8000))
        ps = PaperScene(sheet, resolver)

        data = SheetViewData("plan", "Level 1", "Level 1", 0.01,
                             50, 50, 400, 300)
        vp = ps.add_viewport(data)
        assert len(ps.get_viewports()) == 1
        assert data in sheet.sheet_views

        ps.remove_viewport(vp)
        assert len(ps.get_viewports()) == 0
        assert data not in sheet.sheet_views
```

- [ ] **Step 4: Run all paper space tests**

Run: `pytest tests/test_paper_space.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add firepro3d/paper_space.py tests/test_paper_space.py
git commit -m "refactor(paper-space): PaperScene multi-viewport with Sheet data model"
```

---

### Task 8: PaperSpaceWidget Drop Handling

Enable the paper space view as a drop target for views dragged from the browser.

**Files:**
- Modify: `firepro3d/paper_space.py`

- [ ] **Step 1: Create PaperGraphicsView subclass with drop support**

Add a `QGraphicsView` subclass to `paper_space.py` that handles drag-and-drop:

```python
import json

MIME_VIEW = "application/x-firepro3d-view"


class PaperGraphicsView(QGraphicsView):
    """QGraphicsView for PaperScene with drop support for view placement."""

    def __init__(self, scene: PaperScene, parent=None):
        super().__init__(scene, parent)
        self.setAcceptDrops(True)
        self._paper_scene = scene

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_VIEW):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_VIEW):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_VIEW):
            event.ignore()
            return
        # Decode view type + name
        raw = bytes(event.mimeData().data(MIME_VIEW)).decode("utf-8")
        payload = json.loads(raw)
        view_type = payload["view_type"]
        view_name = payload["view_name"]

        # Map drop position to scene coordinates
        drop_pos = self.mapToScene(event.position().toPoint())

        # Open pre-placement dialog
        dlg = SheetViewPropertiesDialog(view_name, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            event.ignore()
            return

        title = dlg.get_title()
        scale = dlg.get_scale()

        # Compute viewport size from source bounds
        result = self._paper_scene._resolver.resolve(view_type, view_name)
        if result is None:
            event.ignore()
            return
        _, src_rect = result
        vp_w = src_rect.width() * scale
        vp_h = src_rect.height() * scale

        # Clamp to printable area
        pw, ph = PAPER_SIZES[self._paper_scene.sheet.paper_size]
        max_w = pw - 2 * (MARGIN + INNER_MARGIN)
        max_h = ph - 2 * (MARGIN + INNER_MARGIN) - TITLE_H
        if vp_w > max_w or vp_h > max_h:
            clamp = min(max_w / vp_w, max_h / vp_h)
            vp_w *= clamp
            vp_h *= clamp

        # Center on drop point
        x = drop_pos.x() - vp_w / 2
        y = drop_pos.y() - vp_h / 2

        # Clamp position to paper bounds
        x = max(MARGIN + INNER_MARGIN,
                min(x, pw - MARGIN - INNER_MARGIN - vp_w))
        y = max(MARGIN + INNER_MARGIN,
                min(y, ph - MARGIN - INNER_MARGIN - TITLE_H - vp_h))

        data = SheetViewData(view_type, view_name, title, scale,
                             x, y, vp_w, vp_h)
        self._paper_scene.add_viewport(data)
        event.acceptProposedAction()
```

- [ ] **Step 2: Update PaperSpaceWidget to use PaperGraphicsView**

In `PaperSpaceWidget._build_ui()`, replace:

```python
        self.view = QGraphicsView(self.paper_scene)
```

with:

```python
        self.view = PaperGraphicsView(self.paper_scene)
```

- [ ] **Step 3: Update PaperSpaceWidget.__init__ to accept Sheet + ViewResolver**

Change the constructor:

```python
class PaperSpaceWidget(QWidget):
    """Complete Paper Space panel: toolbar + QGraphicsView of PaperScene."""

    navigate_to_view = pyqtSignal(str, str)  # view_type, view_name

    def __init__(self, sheet: Sheet, resolver: ViewResolver, parent=None):
        super().__init__(parent)
        self._sheet = sheet
        self._resolver = resolver

        self.paper_scene = PaperScene(sheet, resolver)

        self._build_ui()
```

- [ ] **Step 4: Wire navigate signal**

In `PaperScene._on_navigate`, emit a signal that `PaperSpaceWidget` can relay:

Update `PaperScene` to be a proper signal source. Since `PaperScene` inherits `QGraphicsScene` (which inherits `QObject`), it can emit signals. Add to `PaperScene`:

```python
    navigate_to_view = pyqtSignal(str, str)

    def _on_navigate(self, view_type: str, view_name: str):
        self.navigate_to_view.emit(view_type, view_name)
```

In `PaperSpaceWidget.__init__`, relay the signal:

```python
        self.paper_scene.navigate_to_view.connect(self.navigate_to_view.emit)
```

- [ ] **Step 5: Update TitleBlockDialog to use Sheet.title_block_fields**

Modify `TitleBlockDialog.__init__` and `_save` to work with `Sheet.title_block_fields` instead of `TitleBlockItem.fields`:

```python
class TitleBlockDialog(QDialog):
    def __init__(self, sheet: Sheet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Title Block")
        self._sheet = sheet

        layout = QFormLayout(self)
        self._edits: dict[str, QLineEdit] = {}

        for key, value in sheet.title_block_fields.items():
            edit = QLineEdit(value)
            # Scale is auto-populated — make read-only
            if key == "Scale":
                edit.setReadOnly(True)
                edit.setStyleSheet("background: #f0f0f0;")
            self._edits[key] = edit
            layout.addRow(key + ":", edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self):
        for key, edit in self._edits.items():
            if key != "Scale":  # don't overwrite auto-populated field
                self._sheet.title_block_fields[key] = edit.text()
        self.accept()
```

Update `PaperSpaceWidget._edit_title` to pass `Sheet`:

```python
    def _edit_title(self):
        dlg = TitleBlockDialog(self._sheet, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Sync fields to title block item
            self.paper_scene.title_block.fields = self._sheet.title_block_fields
            self.paper_scene.title_block.update()
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/test_paper_space.py -v`
Expected: All PASS (update any tests broken by the constructor change)

- [ ] **Step 7: Commit**

```bash
git add firepro3d/paper_space.py
git commit -m "feat(paper-space): add drop handling and view placement workflow"
```

---

### Task 9: Browser Tree — Views Group with Drag

Add the "Views" group to the model browser with drag-and-drop support.

**Files:**
- Modify: `firepro3d/model_browser.py`

- [ ] **Step 1: Add ViewResolver reference and imports**

Add to `model_browser.py` imports:

```python
import json
from PyQt6.QtCore import QMimeData, QByteArray
```

In `ModelBrowser.__init__`, add:

```python
        self._view_resolver = None  # set via set_view_resolver()
        self._placed_views: set[tuple[str, str]] = set()  # (type, name)
```

Add a public method:

```python
    def set_view_resolver(self, resolver):
        """Set the ViewResolver for populating the Views group."""
        self._view_resolver = resolver

    def set_placed_views(self, placed: set[tuple[str, str]]):
        """Set which views are currently placed on a sheet (shown italic)."""
        self._placed_views = placed
```

- [ ] **Step 2: Add Views group to refresh()**

Add a `_ROLE_VIEW` constant after the existing role definitions:

```python
_ROLE_VIEW = Qt.ItemDataRole.UserRole + 2  # stores (view_type, view_name)
```

In `refresh()`, add the Views group **before** the entity groups (so it appears at the top of the tree). Insert after `self._tree.clear()` and expansion save, before the Walls group:

```python
        # ── Views group ──────────────────────────────────────────────────
        if self._view_resolver:
            views_root = QTreeWidgetItem(self._tree, ["Views"])
            views_root.setFont(0, _BOLD_FONT)
            views_root.setExpanded(True)

            available = self._view_resolver.available_views()
            for group_name, view_names in available.items():
                group_node = QTreeWidgetItem(views_root, [group_name])
                group_node.setFont(0, _BOLD_FONT)
                group_node.setExpanded(True)

                # Determine view_type from group name
                type_map = {
                    "Floor Plans": "plan",
                    "Details": "detail",
                    "Elevations": "elevation",
                }
                view_type = type_map.get(group_name, "plan")

                for name in view_names:
                    item = QTreeWidgetItem(group_node, [name])
                    item.setData(0, _ROLE_VIEW, (view_type, name))
                    item.setFlags(
                        item.flags() | Qt.ItemFlag.ItemIsDragEnabled)

                    # Italic if already placed on sheet
                    if (view_type, name) in self._placed_views:
                        italic_font = QFont()
                        italic_font.setItalic(True)
                        item.setFont(0, italic_font)
```

Note: `_BOLD_FONT` needs to be defined if not already present. Check existing code — the `refresh()` method creates bold fonts inline. Use the same pattern:

```python
        _bold = QFont()
        _bold.setBold(True)
```

- [ ] **Step 3: Enable drag on the tree widget**

In `ModelBrowser.__init__`, after the tree widget is created, add:

```python
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
```

- [ ] **Step 4: Override mimeData on the tree**

Create a custom `QTreeWidget` subclass or monkey-patch. The cleaner approach is a subclass. Replace `self._tree = QTreeWidget()` with a custom class:

```python
class _BrowserTree(QTreeWidget):
    """QTreeWidget with drag support for view items."""

    def mimeData(self, items):
        mime = QMimeData()
        for item in items:
            view_data = item.data(0, _ROLE_VIEW)
            if view_data:
                view_type, view_name = view_data
                payload = json.dumps({
                    "view_type": view_type,
                    "view_name": view_name,
                })
                mime.setData(
                    "application/x-firepro3d-view",
                    QByteArray(payload.encode("utf-8")),
                )
                break  # single item drag
        return mime

    def mimeTypes(self):
        return ["application/x-firepro3d-view"]
```

Then in `ModelBrowser.__init__`:

```python
        self._tree = _BrowserTree()
```

- [ ] **Step 5: Commit**

```bash
git add firepro3d/model_browser.py
git commit -m "feat(browser): add Views group with drag-to-paper-space support"
```

---

### Task 10: Serialization — scene_io.py Integration

Save/load `Sheet` data in the project file.

**Files:**
- Modify: `firepro3d/scene_io.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Write failing test for backward compatibility**

Add to `tests/test_paper_space.py`:

```python
class TestSerialization:
    """Sheet serialization in project file."""

    def test_backward_compat_no_sheets_key(self):
        from firepro3d.paper_space import Sheet
        # Simulate loading a project without sheets
        payload = {"version": 4}  # no "sheets" key
        sheets = [Sheet.from_dict(d)
                  for d in payload.get("sheets", [])]
        assert sheets == []

    def test_round_trip_via_payload(self):
        from firepro3d.paper_space import Sheet, SheetViewData
        sheet = Sheet(
            number="FP-1.0", name="Test Sheet",
            paper_size="ANSI D",
            title_block_fields={"Company": "Test", "Scale": "1:100"},
            sheet_views=[
                SheetViewData("plan", "Level 1", "Level 1", 0.01,
                              25, 25, 400, 300),
            ],
        )
        # Simulate save
        payload = {"sheets": [sheet.to_dict()]}
        # Simulate load
        loaded = [Sheet.from_dict(d) for d in payload["sheets"]]
        assert len(loaded) == 1
        assert loaded[0].number == "FP-1.0"
        assert len(loaded[0].sheet_views) == 1
        assert loaded[0].sheet_views[0].scale == pytest.approx(0.01)
```

- [ ] **Step 2: Run tests to verify they pass**

These use only `Sheet`/`SheetViewData` which are already implemented. They should pass immediately as a sanity check.

Run: `pytest tests/test_paper_space.py::TestSerialization -v`
Expected: PASS

- [ ] **Step 3: Add sheets to scene_io.py save payload**

In `firepro3d/scene_io.py`, in the `to_dict()` method (around line 230), add after the `"detail_views"` line:

```python
            "sheets": [s.to_dict() for s in self._sheets]
                       if hasattr(self, '_sheets') else [],
```

- [ ] **Step 4: Add sheets to scene_io.py load**

In the load method (around line 316, after detail_views loading), add:

```python
        # Sheets (paper space)
        from .paper_space import Sheet
        sheet_data = payload.get("sheets", [])
        self._sheets = [Sheet.from_dict(d) for d in sheet_data]
```

- [ ] **Step 5: Initialize _sheets attribute**

In `Model_Space.__init__` (or `SceneIOMixin.__init__` if it exists), ensure `self._sheets = []` is initialized so saving doesn't fail on projects that haven't opened paper space.

- [ ] **Step 6: Run all tests**

Run: `pytest tests/test_paper_space.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add firepro3d/scene_io.py tests/test_paper_space.py
git commit -m "feat(paper-space): add sheet serialization to project save/load"
```

---

### Task 11: Wire Everything in main.py

Connect `ViewResolver`, `Sheet`, and the refactored `PaperScene` / `PaperSpaceWidget`.

**Files:**
- Modify: `firepro3d/main.py`

- [ ] **Step 1: Update imports**

Change the import from `paper_space` (around line 25):

```python
from firepro3d.paper_space import (
    PaperSpaceWidget, Sheet, ViewResolver, PAPER_SIZES,
)
```

- [ ] **Step 2: Create ViewResolver and Sheet**

In `__init__`, after the elevation manager and detail manager are created (around line 355), add:

```python
        # Paper space
        self._sheet = Sheet.create_default()
        self._view_resolver = ViewResolver(
            self.scene, self.plan_view_mgr,
            self.detail_manager, self.elevation_manager,
        )
```

- [ ] **Step 3: Update PaperSpaceWidget creation**

Replace the existing `PaperSpaceWidget(self.scene)` creation (around line 260) with the new signature. Since managers are created later, move paper space creation after the managers. Replace:

```python
        self.paper_space_widget = PaperSpaceWidget(self.scene)
```

with (after `self._view_resolver` is created):

```python
        self.paper_space_widget = PaperSpaceWidget(
            self._sheet, self._view_resolver)
```

- [ ] **Step 4: Connect navigate_to_view signal**

After creating `paper_space_widget`:

```python
        self.paper_space_widget.navigate_to_view.connect(
            self._navigate_to_source_view)
```

Add the handler method to `MainWindow`:

```python
    def _navigate_to_source_view(self, view_type: str, view_name: str):
        """Navigate to a source view from a paper space viewport."""
        if view_type == "plan":
            # Extract level name: "Plan: Level 1" → "Level 1"
            level_name = view_name.replace("Plan: ", "", 1)
            self._activate_plan_view(level_name)
        elif view_type == "detail":
            self.detail_manager.open_detail(view_name)
        elif view_type == "elevation":
            self.elevation_manager.open_elevation(view_name.lower())
```

- [ ] **Step 5: Pass ViewResolver to ModelBrowser**

After creating the model browser (around line 357):

```python
        self.model_browser.set_view_resolver(self._view_resolver)
```

- [ ] **Step 6: Update placed views on browser refresh**

Add a method to sync placed-view state and call it when the paper scene changes. In the browser refresh trigger or in the paper space widget, after adding/removing viewports:

```python
    def _sync_placed_views(self):
        """Update browser italic indicators for placed views."""
        placed = {
            (sv.source_view_type, sv.source_view_name)
            for sv in self._sheet.sheet_views
        }
        self.model_browser.set_placed_views(placed)
        self.model_browser.schedule_refresh()
```

Call this after `PaperScene.add_viewport` and `remove_viewport` by connecting to appropriate signals. The simplest approach: refresh the browser when the paper space tab is activated.

- [ ] **Step 7: Wire sheet to save/load**

In the save flow, ensure `self.scene._sheets` includes the current sheet:

```python
        # Before save
        self.scene._sheets = [self._sheet]
```

In the load flow, after `scene_io` loads, pick up the sheet:

```python
        # After load
        if self.scene._sheets:
            self._sheet = self.scene._sheets[0]
        else:
            self._sheet = Sheet.create_default()
        # Rebuild paper space
        self.paper_space_widget.paper_scene.update_from_sheet(self._sheet)
```

- [ ] **Step 8: Commit**

```bash
git add firepro3d/main.py
git commit -m "feat(paper-space): wire ViewResolver, Sheet, and navigation in main.py"
```

---

### Task 12: Remove Old PaperViewport Class

Clean up the now-unused `PaperViewport` class.

**Files:**
- Modify: `firepro3d/paper_space.py`
- Modify: `tests/test_paper_space.py`

- [ ] **Step 1: Remove PaperViewport class**

Delete the entire `PaperViewport` class from `paper_space.py` (the old single-viewport renderer, approximately lines 463-519 in the original file).

- [ ] **Step 2: Update tests**

Remove `TestPaperViewport` test class from `tests/test_paper_space.py`. Replace with equivalent coverage via `TestSheetViewport` (already written in Task 4).

Update any remaining test imports that reference `PaperViewport`.

- [ ] **Step 3: Run all tests**

Run: `pytest tests/test_paper_space.py -v`
Expected: All PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: No regressions

- [ ] **Step 5: Commit**

```bash
git add firepro3d/paper_space.py tests/test_paper_space.py
git commit -m "refactor(paper-space): remove old PaperViewport, replaced by SheetViewport"
```

---

### Task 13: Integration Smoke Test Pass

Verify everything works end-to-end.

**Files:**
- Read-only verification of all modified files

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: All PASS, no regressions

- [ ] **Step 2: Verify imports are clean**

Run: `python -c "from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver, SheetViewport, PaperScene, PaperSpaceWidget, scale_to_float, float_to_scale_str, SCALE_PRESETS, MIME_VIEW; print('All imports OK')"`
Expected: "All imports OK"

- [ ] **Step 3: Verify backward compatibility**

Run: `python -c "
from firepro3d.paper_space import Sheet
# No sheets key → empty
import json
payload = json.loads('{\"version\": 4}')
sheets = [Sheet.from_dict(d) for d in payload.get('sheets', [])]
assert sheets == [], 'Backward compat failed'
print('Backward compat OK')
"`
Expected: "Backward compat OK"

- [ ] **Step 4: Commit any remaining fixes**

```bash
git add -A
git commit -m "fix(paper-space): integration fixes from smoke test"
```
