"""tests/test_dynamic_input_widget.py — HUD widget and Model_Space seam."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt

from firepro3d.construction_geometry import PolylineItem
from firepro3d.dynamic_input import SCHEMAS, DynamicInputHud
from firepro3d.model_space import Model_Space
from firepro3d.node import Node
from firepro3d.scale_manager import ScaleManager


@pytest.fixture
def scene(qapp):
    sc = Model_Space()
    yield sc


class _MoveEventStub:
    """Minimal stand-in for the mouse-move event ``_move_draw_line`` reads.

    ``QGraphicsSceneMouseEvent`` cannot be instantiated or sub-classed under
    PyQt6, so a real event cannot be built headlessly.  ``_move_draw_line``
    touches only ``modifiers()`` on the event (the position arrives as the
    separate ``snapped`` argument), so this covers the whole surface the
    handler uses.
    """

    def __init__(self, modifiers=Qt.KeyboardModifier.NoModifier):
        self._modifiers = modifiers

    def modifiers(self):
        return self._modifiers


class TestPlacementAnchor:

    def test_none_when_nothing_started(self, scene):
        scene.mode = "draw_line"
        assert scene.get_placement_anchor() is None

    def test_draw_line_anchor(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(10, 20)
        assert scene.get_placement_anchor() == QPointF(10, 20)

    def test_draw_gridline_shares_line_anchor(self, scene):
        scene.mode = "draw_gridline"
        scene._draw_line_anchor = QPointF(1, 2)
        assert scene.get_placement_anchor() == QPointF(1, 2)

    def test_rectangle_anchor(self, scene):
        scene.mode = "draw_rectangle"
        scene._draw_rect_anchor = QPointF(3, 4)
        assert scene.get_placement_anchor() == QPointF(3, 4)

    def test_circle_centre(self, scene):
        scene.mode = "draw_circle"
        scene._draw_circle_center = QPointF(5, 6)
        assert scene.get_placement_anchor() == QPointF(5, 6)

    def test_wall_anchor(self, scene):
        scene.mode = "wall"
        scene._wall_anchor = QPointF(7, 8)
        assert scene.get_placement_anchor() == QPointF(7, 8)

    def test_unknown_mode_is_none(self, scene):
        scene.mode = "select"
        scene._draw_line_anchor = QPointF(10, 20)
        assert scene.get_placement_anchor() is None

    def test_construction_line_is_out_of_scope(self, scene):
        """construction_line is excluded by design — no dynamic input."""
        scene.mode = "construction_line"
        scene._cline_anchor = QPointF(9, 9)
        assert scene.get_placement_anchor() is None

    # ── Branches with real logic ──────────────────────────────────────────

    def test_polyline_returns_last_vertex(self, scene):
        """The anchor is the most recent vertex, not the first."""
        pl = PolylineItem(QPointF(1, 1))
        pl.append_point(QPointF(2, 2))
        pl.append_point(QPointF(3, 3))
        scene.mode = "polyline"
        scene._polyline_active = pl
        assert scene.get_placement_anchor() == QPointF(3, 3)

    def test_polyline_none_when_no_active(self, scene):
        scene.mode = "polyline"
        scene._polyline_active = None
        assert scene.get_placement_anchor() is None

    def test_pipe_returns_node_scene_pos(self, scene):
        """pipe mode stores a Node; the anchor is its scene position.

        The Node sits off-origin so a bug returning a default QPointF()
        cannot pass.
        """
        scene.mode = "pipe"
        scene.node_start_pos = Node(5.0, 7.0)
        assert scene.get_placement_anchor() == QPointF(5.0, 7.0)

    def test_move_returns_raw_point(self, scene):
        """move mode stores a raw QPointF, not a Node."""
        scene.mode = "move"
        scene.node_start_pos = QPointF(11, 22)
        assert scene.get_placement_anchor() == QPointF(11, 22)

    def test_pipe_none_when_no_start_node(self, scene):
        scene.mode = "pipe"
        scene.node_start_pos = None
        assert scene.get_placement_anchor() is None

    # ── Aliasing ──────────────────────────────────────────────────────────

    def test_returned_point_is_a_copy(self, scene):
        """Callers may mutate the result without corrupting internal state."""
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(1, 2)
        a = scene.get_placement_anchor()
        a.setX(999)
        assert scene._draw_line_anchor == QPointF(1, 2)

        # The polyline branch reaches into the item — mutating the result
        # must not relocate an already-committed vertex.
        pl = PolylineItem(QPointF(1, 1))
        pl.append_point(QPointF(3, 4))
        scene.mode = "polyline"
        scene._polyline_active = pl
        b = scene.get_placement_anchor()
        b.setY(-777)
        assert pl._points[-1] == QPointF(3, 4)


class TestPublishPlacementState:

    def test_publishes_resolved_point_not_raw_cursor(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene._last_scene_pos = QPointF(500, -3)      # raw cursor
        constrained = QPointF(500, 0)                 # what Ctrl produced
        scene.publish_placement_state(QPointF(0, 0), constrained)
        assert scene.get_resolved_point() == constrained

    def test_move_draw_line_publishes_the_constrained_point(self, scene):
        """Drive the real handler: the published point must be Ctrl-snapped.

        The previous guard passed the constrained point into
        ``publish_placement_state`` by hand, so it could not tell a publish of
        ``tip`` from a publish of the raw ``snapped`` cursor.  Here the raw
        cursor sits a few degrees off horizontal — well inside the 45° snap —
        so the two points are numerically distinct and only the constrained
        one can satisfy the assertion.

        Driven via ``_move_draw_line`` with a ``_MoveEventStub`` rather than a
        real ``QGraphicsSceneMouseEvent``, which PyQt6 refuses to instantiate.
        """
        anchor = QPointF(0, 0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = anchor
        raw = QPointF(1000, -30)          # ~1.7° off horizontal
        scene._last_scene_pos = raw

        scene._move_draw_line(
            _MoveEventStub(Qt.KeyboardModifier.ControlModifier), raw)

        expected = scene._constrain_angle(anchor, raw)
        got = scene.get_resolved_point()
        assert got is not None
        assert got == expected
        # The constraint actually moved the point, so this is a real distinction.
        assert expected != raw
        assert got != raw

    def test_move_draw_line_readout_matches_the_constrained_point(self, scene):
        """The readout is derived from the same constrained point, not the raw one."""
        anchor = QPointF(0, 0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = anchor
        raw = QPointF(1000, -30)

        scene._move_draw_line(
            _MoveEventStub(Qt.KeyboardModifier.ControlModifier), raw)

        # Snapped to horizontal → 0°, not the raw cursor's ~1.7°.
        assert scene._draw_dim_hint == "L 1000.450 mm  A 0°"

    def test_sets_dim_hint_from_schema(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(1000, -1000))
        assert scene._draw_dim_hint == "L 1414.214 mm  A 45°"

    def test_dim_hint_honours_scale_calibration(self, scene):
        """Scene units are converted through the scene's own ScaleManager.

        This is the assertion that catches treating scene units as mm: at
        2 px/mm a 6000-scene-unit line is 3000 mm, and the readout must say so.
        """
        scene.scale_manager.set_pixels_per_mm(2.0)
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(6000, 0))
        hint = scene._draw_dim_hint
        assert "3000" in hint
        assert "6000" not in hint
        assert hint == "L 3000.000 mm  A 0°"

    def test_clear_resets_both(self, scene):
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        scene.clear_placement_state()
        assert scene.get_resolved_point() is None
        assert scene._draw_dim_hint is None

    def test_no_schema_mode_publishes_point_without_hint(self, scene):
        scene.mode = "select"
        scene.publish_placement_state(QPointF(0, 0), QPointF(9, 9))
        assert scene.get_resolved_point() == QPointF(9, 9)
        assert scene._draw_dim_hint is None

    def test_resolved_point_is_a_copy(self, scene):
        """Same aliasing guard as get_placement_anchor."""
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        p = QPointF(100, 0)
        scene.publish_placement_state(QPointF(0, 0), p)
        got = scene.get_resolved_point()
        got.setX(999)
        assert scene.get_resolved_point() == QPointF(100, 0)

    def test_gridline_replicate_teardown_drops_the_point(self, scene):
        """Cancelling replication must not leave the last point readable.

        ``_end_gridline_replicate`` returns to select mode, so without a full
        clear a caller reading ``get_resolved_point()`` before the next
        mouse-move would get the cancelled placement's point.
        """
        scene.mode = "draw_line"
        scene._draw_line_anchor = QPointF(0, 0)
        scene.publish_placement_state(QPointF(0, 0), QPointF(100, 0))
        assert scene.get_resolved_point() is not None

        scene._end_gridline_replicate()

        assert scene.get_resolved_point() is None
        assert scene._draw_dim_hint is None


@pytest.fixture
def sm_uncal(qapp):
    """A default, *uncalibrated* ScaleManager — the common real-world case."""
    return ScaleManager()


@pytest.fixture
def sm_cal(qapp):
    """A calibrated ScaleManager at 2 scene units per mm."""
    sm = ScaleManager()
    sm.set_pixels_per_mm(2.0)
    return sm


@pytest.fixture
def shown_hud(qapp, sm_uncal):
    """Build a HUD inside a shown host window so focus is really grantable.

    Focus assertions need a visible, activated top-level ancestor; an
    unparented widget cannot hand out keyboard focus headlessly.  This
    mirrors production, where the HUD is a child of a view's viewport.
    """
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    hosts = []

    def _make(schema, scale_manager=None):
        host = QWidget()
        QVBoxLayout(host)
        hud = DynamicInputHud(schema, scale_manager or sm_uncal, parent=host)
        host.layout().addWidget(hud)
        host.show()
        qapp.setActiveWindow(host)
        hosts.append(host)
        return hud

    yield _make

    for host in hosts:
        host.close()


class TestHudConstruction:

    def test_one_editor_per_field_in_order(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        assert hud.field_names() == ("Length", "Angle")
        # Distinct editors, and each resolvable by name.
        assert hud.editor("Length") is not hud.editor("Angle")

    def test_field_names_match_every_schema(self, sm_uncal):
        for schema in SCHEMAS.values():
            hud = DynamicInputHud(schema, sm_uncal)
            assert hud.field_names() == tuple(f.name for f in schema.fields)

    def test_schema_property_round_trips(self, sm_uncal):
        schema = SCHEMAS["circle"]
        assert DynamicInputHud(schema, sm_uncal).schema is schema

    def test_labels_are_shown(self, sm_uncal):
        """The caption beside each editor is the spec's short label."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        from PyQt6.QtWidgets import QLabel
        texts = [w.text() for w in hud.findChildren(QLabel)]
        assert texts == ["L", "A"]

    def test_unknown_field_name_raises(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        with pytest.raises(KeyError):
            hud.editor("Nope")

    def test_is_a_child_widget_not_a_window(self, sm_uncal):
        """Parented to a viewport it must be a plain child, not a dialog.

        Constructed with a real parent because *any* parentless QWidget is a
        top-level window by definition — the flags only mean something once
        it is parented the way ``Model_View`` will parent it.
        """
        from PyQt6.QtWidgets import QWidget
        host = QWidget()
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal, parent=host)
        assert hud.parent() is host
        assert not hud.isWindow()
        wtype = hud.windowFlags() & Qt.WindowType.WindowType_Mask
        assert wtype != Qt.WindowType.Dialog
        host.close()

    # ── Per-kind editor configuration ─────────────────────────────────────

    def test_angle_field_shows_degree_glyph(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 100.0, "Angle": 45.0})
        assert hud.editor("Angle").text() == "45°"

    def test_negative_angle_displays_signed(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 100.0, "Angle": -16.4})
        assert hud.editor("Angle").text() == "-16.4°"

    def test_count_field_shows_bare_integer(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["spacing_count"], sm_uncal)
        hud.set_values({"Spacing": 100.0, "Count": 3})
        text = hud.editor("Count").text()
        assert text == "3"
        assert "mm" not in text and "." not in text

    def test_dimension_field_uses_the_scale_managers_format(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        assert hud.editor("Length").text() == sm_uncal.format_length(1000.0)

    # ── focus_first ───────────────────────────────────────────────────────

    def test_focus_first_selects_all(self, shown_hud):
        """Focus lands on field 1 with its text selected for overwrite."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first()
        ed = hud.editor("Length")
        assert ed.hasFocus()
        assert ed.selectedText() == ed.text()

    def test_focus_first_with_seed_replaces_text(self, shown_hud):
        """Type-to-engage: the digit that opened the HUD lands in field 1."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first(seed="7")
        ed = hud.editor("Length")
        assert ed.hasFocus()
        assert ed.text() == "7"
        assert ed.selectedText() == ""          # cursor at end, not selected
        assert ed.cursorPosition() == 1

    def test_seeded_text_is_what_values_reads_back(self, shown_hud):
        """The seed must survive as a real edit, not be reverted as untouched."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first(seed="7")
        assert hud.values()["Length"] == pytest.approx(7.0)


class TestHudValues:

    def test_seed_then_read_round_trips(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1234.5, "Angle": 30.0})
        got = hud.values()
        assert got["Length"] == pytest.approx(1234.5)
        assert got["Angle"] == pytest.approx(30.0)

    def test_count_round_trips_as_a_number(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["spacing_count"], sm_uncal)
        hud.set_values({"Spacing": 500.0, "Count": 4})
        got = hud.values()
        assert got["Count"] == pytest.approx(4)
        assert got["Spacing"] == pytest.approx(500.0)

    def test_values_reads_typed_text_without_focus_leaving(self, sm_uncal):
        """The stale-seed guard: values() must force commit() on each field.

        ``editingFinished`` does not fire when the user presses Return with
        focus still in the field, so without a forced commit this returns the
        seeded 1000, not the typed 250.
        """
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.editor("Length").setText("250")
        assert hud.values()["Length"] == pytest.approx(250.0)

    def test_values_reads_typed_angle_without_focus_leaving(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.editor("Angle").setText("90")
        assert hud.values()["Angle"] == pytest.approx(90.0)

    # ── Validity ──────────────────────────────────────────────────────────

    def test_clean_hud_has_no_invalid_field(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.values()
        assert hud.has_invalid_field() is False

    def test_garbage_reverts_and_flags_invalid(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("banana")
        got = hud.values()
        assert got["Length"] == pytest.approx(1000.0)     # reverted
        assert hud.has_invalid_field() is True

    def test_value_failing_minimum_reverts_and_flags(self, sm_uncal):
        """Length has minimum=0.0 — strictly-greater, so 0 is rejected."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("0")
        got = hud.values()
        assert got["Length"] == pytest.approx(1000.0)
        assert hud.has_invalid_field() is True

    def test_negative_angle_is_accepted_and_not_flagged(self, sm_uncal):
        """Angles have no minimum, so negatives are legal input."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Angle").setText("-30")
        got = hud.values()
        assert got["Angle"] == pytest.approx(-30.0)
        assert hud.has_invalid_field() is False

    def test_negative_dimension_allowed_where_no_minimum(self, sm_uncal):
        """Rectangle X/Y are signed by design — a negative must not flag."""
        hud = DynamicInputHud(SCHEMAS["rectangle"], sm_uncal)
        hud.set_values({"X": 100.0, "Y": 100.0})
        hud.editor("X").setText("-250")
        got = hud.values()
        assert got["X"] == pytest.approx(-250.0)
        assert hud.has_invalid_field() is False

    def test_valid_entry_that_merely_reformats_is_not_flagged(self, sm_uncal):
        """The false-positive guard on a naive before/after text comparison.

        ``"3ft"`` is valid and parses to 914.4 mm, but the field redisplays it
        as ``"914.400 mm"`` — the text changes across commit even though
        nothing was rejected.  Comparing raw text would call this invalid.
        """
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        ed = hud.editor("Length")
        ed.setText("3ft")
        got = hud.values()
        assert got["Length"] == pytest.approx(914.4)
        assert ed.text() != "3ft"                  # it really did reformat
        assert hud.has_invalid_field() is False    # ...and that is not invalid

    def test_angle_reformat_is_not_flagged(self, sm_uncal):
        """``"45 deg"`` → ``"45°"`` is a reformat, not a rejection."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        ed = hud.editor("Angle")
        ed.setText("45 deg")
        got = hud.values()
        assert got["Angle"] == pytest.approx(45.0)
        assert ed.text() == "45°"
        assert hud.has_invalid_field() is False

    def test_invalid_flag_clears_on_the_next_read(self, sm_uncal):
        """The flag describes the latest read, not a sticky lifetime state."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("banana")
        hud.values()
        assert hud.has_invalid_field() is True
        hud.editor("Length").setText("500")
        hud.values()
        assert hud.has_invalid_field() is False

    def test_untouched_field_is_never_flagged(self, sm_uncal):
        """A seeded, untouched field commits as untouched — not as invalid."""
        hud = DynamicInputHud(SCHEMAS["rectangle"], sm_uncal)
        # Imperial display quantizes, so the seed guard matters here.
        hud.set_values({"X": 1234.567, "Y": -890.1})
        got = hud.values()
        assert got["X"] == pytest.approx(1234.567)
        assert got["Y"] == pytest.approx(-890.1)
        assert hud.has_invalid_field() is False


class TestHudUnitsBoundary:
    """The F7 trap: schemas speak scene units, DimensionEdit speaks mm."""

    def test_uncalibrated_round_trips_scene_units(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 6000.0, "Angle": 0.0})
        assert hud.values()["Length"] == pytest.approx(6000.0)

    def test_uncalibrated_display_matches_the_canvas_readout(self, sm_uncal, scene):
        """Uncalibrated, 1 scene unit is shown as 1 mm — same as the readout."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 6000.0, "Angle": 0.0})
        assert hud.editor("Length").text() == sm_uncal.scene_to_display(6000.0)
        assert hud.editor("Length").text() == "6000.000 mm"

    def test_calibrated_displays_mm_but_returns_scene_units(self, sm_cal):
        """At 2 px/mm a 6000-scene-unit length is 3000 mm on screen.

        The editor must *show* 3000 mm (agreeing with the canvas readout) yet
        ``values()`` must hand back 6000 scene units for the resolver.
        """
        hud = DynamicInputHud(SCHEMAS["line"], sm_cal)
        hud.set_values({"Length": 6000.0, "Angle": 0.0})
        text = hud.editor("Length").text()
        assert "3000" in text
        assert "6000" not in text
        assert hud.values()["Length"] == pytest.approx(6000.0)

    def test_calibrated_display_matches_the_canvas_readout(self, sm_cal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_cal)
        hud.set_values({"Length": 6000.0, "Angle": 0.0})
        assert hud.editor("Length").text() == sm_cal.scene_to_display(6000.0)

    def test_calibrated_typed_mm_converts_back_to_scene_units(self, sm_cal):
        """The user types display mm; the resolver receives scene units."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_cal)
        hud.set_values({"Length": 6000.0, "Angle": 0.0})
        hud.editor("Length").setText("1500 mm")
        assert hud.values()["Length"] == pytest.approx(3000.0)   # 1500 mm × 2

    def test_calibrated_minimum_is_applied_in_scene_units(self, sm_cal):
        """A 0.0 scene minimum must still reject 0 once scaled into mm."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_cal)
        hud.set_values({"Length": 6000.0, "Angle": 0.0})
        hud.editor("Length").setText("0")
        assert hud.values()["Length"] == pytest.approx(6000.0)
        assert hud.has_invalid_field() is True

    def test_angle_and_count_are_never_scaled(self, sm_cal):
        """Dimensionless kinds pass through calibration untouched."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_cal)
        hud.set_values({"Length": 6000.0, "Angle": 45.0})
        assert hud.editor("Angle").text() == "45°"
        assert hud.values()["Angle"] == pytest.approx(45.0)

        hud2 = DynamicInputHud(SCHEMAS["spacing_count"], sm_cal)
        hud2.set_values({"Spacing": 6000.0, "Count": 3})
        assert hud2.editor("Count").text() == "3"
        assert hud2.values()["Count"] == pytest.approx(3)

    def test_works_without_a_scale_manager(self, qapp):
        """A None scale manager degrades to 1 scene unit == 1 mm."""
        hud = DynamicInputHud(SCHEMAS["line"], None)
        hud.set_values({"Length": 250.0, "Angle": 0.0})
        assert hud.values()["Length"] == pytest.approx(250.0)
