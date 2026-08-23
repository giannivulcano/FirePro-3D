"""tests/test_geo2d_fill_opacity.py

Per-item Fill Opacity for solid fills (default 45%).

Tests:
  1. fill_opacity default is 0.45.
  2. Panel "Fill Opacity" row appears only when fill_type == "solid".
  3. Setting "Fill Opacity" via panel (string row editingFinished) stores
     fill_opacity as a fraction (e.g. "80" → 0.80).
  4. Junk input is rejected; prior value is kept.
  5. draw_fill is called with alpha derived from fill_opacity
     (alpha = int(round(fill_opacity * 255))):
     render a solid rect at opacity 0.8 vs 0.3 and compare interior pixel
     luminosity (higher opacity → more opaque colour, less white bleed).
  6. Round-trip: "opacity" key in fill block survives to_dict/from_dict;
     a fill block without "opacity" key defaults to 0.45 (back-compat).
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtWidgets import QGraphicsScene, QLineEdit, QComboBox

from firepro3d.construction_geometry import RectangleItem, CircleItem, LineItem
from firepro3d.level_manager import LevelManager
from firepro3d.property_manager import PropertyManager
from firepro3d.scale_manager import ScaleManager


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (mirror test_geo2d_panel.py)
# ─────────────────────────────────────────────────────────────────────────────

def _make_scene(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    s._level_manager = LevelManager()
    s.scale_manager = ScaleManager()
    return s


def _make_panel(scene) -> PropertyManager:
    pm = PropertyManager()
    pm.set_level_manager(scene._level_manager)
    return pm


def _row_labels(pm: PropertyManager) -> list[str]:
    form = pm._form
    texts = []
    for i in range(form.rowCount()):
        lbl_item = form.itemAt(i, form.ItemRole.LabelRole)
        if lbl_item and lbl_item.widget():
            texts.append(lbl_item.widget().text())
    return texts


def _find_row_editor(pm: PropertyManager, label_text: str):
    """Return the editor widget for the given label.

    Handles the suffix-container case: when a property has a 'suffix' key,
    PropertyManager wraps the real editor in a QWidget container with a
    QHBoxLayout.  We unwrap one level to find the actual editor.
    """
    from PyQt6.QtWidgets import QWidget
    form = pm._form
    for i in range(form.rowCount()):
        lbl_item = form.itemAt(i, form.ItemRole.LabelRole)
        field_item = form.itemAt(i, form.ItemRole.FieldRole)
        if lbl_item and lbl_item.widget():
            if lbl_item.widget().text() == label_text and field_item:
                w = field_item.widget()
                if w is None:
                    return None
                # If it's a plain editor (QLineEdit, QComboBox, …), return it.
                if isinstance(w, (QLineEdit, QComboBox)):
                    return w
                # Otherwise it may be a suffix-container QWidget; look inside.
                layout = w.layout()
                if layout is not None:
                    for j in range(layout.count()):
                        child = layout.itemAt(j).widget()
                        if isinstance(child, (QLineEdit, QComboBox)):
                            return child
                return w
    return None


def _render_to_image(item, size: int = 120, scene_rect=(0, 0, 120, 120)) -> QImage:
    """Render *item* (already added to a scene) into a white QImage."""
    scene = item.scene()
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), QRectF(*scene_rect))
    p.end()
    return img


def _pixel(img: QImage, x: int, y: int) -> QColor:
    return QColor(img.pixel(x, y))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Default fill_opacity
# ─────────────────────────────────────────────────────────────────────────────

def test_fill_opacity_default(qapp):
    """fill_opacity must default to 0.45 on a new item."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    assert hasattr(r, "fill_opacity"), "RectangleItem must have fill_opacity attribute"
    assert r.fill_opacity == pytest.approx(0.45)


def test_fill_opacity_default_circle(qapp):
    """CircleItem fill_opacity must also default to 0.45."""
    c = CircleItem(QPointF(50, 50), 40.0)
    assert c.fill_opacity == pytest.approx(0.45)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Panel row visibility: only for solid fill
# ─────────────────────────────────────────────────────────────────────────────

def test_fill_opacity_row_present_for_solid(qapp):
    """'Fill Opacity' row must appear in _geom2d_properties() when fill_type='solid'."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    props = r.get_properties()
    assert "Fill Opacity" in props, (
        f"'Fill Opacity' must be in properties when solid; keys: {list(props)}"
    )


def test_fill_opacity_row_absent_for_none(qapp):
    """'Fill Opacity' row must NOT appear when fill_type='none'."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "none"
    props = r.get_properties()
    assert "Fill Opacity" not in props, (
        "'Fill Opacity' must not appear for fill_type='none'"
    )


def test_fill_opacity_row_absent_for_hatch(qapp):
    """'Fill Opacity' row must NOT appear when fill_type='hatch'."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "hatch"
    props = r.get_properties()
    assert "Fill Opacity" not in props, (
        "'Fill Opacity' must not appear for fill_type='hatch'"
    )


def test_fill_opacity_row_absent_for_non_fillable(qapp):
    """LineItem (not fillable) must never expose 'Fill Opacity'."""
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    props = line.get_properties()
    assert "Fill Opacity" not in props


# ─────────────────────────────────────────────────────────────────────────────
# 3. Panel commit: string QLineEdit "80" → fill_opacity == 0.80
# ─────────────────────────────────────────────────────────────────────────────

def test_panel_commit_opacity_via_string_editor(qapp):
    """Typing '80' in the 'Fill Opacity' field must set fill_opacity=0.80."""
    scene = _make_scene(qapp)
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    scene.addItem(r)

    pm = _make_panel(scene)
    pm.show_properties(r)

    editor = _find_row_editor(pm, "Fill Opacity")
    assert editor is not None, (
        f"'Fill Opacity' row editor not found in panel; labels: {_row_labels(pm)}"
    )
    assert isinstance(editor, QLineEdit), (
        f"Expected QLineEdit for 'Fill Opacity', got {type(editor).__name__}"
    )

    editor.setText("80")
    editor.editingFinished.emit()

    assert r.fill_opacity == pytest.approx(0.80), (
        f"Expected fill_opacity=0.80 after setting '80', got {r.fill_opacity}"
    )


def test_panel_commit_opacity_100(qapp):
    """Setting '100' must clamp to fill_opacity=1.0."""
    scene = _make_scene(qapp)
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    scene.addItem(r)

    pm = _make_panel(scene)
    pm.show_properties(r)

    editor = _find_row_editor(pm, "Fill Opacity")
    assert editor is not None
    editor.setText("100")
    editor.editingFinished.emit()

    assert r.fill_opacity == pytest.approx(1.0)


def test_panel_commit_opacity_0(qapp):
    """Setting '0' must store fill_opacity=0.0."""
    scene = _make_scene(qapp)
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    scene.addItem(r)

    pm = _make_panel(scene)
    pm.show_properties(r)

    editor = _find_row_editor(pm, "Fill Opacity")
    assert editor is not None
    editor.setText("0")
    editor.editingFinished.emit()

    assert r.fill_opacity == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Junk input rejected; prior value kept
# ─────────────────────────────────────────────────────────────────────────────

def test_panel_commit_opacity_junk_keeps_prior(qapp):
    """Non-numeric input must be rejected; fill_opacity must stay at prior value."""
    scene = _make_scene(qapp)
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    r.fill_opacity = 0.60
    scene.addItem(r)

    pm = _make_panel(scene)
    pm.show_properties(r)

    editor = _find_row_editor(pm, "Fill Opacity")
    assert editor is not None
    editor.setText("abc")
    editor.editingFinished.emit()

    assert r.fill_opacity == pytest.approx(0.60), (
        f"Junk input must not change fill_opacity; got {r.fill_opacity}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Render: higher opacity → more opaque (less white bleed)
# ─────────────────────────────────────────────────────────────────────────────

def _luminosity(c: QColor) -> int:
    """Approximate luminosity (0=black, 255=white)."""
    return (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000


def test_higher_opacity_renders_more_opaque(qapp):
    """A rect at 0.8 opacity must render the interior darker than at 0.3.

    Uses pure blue (#0000ff) fill on a white background so the alpha blend
    is predictable: higher alpha → less white bleed → lower luminosity.
    """
    def _render_rect_at_opacity(opacity: float) -> QColor:
        scene = QGraphicsScene()
        r = RectangleItem(QPointF(10, 10), QPointF(110, 110))
        r.fill_type = "solid"
        r._display_fill_color = "#0000ff"
        r.fill_opacity = opacity
        scene.addItem(r)
        img = QImage(120, 120, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        scene.render(p, QRectF(0, 0, 120, 120), QRectF(0, 0, 120, 120))
        p.end()
        return _pixel(img, 60, 60)

    c_80 = _render_rect_at_opacity(0.80)
    c_30 = _render_rect_at_opacity(0.30)

    lum_80 = _luminosity(c_80)
    lum_30 = _luminosity(c_30)

    assert lum_80 < lum_30, (
        f"0.8 opacity (lum={lum_80}) should be darker than 0.3 opacity (lum={lum_30})"
    )


def test_opacity_alpha_value_used_in_draw_fill(qapp):
    """Alpha passed to draw_fill must be int(round(fill_opacity * 255)).

    We intercept draw_fill to capture the alpha argument and verify it
    matches the expected formula for fill_opacity=0.6.
    """
    import firepro3d.construction_geometry as cg_mod
    import firepro3d.displayable_item as di_mod

    captured_alphas: list[int] = []

    original_draw_fill = di_mod.draw_fill

    def spy_draw_fill(painter, closed_path, scene, fill_type, pattern, colour,
                      alpha=115):
        captured_alphas.append(alpha)
        return original_draw_fill(painter, closed_path, scene, fill_type,
                                  pattern, colour, alpha)

    # Patch into the construction_geometry local namespace
    import firepro3d.displayable_item as _di
    original = _di.draw_fill

    # We need to patch in the module where it's imported (construction_geometry)
    # by patching the module-level name that paint() calls via "from .displayable_item import draw_fill"
    # Since it's imported at call time (inside paint()), we patch at the source module.
    _di.draw_fill = spy_draw_fill
    try:
        scene = QGraphicsScene()
        r = RectangleItem(QPointF(10, 10), QPointF(110, 110))
        r.fill_type = "solid"
        r._display_fill_color = "#0000ff"
        r.fill_opacity = 0.60
        scene.addItem(r)

        img = QImage(120, 120, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        scene.render(p, QRectF(0, 0, 120, 120), QRectF(0, 0, 120, 120))
        p.end()
    finally:
        _di.draw_fill = original

    expected_alpha = int(round(0.60 * 255))  # = 153
    assert len(captured_alphas) > 0, "draw_fill was never called (item may not have rendered)"
    assert captured_alphas[0] == expected_alpha, (
        f"Expected alpha={expected_alpha} for fill_opacity=0.60, got {captured_alphas[0]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Serialisation round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_to_dict_includes_opacity_for_solid(qapp):
    """to_dict must include 'opacity' in the fill block when fill_type='solid'."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    r._display_fill_color = "#112233"
    r.fill_opacity = 0.70

    d = r.to_dict()
    assert "fill" in d, "fill block must be present for solid fill"
    assert "opacity" in d["fill"], "'opacity' key must be in the fill block"
    assert d["fill"]["opacity"] == pytest.approx(0.70)


def test_from_dict_restores_opacity(qapp):
    """from_dict must restore fill_opacity from the 'opacity' key."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    r._display_fill_color = "#aabbcc"
    r.fill_opacity = 0.80

    d = r.to_dict()
    r2 = RectangleItem.from_dict(d)

    assert r2.fill_opacity == pytest.approx(0.80)


def test_from_dict_backcompat_missing_opacity_defaults_to_045(qapp):
    """A fill block without 'opacity' key must default fill_opacity to 0.45."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    r._display_fill_color = "#deadbe"
    r.fill_opacity = 0.80

    d = r.to_dict()
    # Simulate a pre-opacity serialized file by removing the key
    d["fill"].pop("opacity", None)

    r2 = RectangleItem.from_dict(d)
    assert r2.fill_opacity == pytest.approx(0.45), (
        f"Back-compat: missing opacity key must default to 0.45, got {r2.fill_opacity}"
    )


def test_opacity_not_in_dict_when_fill_none(qapp):
    """When fill_type='none', the fill block is omitted entirely."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "none"
    d = r.to_dict()
    assert "fill" not in d


def test_to_dict_includes_opacity_for_hatch_fill_block(qapp):
    """Hatch fill block should also include 'opacity' for forward-compat,
    even though draw_fill ignores it for hatch rendering."""
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "hatch"
    r._display_fill_color = "#336699"
    r.fill_opacity = 0.60  # stored but not used by hatch renderer

    d = r.to_dict()
    assert "fill" in d
    assert "opacity" in d["fill"]
    assert d["fill"]["opacity"] == pytest.approx(0.60)
