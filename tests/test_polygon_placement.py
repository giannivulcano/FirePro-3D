"""Tests for the 3-step polygon placement (centre → radius → rotate).

Feature 2: live readout (↑/↓ sides, ←/→ shape) at every step.
Feature 3: 3-step placement workflow mirroring draw_rectangle.
Feature 6: dashed reference circle during placement and when selected.

RED-VERIFY note: the 3-step tests (test_three_step_*) must FAIL against the
old 2-step code where step2 immediately committed.
"""
import math
import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QKeyEvent, QPainter
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtGui import QPixmap
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.construction_geometry import RegularPolygonItem


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def scene(qapp):
    return Model_Space()


@pytest.fixture
def view(scene):
    v = Model_View(scene)
    v.resize(800, 600)
    v.resetTransform()
    v.show()
    QTest.qWaitForWindowExposed(v)
    yield v
    v.close()


# ── Helper ────────────────────────────────────────────────────────────────────

def send_key(target, key):
    """Send a key press + release to ``target``."""
    for et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(target, QKeyEvent(et, key, Qt.KeyboardModifier.NoModifier))


# ── Feature 3: 3-step placement ───────────────────────────────────────────────

def test_three_step_click1_arms_center(scene):
    """Click 1 sets _polygon_center and does NOT create an item."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    assert scene._polygon_center == QPointF(0, 0)
    assert len(scene._draw_polygons) == 0
    assert not scene._polygon_rotating


def test_three_step_click2_sets_radius_and_enters_rotate(scene):
    """Click 2 stores _polygon_sized_radius and _polygon_rotating=True, no item yet."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)

    assert scene._polygon_rotating is True
    assert scene._polygon_sized_radius is not None
    assert math.isclose(scene._polygon_sized_radius, 100.0, abs_tol=1e-6)
    # No item committed yet
    assert len(scene._draw_polygons) == 0


def test_three_step_click2_does_not_commit(scene):
    """RED-VERIFY target: old 2-step code committed on click 2; new code must not."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert len(scene._draw_polygons) == 0, (
        "3-step: click 2 must NOT commit (only advances to rotate step)"
    )


def test_three_step_click3_commits_item(scene):
    """Click 3 commits a RegularPolygonItem with the correct radius."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0, 100), None, None, None)

    assert len(scene._draw_polygons) == 1
    poly = scene._draw_polygons[-1]
    assert isinstance(poly, RegularPolygonItem)
    assert math.isclose(poly._radius_mm, 100.0, abs_tol=1e-6)


def test_three_step_state_cleared_after_commit(scene):
    """All placement state cleared after step 3 commit."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0, 100), None, None, None)

    assert scene._polygon_center is None
    assert scene._polygon_rotating is False
    assert scene._polygon_sized_radius is None
    assert scene._polygon_preview is None
    assert scene.mode == "polygon"   # stays in placement mode


def test_three_step_rotation_ground_truth(scene):
    """Centre (0,0), radius click (100,0), rotate click (0,100) → rotation ≈ 90°.

    Y-up convention: atan2(-(0-100-0), 0-0) where cursor is (0,100), centre (0,0):
    atan2(-(100), 0) = atan2(-100, 0) = -90°... wait, let's think:
    cursor.y=100, center.y=0 → -(cursor.y - center.y) = -(100) = -100
    cursor.x=0, center.x=0 → 0
    atan2(-100, 0) = -90° ... but in Qt scene-space Y is DOWN.
    The formula is atan2(-(cursor.y - piv.y), cursor.x - piv.x) which gives
    Y-up convention: a cursor ABOVE center (negative Y in scene) gives positive angles.
    Here cursor (0,100) is BELOW center in Y-up, so rotation = -90°.
    We just verify the committed polygon matches _polygon_rotation_angle_to.
    """
    scene.set_mode("polygon")
    center = QPointF(0, 0)
    radius_click = QPointF(100, 0)
    rotate_click = QPointF(0, 100)

    scene._press_polygon(None, None, center, None, None, None)
    scene._press_polygon(None, None, radius_click, None, None, None)

    expected_angle = scene._polygon_rotation_angle_to(rotate_click)
    scene._press_polygon(None, None, rotate_click, None, None, None)

    poly = scene._draw_polygons[-1]
    assert math.isclose(poly._rotation_deg, expected_angle, abs_tol=1e-6), (
        f"Rotation {poly._rotation_deg!r} != expected {expected_angle!r}"
    )


def test_rotation_angle_to_east_is_zero(scene):
    """Cursor due-east of center → rotation 0°."""
    scene.set_mode("polygon")
    scene._polygon_center = QPointF(0, 0)
    assert math.isclose(scene._polygon_rotation_angle_to(QPointF(1, 0)), 0.0, abs_tol=1e-6)


def test_rotation_angle_to_north_is_positive_90(scene):
    """Cursor due-NORTH of center (negative Y in scene) → +90° in Y-up."""
    scene.set_mode("polygon")
    scene._polygon_center = QPointF(0, 0)
    # North = scene y < 0 → -(−1) = 1, atan2(1, 0) = 90°
    assert math.isclose(
        scene._polygon_rotation_angle_to(QPointF(0, -100)), 90.0, abs_tol=1e-6)


def test_ghost_is_axis_aligned_after_step2(scene):
    """After step 2 (radius locked), the ghost polygon has rotation_deg == 0."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)

    assert scene._polygon_rotating is True
    ghost = scene._polygon_preview
    assert ghost is not None
    # Ghost is built at rotation 0 (axis-aligned) during the rotate step entry.
    assert ghost._rotation_deg == 0.0


def test_radius_too_small_rejected_at_step1(scene):
    """Radius < 0.5 mm at step 1 keeps center armed, no advance to rotate step."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0.1, 0), None, None, None)
    assert len(scene._draw_polygons) == 0
    assert scene._polygon_rotating is False
    assert scene._polygon_center == QPointF(0, 0)


def test_continuous_placement_after_commit(scene):
    """After a 3-step commit the scene stays in polygon mode."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0, 100), None, None, None)
    assert scene.mode == "polygon"


# ── Feature 6: reference circle ───────────────────────────────────────────────

def test_ref_circle_created_after_step1(scene):
    """After step 1 (radius locked), _polygon_ref_circle is in scene and visible."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)

    assert scene._polygon_ref_circle is not None
    assert scene._polygon_ref_circle.scene() is scene
    assert scene._polygon_ref_circle.isVisible()


def test_ref_circle_removed_after_commit(scene):
    """After step 3 commit, _polygon_ref_circle is gone."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0, 100), None, None, None)

    assert scene._polygon_ref_circle is None


def test_ref_circle_created_during_sizing_step(scene):
    """During sizing step (after centre, before radius click), ref circle tracks cursor."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    # Simulate mouse move during sizing step
    scene._move_polygon(None, QPointF(80, 0))
    # A ref circle should be visible now
    assert scene._polygon_ref_circle is not None
    assert scene._polygon_ref_circle.scene() is scene


def test_ref_circle_removed_on_mode_change(scene):
    """Mode change clears ref circle."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert scene._polygon_ref_circle is not None

    scene.set_mode("select")
    assert scene._polygon_ref_circle is None


def test_selected_polygon_paint_runs_without_error(scene, qapp):
    """Paint with isSelected() draws the ref circle without raising."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0, 100), None, None, None)

    poly = scene._draw_polygons[-1]
    poly.setSelected(True)

    # Paint into an offscreen pixmap — must not raise.
    pix = QPixmap(300, 300)
    pix.fill(Qt.GlobalColor.black)
    painter = QPainter(pix)
    scene.render(painter)
    painter.end()


# ── Feature 2: live readout ───────────────────────────────────────────────────

def test_readout_helper_format(scene):
    """_polygon_readout returns expected format."""
    scene.set_mode("polygon")
    scene._polygon_sides = 8
    scene._polygon_inscribed = True
    out = scene._polygon_readout()
    assert "8 sides" in out
    assert "↑/↓" in out
    assert "inscribed" in out
    assert "←/→" in out


def test_instruction_emitted_on_mode_enter(scene):
    """Entering polygon mode emits an instruction with readout suffix."""
    emissions = []
    scene.instructionChanged.connect(emissions.append)
    scene.set_mode("polygon")
    assert any("↑/↓" in e for e in emissions), (
        f"No readout in instructions: {emissions}"
    )


def test_instruction_emitted_on_step0_click(scene):
    """Step 0 click (set centre) emits readout with 'radius'."""
    emissions = []
    scene.instructionChanged.connect(emissions.append)
    scene.set_mode("polygon")
    emissions.clear()
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    assert any("radius" in e.lower() for e in emissions), (
        f"Expected 'radius' in step-0 emission; got: {emissions}"
    )


def test_instruction_emitted_on_step1_advance(scene):
    """Step 1 advance (set radius) emits readout with 'rotation'."""
    emissions = []
    scene.instructionChanged.connect(emissions.append)
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    emissions.clear()
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert any("rotation" in e.lower() for e in emissions), (
        f"Expected 'rotation' in step-1 emission; got: {emissions}"
    )


def test_up_down_readout_contains_new_sides(scene):
    """↑ key: emitted instruction contains the new sides count."""
    scene.set_mode("polygon")
    scene._polygon_sides = 6
    emissions = []
    scene.instructionChanged.connect(emissions.append)
    scene._cycle_polygon_sides(+1)
    assert scene._polygon_sides == 7
    assert any("7 sides" in e for e in emissions), (
        f"Expected '7 sides' in emission; got {emissions}"
    )


def test_up_down_readout_contains_arrow_hint(scene):
    """↑/↓ key: emitted instruction contains '↑/↓'."""
    scene.set_mode("polygon")
    emissions = []
    scene.instructionChanged.connect(emissions.append)
    scene._cycle_polygon_sides(+1)
    assert any("↑/↓" in e for e in emissions)


def test_lr_toggle_readout_step_aware(scene):
    """←/→ toggle at step 2 emits 'rotation' in instruction."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert scene._polygon_rotating

    emissions = []
    scene.instructionChanged.connect(emissions.append)
    scene._toggle_polygon_inscribed()
    assert any("rotation" in e.lower() for e in emissions), (
        f"Expected 'rotation' in step-2 toggle emission; got: {emissions}"
    )


# ── Key routing (existing behavior preserved) ─────────────────────────────────

def test_default_sides_six(scene):
    scene.set_mode("polygon")
    assert scene._polygon_sides == 6


def test_sides_clamped_3_to_120(scene):
    scene.set_mode("polygon")
    scene._polygon_sides = 3
    scene._cycle_polygon_sides(-1)
    assert scene._polygon_sides == 3
    scene._polygon_sides = 120
    scene._cycle_polygon_sides(+1)
    assert scene._polygon_sides == 120


def test_up_down_change_sides_live(view, scene):
    scene.set_mode("polygon")
    send_key(view, Qt.Key.Key_Up)
    assert scene._polygon_sides == 7
    send_key(view, Qt.Key.Key_Down)
    send_key(view, Qt.Key.Key_Down)
    assert scene._polygon_sides == 5


def test_left_right_toggle_inscribed(view, scene):
    scene.set_mode("polygon")
    start = scene._polygon_inscribed
    send_key(view, Qt.Key.Key_Left)
    assert scene._polygon_inscribed is (not start)


# ── HUD schema step-awareness ─────────────────────────────────────────────────

def test_active_schema_sizing_step_is_polygon(scene):
    """active_schema() returns 'polygon' schema during sizing step."""
    from firepro3d.dynamic_input import SCHEMAS
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    assert not scene._polygon_rotating
    schema = scene.active_schema()
    assert schema is not None
    assert schema is SCHEMAS.get("polygon")


def test_active_schema_rotate_step_is_rotation(scene):
    """active_schema() returns 'rotation' schema during rotate step."""
    from firepro3d.dynamic_input import SCHEMAS
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert scene._polygon_rotating
    schema = scene.active_schema()
    assert schema is not None
    assert schema is SCHEMAS.get("rotation")


def test_hud_applier_registered(scene):
    """The polygon HUD applier is registered in _APPLIER_FOR_MODE."""
    assert "polygon" in scene._APPLIER_FOR_MODE
    assert scene._APPLIER_FOR_MODE["polygon"] == "_apply_polygon_dynamic_input"


def test_hud_radius_advances_to_rotate(scene):
    """Typing a radius through _apply_polygon_dynamic_input advances to rotate step."""
    from firepro3d.dynamic_input import SCHEMAS
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    # Resolve a radius-typed point via the polygon schema.
    poly_schema = SCHEMAS["polygon"]
    rim = poly_schema.resolve(QPointF(0, 0), {"Radius": 150.0})
    # Apply through the step-aware applier.
    result = scene._apply_polygon_dynamic_input(rim)
    assert result is True
    assert scene._polygon_rotating is True
    assert math.isclose(scene._polygon_sized_radius, 150.0, abs_tol=1e-6)
    assert len(scene._draw_polygons) == 0   # still no commit


def test_hud_angle_commits_polygon(scene):
    """Typing a rotation angle through _apply_polygon_dynamic_input commits the polygon."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert scene._polygon_rotating

    result = scene._apply_polygon_dynamic_input({"angle_deg": 45.0})
    assert result is True
    assert len(scene._draw_polygons) == 1
    poly = scene._draw_polygons[-1]
    assert math.isclose(poly._rotation_deg, 45.0, abs_tol=1e-6)


# ── Move dispatch ──────────────────────────────────────────────────────────────

def test_move_dispatch_registered(scene):
    assert scene._MOVE_DISPATCH.get("polygon") == "_move_polygon"


def test_move_creates_ghost_during_sizing(scene):
    """_move_polygon creates a preview ghost during sizing step."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._move_polygon(None, QPointF(100, 0))
    assert scene._polygon_preview is not None


def test_move_updates_ghost_during_rotate(scene):
    """_move_polygon rebuilds ghost with new angle during rotate step."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    assert scene._polygon_rotating
    scene._move_polygon(None, QPointF(0, -100))   # north → rotation ≈ 90°
    ghost = scene._polygon_preview
    assert ghost is not None
    # Ghost radius matches the fixed sized radius.
    assert math.isclose(ghost._radius_mm, 100.0, abs_tol=1e-6)


def test_commit_clears_ghost(scene):
    """Ghost cleared after 3-step commit."""
    scene.set_mode("polygon")
    scene._press_polygon(None, None, QPointF(0, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(100, 0), None, None, None)
    scene._press_polygon(None, None, QPointF(0, 100), None, None, None)
    assert scene._polygon_preview is None


# ── P shortcut (regression guard) ────────────────────────────────────────────

def test_p_shortcut_sets_polygon_mode(view, scene):
    """Posting Key_P to a focused Model_View must switch scene.mode to 'polygon'."""
    scene.set_mode("select")
    assert scene.mode != "polygon"
    view.setFocus()
    QApplication.processEvents()
    send_key(view, Qt.Key.Key_P)
    assert scene.mode == "polygon"


# ── Misc regression guards ────────────────────────────────────────────────────

def test_no_single_place_attribute(scene):
    assert not hasattr(scene, "single_place_mode")
