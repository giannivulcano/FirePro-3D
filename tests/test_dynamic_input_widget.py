"""tests/test_dynamic_input_widget.py — the ``DynamicInputHud`` widget.

Construction, seeding, value reads, invalid styling and key routing.  The
``Model_Space`` seam (anchors and placement state) lives in
``tests/test_dynamic_input_seam.py``.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest

from firepro3d.dynamic_input import SCHEMAS, DynamicInputHud
from firepro3d.scale_manager import ScaleManager


def _type(editor, text: str) -> None:
    """Replace *editor*'s text the way a user would, emitting ``textEdited``.

    ``setText`` is a programmatic set and deliberately does *not* emit
    ``textEdited``, so it cannot stand in for typing where the distinction
    matters (the HUD clears a field's sticky invalid flag on user edits only).
    """
    editor.selectAll()
    QTest.keyClicks(editor, text)


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

    def test_invalid_flag_clears_once_the_user_edits_again(self, sm_uncal):
        """The flag clears when the user retypes — not merely on a re-read."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        ed = hud.editor("Length")
        ed.setText("banana")
        hud.values()
        assert hud.has_invalid_field() is True
        _type(ed, "500")
        hud.values()
        assert hud.has_invalid_field() is False

    def test_invalid_flag_is_sticky_across_repeated_reads(self, sm_uncal):
        """C1: a second ``values()`` must not launder rejected input.

        The first read reverts the field to its last valid text, so a
        validity check re-derived from the *current* text sees clean input
        and reports valid.  Task 7's Enter handler calls ``values()``
        per keypress: Enter #1 refuses, Enter #2 would commit geometry the
        user never typed.  The flag must survive until the user edits.
        """
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("banana")

        first = hud.values()
        assert hud.has_invalid_field() is True

        second = hud.values()
        assert hud.has_invalid_field() is True
        assert second["Length"] == pytest.approx(first["Length"])

    def test_invalid_flag_is_sticky_for_a_below_minimum_entry(self, sm_uncal):
        """Same stickiness for the minimum-rejection path, not just parse."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("0")
        hud.values()
        hud.values()
        assert hud.has_invalid_field() is True

    def test_set_values_reseed_clears_the_sticky_flag(self, sm_uncal):
        """A fresh seed replaces the rejected text, so the flag must drop."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("banana")
        hud.values()
        assert hud.has_invalid_field() is True
        hud.set_values({"Length": 2000.0, "Angle": 45.0})
        assert hud.has_invalid_field() is False
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


class TestHudInvalidStyling:
    """I1: the rejection must be *visible*, not just recorded.

    Without a border change Enter #1 produces no observable feedback at all,
    which makes pressing Enter again the natural response — exactly the input
    that used to slip a never-typed value through.
    """

    def test_property_starts_false(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        assert hud.editor("Length").property("invalid") == "false"

    def test_property_is_set_on_rejection(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("banana")
        hud.values()
        assert hud.editor("Length").property("invalid") == "true"
        # The accepted sibling must not be tarred with it.
        assert hud.editor("Angle").property("invalid") == "false"

    def test_property_survives_a_second_read(self, sm_uncal):
        """Paired with the sticky flag: the border must not silently clear."""
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("banana")
        hud.values()
        hud.values()
        assert hud.editor("Length").property("invalid") == "true"

    def test_property_clears_when_the_user_retypes(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        ed = hud.editor("Length")
        ed.setText("banana")
        hud.values()
        assert ed.property("invalid") == "true"
        _type(ed, "500")
        assert ed.property("invalid") == "false"

    def test_property_clears_on_reseed(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Length").setText("banana")
        hud.values()
        hud.set_values({"Length": 2000.0, "Angle": 45.0})
        assert hud.editor("Length").property("invalid") == "false"

    def test_the_stylesheet_actually_carries_an_invalid_rule(self, sm_uncal):
        """The QSS hazard: a property selector with no rule fails invisibly.

        Setting ``invalid`` is inert unless a matching rule exists, and Qt
        gives no warning for the missing half — it just renders as the base
        state.  Assert the rule is present and coloured from the theme.
        """
        from firepro3d import theme

        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        qss = hud.styleSheet()
        assert 'QLineEdit[invalid="true"]' in qss
        assert theme.detect().status_error in qss

    def test_stylesheet_is_built_from_theme_tokens(self, sm_uncal):
        """I3: no hard-coded hexes — every colour traces to a theme token."""
        import re

        from firepro3d import theme

        t = theme.detect()
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        qss = hud.styleSheet()
        known = {t.bg_raised, t.bg_sunken, t.border_strong, t.accent_primary,
                 t.text_primary, t.text_secondary, t.status_error}
        found = set(re.findall(r"#[0-9a-fA-F]{6}", qss))
        assert found                      # it really is colouring something
        assert found <= known, f"untokenised literals: {found - known}"

    def test_light_variant_produces_readable_light_colours(self, sm_uncal):
        """I3: the HUD is not hard-wired dark — it follows the variant.

        Built from ``_build_hud_style`` directly rather than by swapping the
        application palette, which would leak the light theme into every later
        test in the session.
        """
        from firepro3d import theme
        from firepro3d.dynamic_input import _build_hud_style

        light = _build_hud_style(theme.LIGHT)
        assert theme.LIGHT.bg_sunken in light           # "#ffffff"
        assert theme.LIGHT.status_error in light
        assert theme.DARK.bg_sunken not in light        # no dark leftovers


class TestCountRounding:
    """I2: a fractional count is rounded, deliberately, and not flagged."""

    def test_fractional_count_rounds_without_flagging(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["spacing_count"], sm_uncal)
        hud.set_values({"Spacing": 500.0, "Count": 2})
        hud.editor("Count").setText("2.6")
        assert hud.values()["Count"] == pytest.approx(3)
        assert hud.has_invalid_field() is False
        # The substitution is shown back to the user, not hidden.
        assert hud.editor("Count").text() == "3"

    def test_unparseable_count_still_reverts_and_flags(self, sm_uncal):
        """Rounding tolerance stops at numbers — junk is still rejected."""
        hud = DynamicInputHud(SCHEMAS["spacing_count"], sm_uncal)
        hud.set_values({"Spacing": 500.0, "Count": 2})
        hud.editor("Count").setText("three")
        assert hud.values()["Count"] == pytest.approx(2)
        assert hud.has_invalid_field() is True


class TestHudUnitsBoundary:
    """The F7 trap: schemas speak scene units, DimensionEdit speaks mm."""

    def test_uncalibrated_round_trips_scene_units(self, sm_uncal):
        hud = DynamicInputHud(SCHEMAS["line"], sm_uncal)
        hud.set_values({"Length": 6000.0, "Angle": 0.0})
        assert hud.values()["Length"] == pytest.approx(6000.0)

    def test_uncalibrated_display_matches_the_canvas_readout(self, sm_uncal):
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


class TestHudKeys:
    """Task 7: Tab / Shift+Tab / Enter / Escape routing.

    Every test drives a **real** key event through ``QTest``.  Calling the
    slots directly would pass while the wiring was dead — and for Escape it
    would bypass the very thing under test, the window-level ``QShortcut`` in
    ``main.py`` that Escape must be stolen back from.
    """

    # ── Tab / Shift+Tab ───────────────────────────────────────────────────

    def test_tab_advances_to_the_next_field(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Tab)
        assert hud.editor("Angle").hasFocus()

    def test_tab_wraps_from_the_last_field_to_the_first(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Angle").setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Tab)
        assert hud.editor("Length").hasFocus()

    def test_shift_tab_reverses(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Angle").setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Backtab,
                       Qt.KeyboardModifier.ShiftModifier)
        assert hud.editor("Length").hasFocus()

    def test_shift_tab_wraps_backwards_from_the_first_field(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Backtab,
                       Qt.KeyboardModifier.ShiftModifier)
        assert hud.editor("Angle").hasFocus()

    def test_tab_commits_the_field_being_left(self, shown_hud):
        """Typed text must take effect on Tab, not revert as a stale seed."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "250")
        QTest.keyClick(ed, Qt.Key.Key_Tab)
        assert ed.value_mm() == pytest.approx(250.0)

    def test_tab_emits_field_committed(self, shown_hud):
        """Tab out of a field fires ``fieldCommitted`` for the preview seam."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        seen = []
        hud.fieldCommitted.connect(lambda: seen.append(True))
        ed = hud.editor("Length")
        _type(ed, "1200")
        QTest.keyClick(ed, Qt.Key.Key_Tab)
        assert seen, "Tab out of a field must emit fieldCommitted"

    def test_current_values_reads_without_committing_or_flagging(self,
                                                                 shown_hud):
        """``current_values`` reflects the edited field, leaves neighbours
        at their seed, and never sets an invalid flag."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 800.0, "Angle": 30.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "1200")
        QTest.keyClick(ed, Qt.Key.Key_Tab)
        vals = hud.current_values()
        assert vals["Length"] == pytest.approx(1200.0)
        assert vals["Angle"] == pytest.approx(30.0)   # still the seed
        assert not hud.has_invalid_field()

    def test_current_values_does_not_flag_a_half_typed_neighbour(self,
                                                                 shown_hud):
        """Reading current_values must not launder an unparseable neighbour
        into an invalid mark (the whole point of the non-destructive read)."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 800.0, "Angle": 30.0})
        # Leave a garbage neighbour un-committed; DimensionEdit reverts it to
        # last-valid on focus-out, so current_values reads clean without flags.
        hud.current_values()
        assert not hud.has_invalid_field()

    def test_tab_selects_all_in_the_field_it_lands_on(self, shown_hud):
        """The new field is ready for overwrite, matching ``focus_first``."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Tab)
        ed = hud.editor("Angle")
        assert ed.selectedText() == ed.text()

    def test_tab_in_a_single_field_schema_stays_put(self, shown_hud):
        """Wrapping a one-field schema returns to the same editor."""
        hud = shown_hud(SCHEMAS["circle"])
        hud.set_values({"Radius": 500.0})
        hud.focus_first()
        QTest.keyClick(hud.editor("Radius"), Qt.Key.Key_Tab)
        assert hud.editor("Radius").hasFocus()

    # ── Space must reach the editor ───────────────────────────────────────

    def test_space_types_a_literal_space(self, shown_hud):
        """``12' 6"`` is unreachable if the filter swallows Space."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first()
        ed = hud.editor("Length")
        ed.selectAll()
        QTest.keyClicks(ed, "12'")
        QTest.keyClick(ed, Qt.Key.Key_Space)
        QTest.keyClicks(ed, "6\"")
        assert ed.text() == "12' 6\""

    def test_space_separated_feet_inches_commits(self, shown_hud):
        """End to end: the typed imperial string parses on Enter."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first()
        ed = hud.editor("Length")
        ed.selectAll()
        QTest.keyClicks(ed, "12'")
        QTest.keyClick(ed, Qt.Key.Key_Space)
        QTest.keyClicks(ed, "6\"")

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(ed, Qt.Key.Key_Return)

        assert len(got) == 1
        assert got[0]["Length"] == pytest.approx(12 * 304.8 + 6 * 25.4)

    # ── Enter ─────────────────────────────────────────────────────────────

    def test_enter_emits_committed_once_with_the_typed_value(self, shown_hud):
        """The Enter-ordering guard.

        ``editingFinished`` does not fire while focus stays in the field, so a
        handler reading ``value_mm()`` directly would emit the seeded 1000
        rather than the typed 250.
        """
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "250")

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(ed, Qt.Key.Key_Return)

        assert len(got) == 1
        assert got[0]["Length"] == pytest.approx(250.0)
        assert got[0]["Angle"] == pytest.approx(45.0)

    def test_enter_key_enter_also_commits(self, shown_hud):
        """The numeric-keypad Enter is the same accept."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Enter)
        assert len(got) == 1

    def test_enter_does_not_emit_cancelled(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        cancels = []
        hud.cancelled.connect(lambda: cancels.append(1))
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Return)
        assert cancels == []

    def test_enter_from_the_second_field_commits_both(self, shown_hud):
        """Committing reads every field, not just the focused one."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first()
        _type(hud.editor("Length"), "250")
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Tab)
        _type(hud.editor("Angle"), "30")

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Return)

        assert len(got) == 1
        assert got[0]["Length"] == pytest.approx(250.0)
        assert got[0]["Angle"] == pytest.approx(30.0)

    def test_enter_with_an_invalid_field_emits_nothing(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "banana")

        got = []
        cancels = []
        hud.committed.connect(got.append)
        hud.cancelled.connect(lambda: cancels.append(1))
        QTest.keyClick(ed, Qt.Key.Key_Return)

        assert got == []
        assert cancels == []
        assert hud.has_invalid_field() is True

    def test_enter_twice_with_an_invalid_field_still_emits_nothing(
            self, shown_hud):
        """The sticky-``_invalid`` regression guard.

        Enter #1 reverts the field to clean text, so a validity check derived
        from the current text would pass on Enter #2 and commit geometry the
        user never typed.
        """
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "banana")

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(ed, Qt.Key.Key_Return)
        QTest.keyClick(ed, Qt.Key.Key_Return)

        assert got == []
        assert hud.has_invalid_field() is True

    def test_enter_commits_once_the_user_fixes_the_invalid_field(
            self, shown_hud):
        """Retyping retires the flag, so the next Enter goes through."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "banana")

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(ed, Qt.Key.Key_Return)
        assert got == []

        _type(ed, "250")
        QTest.keyClick(ed, Qt.Key.Key_Return)
        assert len(got) == 1
        assert got[0]["Length"] == pytest.approx(250.0)

    # ── Tab must not launder a rejected field ─────────────────────────────

    def test_tab_past_an_invalid_field_cannot_launder_it(self, shown_hud):
        """``try_commit()`` is stateful, so the Tab-time verdict is the record.

        The first ``try_commit()`` on ``banana`` rejects *and reverts* the text
        to the last valid value, re-seeding the editor.  A later ``values()``
        therefore finds clean text and returns True — so if Tab did not record
        its own reject verdict, Enter would commit the seeded 1000 as though
        the user had typed it.
        """
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        _type(hud.editor("Length"), "banana")
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Tab)
        assert hud.has_invalid_field() is True

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Return)
        assert got == []

    def test_tab_past_a_below_minimum_field_cannot_launder_it(self, shown_hud):
        """Same laundering, via the ``minimum`` reject path rather than parse.

        ``Radius`` has ``minimum=0.0`` (strictly greater), so ``0`` parses
        cleanly yet is still refused.  Single-field schema, so Tab wraps onto
        the same editor — the verdict must survive that too.
        """
        hud = shown_hud(SCHEMAS["circle"])
        hud.set_values({"Radius": 500.0})
        hud.focus_first()
        _type(hud.editor("Radius"), "0")
        QTest.keyClick(hud.editor("Radius"), Qt.Key.Key_Tab)
        assert hud.has_invalid_field() is True

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(hud.editor("Radius"), Qt.Key.Key_Return)
        assert got == []

    # ── Escape ────────────────────────────────────────────────────────────

    def test_escape_emits_cancelled_and_not_committed(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        got = []
        cancels = []
        hud.committed.connect(got.append)
        hud.cancelled.connect(lambda: cancels.append(1))

        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Escape)

        assert cancels == [1]           # exactly once
        assert got == []

    def test_escape_after_typing_discards_rather_than_commits(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "250")

        got = []
        cancels = []
        hud.committed.connect(got.append)
        hud.cancelled.connect(lambda: cancels.append(1))
        QTest.keyClick(ed, Qt.Key.Key_Escape)

        assert cancels == [1]
        assert got == []

    # ── Modifier gating: the two branches must agree ──────────────────────

    def test_ctrl_escape_does_not_cancel(self, shown_hud):
        """``eventFilter`` only claims the override for *bare* Escape.

        If ``_handle_key`` acted on Ctrl+Escape anyway the HUD would cancel on
        a combination it never claimed, so the same keystroke could reach
        either the HUD or a window shortcut depending on focus.
        """
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        cancels = []
        hud.cancelled.connect(lambda: cancels.append(1))
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Escape,
                       Qt.KeyboardModifier.ControlModifier)
        assert cancels == []

    def test_shift_escape_does_not_cancel(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        cancels = []
        hud.cancelled.connect(lambda: cancels.append(1))
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Escape,
                       Qt.KeyboardModifier.ShiftModifier)
        assert cancels == []

    def test_ctrl_tab_does_not_step_fields(self, shown_hud):
        """Ctrl+Tab is left to Qt, not treated as a plain field step."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Tab,
                       Qt.KeyboardModifier.ControlModifier)
        assert not hud.editor("Angle").hasFocus()

    def test_ctrl_enter_does_not_commit(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Return,
                       Qt.KeyboardModifier.ControlModifier)
        assert got == []

    def test_shift_tab_still_steps_backwards(self, shown_hud):
        """The one legitimate modifier survives the gating."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Angle").setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Backtab,
                       Qt.KeyboardModifier.ShiftModifier)
        assert hud.editor("Length").hasFocus()

    # ── Numpad: KeypadModifier is not a real modifier ─────────────────────
    #
    # ``Model_Space.keyPressEvent`` accepts ``KeypadModifier`` on the engage
    # branch, so numpad *digits* open the HUD.  Every key the HUD acts on has
    # to accept it too, or a user who typed the value on the numpad cannot
    # commit it from there — the keypad Enter would fall through to the
    # editor and do nothing.

    def test_numpad_enter_commits(self, shown_hud):
        """Numpad Enter arrives with ``KeypadModifier`` set and must accept."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "250")

        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(ed, Qt.Key.Key_Enter,
                       Qt.KeyboardModifier.KeypadModifier)

        assert len(got) == 1
        assert got[0]["Length"] == pytest.approx(250.0)

    def test_numpad_return_commits(self, shown_hud):
        """Some layouts report the keypad accept key as ``Key_Return``."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Return,
                       Qt.KeyboardModifier.KeypadModifier)
        assert len(got) == 1

    def test_numpad_tab_steps_fields(self, shown_hud):
        """Guards the masking, not a specific keyboard.

        Qt sets ``KeypadModifier`` from the native scan code, and which keys
        a given platform/layout flags is not something this codebase can
        control — so ``Key_Tab`` with the flag set is treated as reachable
        and must behave exactly like a bare Tab.
        """
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Tab,
                       Qt.KeyboardModifier.KeypadModifier)
        assert hud.editor("Angle").hasFocus()

    def test_numpad_escape_cancels(self, shown_hud):
        """Masking is uniform: no branch is left gating on the raw modifier."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        cancels = []
        hud.cancelled.connect(lambda: cancels.append(1))
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Escape,
                       Qt.KeyboardModifier.KeypadModifier)
        assert cancels == [1]

    def test_ctrl_numpad_enter_still_does_not_commit(self, shown_hud):
        """Masking removes only the keypad bit; real modifiers still gate."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.focus_first()
        got = []
        hud.committed.connect(got.append)
        QTest.keyClick(hud.editor("Length"), Qt.Key.Key_Enter,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.KeypadModifier)
        assert got == []

    def test_shift_numpad_tab_steps_backwards(self, shown_hud):
        """Shift survives the mask, so Shift+Tab still reverses."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 45.0})
        hud.editor("Angle").setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Tab,
                       Qt.KeyboardModifier.ShiftModifier
                       | Qt.KeyboardModifier.KeypadModifier)
        assert hud.editor("Length").hasFocus()

    # ── ShortcutOverride: stealing Escape from the window QShortcut ───────

    def test_shortcut_override_is_accepted_for_escape(self, shown_hud):
        """``main.py`` binds Escape window-wide via ``QShortcut``.

        A window shortcut beats a focused widget unless that widget accepts
        the ``ShortcutOverride`` event, so without this Escape would never
        reach the HUD and would cancel the whole placement mode instead.
        """
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtWidgets import QApplication

        hud = shown_hud(SCHEMAS["line"])
        hud.focus_first()
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Escape,
                       Qt.KeyboardModifier.NoModifier)
        ev.setAccepted(False)
        QApplication.sendEvent(hud.editor("Length"), ev)
        assert ev.isAccepted()

    def test_ctrl_z_override_verdict_is_left_to_the_line_edit(self, shown_hud):
        """The filter must not *change* the verdict on Ctrl+Z.

        ``QLineEdit`` already accepts ``ShortcutOverride`` for Ctrl+Z on its
        own — that is how text undo keeps working inside a focused field, and
        it is the behaviour we want in input mode (scene undo is a cursor-mode
        concern).  So the assertion is not "unaccepted" but "identical to a
        bare ``QLineEdit``": the filter adds nothing and takes nothing away.
        A hand-written "not accepted" expectation here would be asserting the
        *breakage* of in-field text undo.
        """
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtWidgets import QApplication, QLineEdit

        hud = shown_hud(SCHEMAS["line"])
        hud.focus_first()

        def _verdict(widget):
            ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Z,
                           Qt.KeyboardModifier.ControlModifier)
            ev.setAccepted(False)
            QApplication.sendEvent(widget, ev)
            return ev.isAccepted()

        baseline = QLineEdit(hud)
        assert _verdict(hud.editor("Length")) == _verdict(baseline)

    def test_escape_override_is_the_only_verdict_the_filter_changes(
            self, shown_hud):
        """Escape is the one key whose verdict the HUD flips.

        Compared against a bare ``QLineEdit`` so the test pins the *delta* the
        filter introduces rather than restating Qt's built-in behaviour: only
        Escape may differ, and it must differ in the accepting direction.
        """
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtWidgets import QApplication, QLineEdit

        hud = shown_hud(SCHEMAS["line"])
        hud.focus_first()
        baseline = QLineEdit(hud)

        def _verdict(widget, key, mod):
            ev = QKeyEvent(QEvent.Type.ShortcutOverride, key, mod)
            ev.setAccepted(False)
            QApplication.sendEvent(widget, ev)
            return ev.isAccepted()

        no_mod = Qt.KeyboardModifier.NoModifier
        ctrl = Qt.KeyboardModifier.ControlModifier
        others = [("Delete", Qt.Key.Key_Delete, no_mod),
                  ("Ctrl+C", Qt.Key.Key_C, ctrl),
                  ("Ctrl+V", Qt.Key.Key_V, ctrl),
                  ("Ctrl+A", Qt.Key.Key_A, ctrl),
                  ("F3", Qt.Key.Key_F3, no_mod)]
        for name, key, mod in others:
            assert _verdict(hud.editor("Length"), key, mod) == \
                _verdict(baseline, key, mod), f"filter changed verdict for {name}"

        # Escape is the exception, and the bare editor really did decline it.
        assert _verdict(baseline, Qt.Key.Key_Escape, no_mod) is False
        assert _verdict(hud.editor("Length"), Qt.Key.Key_Escape, no_mod) is True

    # ── Ordinary keys still reach the editor ──────────────────────────────

    def test_letters_and_digits_fall_through(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first()
        ed = hud.editor("Length")
        ed.selectAll()
        QTest.keyClicks(ed, "3ft")
        assert ed.text() == "3ft"

    def test_backspace_still_edits(self, shown_hud):
        hud = shown_hud(SCHEMAS["line"])
        hud.set_values({"Length": 1000.0, "Angle": 0.0})
        hud.focus_first()
        ed = hud.editor("Length")
        ed.selectAll()
        QTest.keyClicks(ed, "250")
        QTest.keyClick(ed, Qt.Key.Key_Backspace)
        assert ed.text() == "25"


class TestHudSessionUndo:
    """Ctrl+Z belongs to the HUD for the whole placement (decision S3).

    ``DimensionEdit._reformat`` calls ``setText`` on every commit, and
    ``QLineEdit.setText`` clears the widget's own undo history — so the
    built-in per-field undo is wiped by every focus change and every Tab.
    The HUD therefore keeps the stack itself: one stack for the session,
    stepping back through the edits in the order they were made, and moving
    focus to the field each edit belonged to.
    """

    def _hud(self):
        hud = DynamicInputHud(SCHEMAS["line"], ScaleManager())
        hud.set_values({"Length": 100.0, "Angle": 0.0})
        hud.show()
        # hasFocus() is False unless the window is active, so the focus
        # assertion below would fail for a harness reason rather than a real
        # one.  Exposing and activating makes it answer about the widget.
        QTest.qWaitForWindowExposed(hud)
        hud.activateWindow()
        hud.focus_first()
        return hud

    def _ctrl_z(self, hud, editor):
        QTest.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    def test_undo_restores_the_previous_value(self, qapp):
        hud = self._hud()
        ed = hud.editor("Length")
        ed.setText("250")
        ed.try_commit()
        assert hud.values()["Length"] == pytest.approx(250.0)

        self._ctrl_z(hud, ed)
        assert hud.values()["Length"] == pytest.approx(100.0)

    def test_undo_survives_a_focus_round_trip(self, qapp):
        """The reported bug: typing, losing focus, then Ctrl+Z did nothing."""
        hud = self._hud()
        ed = hud.editor("Length")
        ed.setText("250")
        ed.try_commit()                      # what focus-out does
        hud.editor("Angle").setFocus()       # focus leaves the field
        hud.restore_focus()                  # and comes back

        self._ctrl_z(hud, hud.editor("Length"))
        assert hud.values()["Length"] == pytest.approx(100.0)

    def test_undo_moves_focus_to_the_field_it_undid(self, qapp):
        hud = self._hud()
        angle = hud.editor("Angle")
        angle.setText("45")
        angle.try_commit()
        length = hud.editor("Length")
        length.setFocus()

        self._ctrl_z(hud, length)
        assert hud.values()["Angle"] == pytest.approx(0.0)
        assert angle.hasFocus()

    def test_undo_steps_back_through_edits_in_order(self, qapp):
        hud = self._hud()
        length, angle = hud.editor("Length"), hud.editor("Angle")
        length.setText("250")
        length.try_commit()
        angle.setText("45")
        angle.try_commit()

        self._ctrl_z(hud, angle)
        assert hud.values()["Angle"] == pytest.approx(0.0)
        assert hud.values()["Length"] == pytest.approx(250.0)

        self._ctrl_z(hud, hud.editor("Length"))
        assert hud.values()["Length"] == pytest.approx(100.0)

    def test_undo_stops_at_the_seeded_state(self, qapp):
        hud = self._hud()
        ed = hud.editor("Length")
        ed.setText("250")
        ed.try_commit()
        for _ in range(5):
            self._ctrl_z(hud, ed)
        assert hud.values()["Length"] == pytest.approx(100.0)

    def test_undo_is_swallowed_so_it_never_reaches_scene_undo(self, qapp):
        """Even with nothing to undo, Ctrl+Z must not fall through."""
        hud = self._hud()
        ed = hud.editor("Length")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z,
                          Qt.KeyboardModifier.ControlModifier)
        assert hud.eventFilter(ed, event) is True


class TestHudUndoDiscardsTypingFirst:
    """Undo starts with the half-typed text, then walks committed edits.

    The HUD consumes Ctrl+Z before QLineEdit sees it, so the widget's own
    within-field text undo is no longer reachable.  Undo therefore has to
    cover the uncommitted case itself, or typing "250" and pressing Ctrl+Z
    before Tab would silently do nothing.
    """

    def _hud(self):
        hud = DynamicInputHud(SCHEMAS["line"], ScaleManager())
        hud.set_values({"Length": 100.0, "Angle": 0.0})
        hud.show()
        QTest.qWaitForWindowExposed(hud)
        hud.activateWindow()
        hud.focus_first()
        return hud

    def test_uncommitted_typing_is_discarded_first(self, qapp):
        hud = self._hud()
        ed = hud.editor("Length")
        seeded = ed.text()
        ed.setText("250")                     # typed, never committed
        QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert ed.text() == seeded
        assert hud.values()["Length"] == pytest.approx(100.0)

    def test_then_steps_back_the_committed_edit(self, qapp):
        hud = self._hud()
        ed = hud.editor("Length")
        ed.setText("250")
        ed.try_commit()                       # committed edit
        committed_text = ed.text()
        ed.setText("999")                     # uncommitted on top of it

        QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert ed.text() == committed_text
        assert hud.values()["Length"] == pytest.approx(250.0)

        QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert hud.values()["Length"] == pytest.approx(100.0)

    def test_undo_does_not_launder_a_rejection(self, qapp):
        """A rejected entry stays flagged through undo (finding F9).

        ``values()`` already reverted the text, so there is no half-typed
        input left for undo to discard.  The sticky flag is what stops a
        second Enter committing the reverted geometry, so undo must not
        clear it — undo steps back *edits*, it does not launder rejections.
        """
        hud = self._hud()
        ed = hud.editor("Length")
        ed.setText("garbage")
        hud.values()                          # forces the reject + revert
        assert hud.has_invalid_field() is True
        QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert hud.has_invalid_field() is True
        assert hud.values()["Length"] == pytest.approx(100.0)


class TestFieldWidth:
    """Decision S2: size to content, grow-only, with two characters of slack.

    The HUD now reads out live values for the whole placement, so its text
    changes on every mouse move.  A width that tracked the text exactly would
    twitch continuously; these pin the three properties that stop it.
    """

    def _hud(self):
        return DynamicInputHud(SCHEMAS["line"], ScaleManager())

    def test_field_grows_to_fit_longer_text(self, qapp):
        hud = self._hud()
        ed = hud.editor("Length")
        hud.set_values({"Length": 1.0, "Angle": 0.0})
        narrow = ed.width()
        hud.set_values({"Length": 123456789.0, "Angle": 0.0})
        assert ed.width() > narrow

    def test_field_never_shrinks_within_one_placement(self, qapp):
        """Grow-only is what makes the readout settle instead of jiggling."""
        hud = self._hud()
        ed = hud.editor("Length")
        hud.set_values({"Length": 123456789.0, "Angle": 0.0})
        wide = ed.width()
        hud.set_values({"Length": 1.0, "Angle": 0.0})
        assert ed.width() == wide

    def test_field_carries_two_characters_of_headroom(self, qapp):
        """Adding a digit must not resize the field mid-keystroke."""
        hud = self._hud()
        ed = hud.editor("Length")
        hud.set_values({"Length": 1234.0, "Angle": 0.0})
        settled = ed.width()
        fm = ed.fontMetrics()
        assert settled >= fm.horizontalAdvance(ed.text()) + \
            fm.horizontalAdvance("00")

    def test_typing_a_digit_does_not_resize(self, qapp):
        hud = self._hud()
        ed = hud.editor("Length")
        hud.set_values({"Length": 1234.0, "Angle": 0.0})
        settled = ed.width()
        ed.setText(ed.text() + "0")
        assert ed.width() == settled

    def test_a_fresh_hud_does_not_inherit_the_previous_width(self, qapp):
        """The grow-only floor is per HUD, so each placement starts compact."""
        first = self._hud()
        first.set_values({"Length": 123456789.0, "Angle": 0.0})
        wide = first.editor("Length").width()

        second = self._hud()
        second.set_values({"Length": 1.0, "Angle": 0.0})
        assert second.editor("Length").width() < wide


class TestArcSpanCoupling:
    """Task 6: Span° and Arc-length are live-coupled through the seed radius.

    Editing one field rewrites the other via ``arc_len = r * radians(span)``.
    The coupling is a pure widget+math affair (no scene): the HUD is told the
    radius in mm, and because ``arc_span`` fields are DIMENSION/ANGLE the write
    -back reuses the same seed path a normal reseed uses.
    """

    _R = 1000.0     # mm; uncalibrated so 1 scene unit == 1 mm

    def _arc_hud(self, shown_hud):
        hud = shown_hud(SCHEMAS["arc_span"])
        hud.set_coupling_radius(self._R)
        hud.set_values({"Span": 0.0, "ArcLength": 0.0})
        hud.focus_first()
        return hud

    def test_span_edit_updates_arc_length(self, shown_hud):
        """90° on a 1000 mm radius is a quarter circumference ≈ 1570.8 mm."""
        hud = self._arc_hud(shown_hud)
        span = hud.editor("Span")
        _type(span, "90")
        QTest.keyClick(span, Qt.Key.Key_Tab)     # commit Span, wraps to Arc
        assert hud.editor("ArcLength").value_mm() == pytest.approx(
            math.pi / 2 * self._R, abs=1e-3)

    def test_arc_length_edit_updates_span(self, shown_hud):
        """1000 mm of arc on a 1000 mm radius is 1 radian ≈ 57.296°."""
        hud = self._arc_hud(shown_hud)
        # Move focus onto the ArcLength field first.
        arc = hud.editor("ArcLength")
        arc.setFocus(Qt.FocusReason.OtherFocusReason)
        _type(arc, "1000")
        QTest.keyClick(arc, Qt.Key.Key_Tab)      # commit Arc, wraps to Span
        assert hud.editor("Span").value_mm() == pytest.approx(
            math.degrees(1000.0 / self._R), abs=1e-3)

    def test_coupling_does_not_run_without_a_radius(self, shown_hud):
        """No radius armed → editing Span leaves ArcLength untouched."""
        hud = shown_hud(SCHEMAS["arc_span"])
        hud.set_values({"Span": 0.0, "ArcLength": 0.0})
        hud.focus_first()
        span = hud.editor("Span")
        _type(span, "90")
        QTest.keyClick(span, Qt.Key.Key_Tab)
        assert hud.editor("ArcLength").value_mm() == pytest.approx(0.0)

    def test_coupling_is_isolated_to_arc_span(self, shown_hud):
        """A radius set on a line HUD must not perturb its fields."""
        hud = shown_hud(SCHEMAS["line"])
        hud.set_coupling_radius(1000.0)
        hud.set_values({"Length": 500.0, "Angle": 0.0})
        hud.focus_first()
        ed = hud.editor("Length")
        _type(ed, "250")
        QTest.keyClick(ed, Qt.Key.Key_Tab)
        # Angle is untouched: the line schema has no coupling.
        assert hud.editor("Angle").value_mm() == pytest.approx(0.0)
        assert hud.values()["Length"] == pytest.approx(250.0)

    def test_write_back_does_not_flag_the_derived_field(self, shown_hud):
        """The coupled write must not spuriously mark a field invalid."""
        hud = self._arc_hud(shown_hud)
        span = hud.editor("Span")
        _type(span, "90")
        QTest.keyClick(span, Qt.Key.Key_Tab)
        hud.values()
        assert hud.has_invalid_field() is False


class TestEngagement:
    """Decision S1: the HUD is a readout until a field is deliberately given
    the keyboard, and is transparent to the mouse until then."""

    _TRANSPARENT = Qt.WidgetAttribute.WA_TransparentForMouseEvents

    def _hud(self):
        hud = DynamicInputHud(SCHEMAS["line"], ScaleManager())
        hud.set_values({"Length": 100.0, "Angle": 0.0})
        return hud

    def test_starts_disengaged(self, qapp):
        assert self._hud().is_engaged() is False

    def test_starts_transparent_to_the_mouse(self, qapp):
        hud = self._hud()
        assert hud.testAttribute(self._TRANSPARENT)
        assert all(ed.testAttribute(self._TRANSPARENT)
                   for ed in (hud.editor("Length"), hud.editor("Angle")))

    def test_engage_focuses_and_accepts_the_mouse(self, qapp):
        hud = self._hud()
        hud.show()
        hud.engage()
        assert hud.is_engaged() is True
        assert not hud.testAttribute(self._TRANSPARENT)
        assert hud.editor("Length").hasSelectedText()

    def test_engage_forwards_the_seed_keystroke(self, qapp):
        hud = self._hud()
        hud.show()
        hud.engage("7")
        assert hud.editor("Length").text() == "7"

    def test_disengage_returns_to_a_transparent_readout(self, qapp):
        hud = self._hud()
        hud.show()
        hud.engage()
        hud.disengage()
        assert hud.is_engaged() is False
        assert hud.testAttribute(self._TRANSPARENT)
        assert all(ed.testAttribute(self._TRANSPARENT)
                   for ed in (hud.editor("Length"), hud.editor("Angle")))
