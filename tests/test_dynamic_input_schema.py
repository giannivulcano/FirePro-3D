"""tests/test_dynamic_input_schema.py — schemas, resolvers, seeds (no scene)."""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.dynamic_input import (
    FieldKind, FieldSpec, SCHEMAS,
    resolve_line, seed_line,
    resolve_rectangle, seed_rectangle,
    resolve_circle, seed_circle,
    resolve_displacement, resolve_distance, resolve_spacing_count,
    resolve_arc_span, resolve_rotation,
)

# A non-origin anchor, so a seed that silently drops the anchor still fails.
ANCHOR = QPointF(1234.0, -567.0)

# Several non-axis-aligned offsets per quadrant, in scene coords (Y down).
# The (+X, -Y) quadrant alone hides sign bugs, so all four are covered.
QUADRANT_OFFSETS = [
    (317.0, -412.0), (1500.0, -25.0),      # up-right
    (-317.0, -412.0), (-25.0, -1500.0),    # up-left
    (-317.0, 412.0), (-3000.0, 2000.0),    # down-left  (the C1 repro)
    (317.0, 412.0), (2000.0, 3000.0),      # down-right
]


class TestRegistry:

    def test_schemas_registered(self):
        assert set(SCHEMAS) == {
            "line", "rectangle", "circle", "polygon",
            "displacement", "distance", "spacing_count",
            "arc_span", "rotation", "track",
            "manip_move", "manip_resize", "manip_rotate",
        }

    def test_line_fields(self):
        f = SCHEMAS["line"].fields
        assert [s.name for s in f] == ["Length", "Angle"]
        assert f[0].kind is FieldKind.DIMENSION
        assert f[1].kind is FieldKind.ANGLE
        assert f[0].minimum == 0.0      # zero-length rejected
        assert f[1].minimum is None     # negative angles allowed

    def test_count_field_has_minimum_zero(self):
        count = [s for s in SCHEMAS["spacing_count"].fields
                 if s.name == "Count"][0]
        assert count.kind is FieldKind.COUNT
        assert count.minimum == 0.0     # DimensionEdit uses strict >, so >= 1

    def test_rectangle_extents_allow_negatives(self):
        """Signed extents need an unbounded field, as displacement dX/dY do.

        ``DimensionEdit`` reverts anything not strictly greater than *minimum*,
        so a 0.0 floor would reject the negative seed a left/down drag produces.
        """
        for spec in SCHEMAS["rectangle"].fields:
            assert spec.minimum is None, spec.name

    def test_placement_flag_matches_resolve_return_type(self):
        """``is_placement`` must agree with what ``resolve`` actually returns.

        Pins the invariant the flag exists to express, rather than the
        ``returns_point`` field that currently implements it.
        """
        anchor = QPointF(10.0, 20.0)
        sample = {
            "Length": 100.0, "Angle": 30.0,
            "X": -40.0, "Y": -50.0,
            "Radius": 60.0,
            "dX": 70.0, "dY": 80.0,
            "Distance": 90.0,
            "Spacing": 500.0, "Count": 3.0,
            "Span": 90.0, "ArcLength": 0.0,
            "Width": 120.0, "Height": 140.0,
        }
        for name, schema in SCHEMAS.items():
            out = schema.resolve(anchor, sample)
            assert isinstance(out, QPointF) == schema.returns_point, name
            assert schema.is_placement == schema.returns_point, name

    def test_only_placement_schemas_seed(self):
        """Today's schemas happen to align; the flag is what callers trust."""
        for name, schema in SCHEMAS.items():
            if schema.seed is not None:
                assert schema.returns_point, name

    def test_requires_anchor_covers_placements_plus_move(self):
        """The engage/commit anchor gate keys on this, not on ``is_placement``.

        Every placement needs an anchor; ``move`` and ``arc_span`` are the
        transforms that also do (a base point / an armed centre+radius+start),
        so neither opens a HUD before that state exists.  The gridline
        replicate transforms are anchorless.
        """
        need = {n for n, s in SCHEMAS.items() if s.requires_anchor}
        assert need == {"line", "rectangle", "circle", "polygon",
                        "displacement", "arc_span", "rotation", "track",
                        "manip_move", "manip_resize", "manip_rotate"}

    def test_anchorless_transforms_do_not_require_an_anchor(self):
        assert SCHEMAS["distance"].requires_anchor is False
        assert SCHEMAS["spacing_count"].requires_anchor is False

    def test_move_is_a_transform_that_still_requires_an_anchor(self):
        """The distinction T15 turns on: transform (dict), yet anchored."""
        disp = SCHEMAS["displacement"]
        assert disp.is_placement is False       # resolves to a dict
        assert disp.needs_anchor is True
        assert disp.requires_anchor is True


class TestLine:

    def test_resolve_is_y_up(self):
        out = resolve_line(QPointF(0, 0), {"Length": 100.0, "Angle": 90.0})
        assert out.x() == pytest.approx(0.0, abs=1e-9)
        assert out.y() == pytest.approx(-100.0)     # up = negative scene Y

    def test_resolve_zero_angle_is_right(self):
        out = resolve_line(QPointF(10, 20), {"Length": 5.0, "Angle": 0.0})
        assert out.x() == pytest.approx(15.0)
        assert out.y() == pytest.approx(20.0)

    def test_seed_round_trips(self):
        anchor, point = QPointF(100, 100), QPointF(400, -300)
        vals = seed_line(anchor, point)
        back = resolve_line(anchor, vals)
        assert back.x() == pytest.approx(point.x())
        assert back.y() == pytest.approx(point.y())

    def test_seed_length_and_angle(self):
        vals = seed_line(QPointF(0, 0), QPointF(0, -50))
        assert vals["Length"] == pytest.approx(50.0)
        assert vals["Angle"] == pytest.approx(90.0)

    @pytest.mark.parametrize("dx,dy", QUADRANT_OFFSETS)
    def test_seed_round_trips_in_every_quadrant(self, dx, dy):
        """Line seeds are an exact inverse: the point comes back unchanged."""
        point = QPointF(ANCHOR.x() + dx, ANCHOR.y() + dy)
        back = resolve_line(ANCHOR, seed_line(ANCHOR, point))
        assert back.x() == pytest.approx(point.x())
        assert back.y() == pytest.approx(point.y())


class TestRectangle:

    def test_resolve_is_y_up(self):
        out = resolve_rectangle(QPointF(0, 0), {"X": 30.0, "Y": 40.0})
        assert out.x() == pytest.approx(30.0)
        assert out.y() == pytest.approx(-40.0)

    def test_seed_keeps_sign(self):
        """A down-left drag seeds negative extents.

        Corner mode builds ``QRectF(anchor, snapped)``, so the sign IS the
        geometry — dropping it moves the rectangle to the opposite quadrant.
        """
        vals = seed_rectangle(QPointF(0, 0), QPointF(-30, 40))
        assert vals["X"] == pytest.approx(-30.0)
        assert vals["Y"] == pytest.approx(-40.0)      # Y-up: +40 scene = -40 up

    @pytest.mark.parametrize("dx,dy", QUADRANT_OFFSETS)
    def test_seed_round_trips_in_every_quadrant(self, dx, dy):
        """Rectangle seeds are an exact inverse, corner included.

        Only signed extents survive the round trip; ``abs()`` extents rebuild
        every corner in the up-right quadrant.
        """
        point = QPointF(ANCHOR.x() + dx, ANCHOR.y() + dy)
        back = resolve_rectangle(ANCHOR, seed_rectangle(ANCHOR, point))
        assert back.x() == pytest.approx(point.x())
        assert back.y() == pytest.approx(point.y())

    @pytest.mark.parametrize("dx,dy", QUADRANT_OFFSETS)
    def test_from_centre_extents_are_direction_independent(self, dx, dy):
        """From-centre mode re-applies ``abs()``, so signed seeds are safe.

        This is the half-extent derivation from the click-commit path; it must
        stay identical whichever quadrant the drag went into.
        """
        point = QPointF(ANCHOR.x() + dx, ANCHOR.y() + dy)
        back = resolve_rectangle(ANCHOR, seed_rectangle(ANCHOR, point))
        assert abs(back.x() - ANCHOR.x()) == pytest.approx(abs(dx))
        assert abs(back.y() - ANCHOR.y()) == pytest.approx(abs(dy))


class TestCircle:

    def test_resolve_returns_point_at_radius(self):
        out = resolve_circle(QPointF(5, 5), {"Radius": 12.0})
        assert math.hypot(out.x() - 5, out.y() - 5) == pytest.approx(12.0)

    def test_seed_is_distance_from_centre(self):
        vals = seed_circle(QPointF(0, 0), QPointF(3, 4))
        assert vals["Radius"] == pytest.approx(5.0)

    @pytest.mark.parametrize("dx,dy", QUADRANT_OFFSETS)
    def test_seed_round_trips_radius_in_every_quadrant(self, dx, dy):
        """Circle round-trips the *radius*, not the point.

        ``resolve_circle`` legitimately returns a different point on the same
        circle — direction is discarded because the commit path only takes the
        hypot.  Asserting point identity here would be asserting a coincidence.
        """
        point = QPointF(ANCHOR.x() + dx, ANCHOR.y() + dy)
        back = resolve_circle(ANCHOR, seed_circle(ANCHOR, point))
        r_in = math.hypot(dx, dy)
        r_out = math.hypot(back.x() - ANCHOR.x(), back.y() - ANCHOR.y())
        assert r_out == pytest.approx(r_in)


class TestTransforms:

    def test_displacement_flips_y(self):
        out = resolve_displacement(None, {"dX": 10.0, "dY": 20.0})
        assert out["offset"].x() == pytest.approx(10.0)
        assert out["offset"].y() == pytest.approx(-20.0)

    def test_distance(self):
        assert resolve_distance(None, {"Distance": 42.0}) == {"distance": 42.0}

    def test_spacing_count_coerces_int(self):
        out = resolve_spacing_count(None, {"Spacing": 500.0, "Count": 3.4})
        assert out == {"spacing": 500.0, "count": 3}

    def test_spacing_count_floors_at_one(self):
        out = resolve_spacing_count(None, {"Spacing": 500.0, "Count": 0.2})
        assert out["count"] == 1


class TestArcSpan:
    """Arc step 3: a span sweep, coupled to a derived arc-length view."""

    def test_arc_span_resolves_to_transform_dict(self):
        out = resolve_arc_span(None, {"Span": 90.0, "ArcLength": 0.0})
        assert out == {"span_deg": 90.0}

    def test_arc_span_schema_is_anchored_transform(self):
        s = SCHEMAS["arc_span"]
        assert s.returns_point is False
        assert s.needs_anchor is True          # radius/start armed before step 3
        assert [f.name for f in s.fields] == ["Span", "ArcLength"]

    def test_arc_length_field_is_a_dimension_with_zero_floor(self):
        arc = [f for f in SCHEMAS["arc_span"].fields
               if f.name == "ArcLength"][0]
        assert arc.kind is FieldKind.DIMENSION
        assert arc.minimum == 0.0

    def test_span_field_is_a_span_kind(self):
        # SPAN (0-360 magnitude), not ANGLE (±180 heading): a 270 sweep must
        # read 270, not -90.
        span = [f for f in SCHEMAS["arc_span"].fields
                if f.name == "Span"][0]
        assert span.kind is FieldKind.SPAN

    def test_span_format_parse_does_not_wrap_reflex(self):
        from firepro3d.dynamic_input import _format_span, _parse_span
        assert _format_span(270.0) == "270°"       # not -90
        assert _format_span(57.2957795) == "57.3°"
        assert _parse_span("270°") == 270.0        # not -90
        assert _parse_span("300") == 300.0
        assert _parse_span("junk") is None

    def test_only_the_span_reaches_the_applier(self):
        """ArcLength is a derived HUD view; the resolver ignores it."""
        out = resolve_arc_span(None, {"Span": 45.0, "ArcLength": 9999.0})
        assert out == {"span_deg": 45.0}


class TestRotation:
    """The rectangle rotate step's transform schema (Task 12)."""

    def test_resolve_returns_angle_dict(self):
        assert resolve_rotation(None, {"Angle": 30}) == {"angle_deg": 30.0}

    def test_resolve_is_anchor_independent(self):
        """The pivot lives in scene state, so the anchor is unused here."""
        assert resolve_rotation(QPointF(9, 9), {"Angle": -45.0}) == {
            "angle_deg": -45.0}

    def test_rotation_schema_is_anchored_transform(self):
        s = SCHEMAS["rotation"]
        assert s.returns_point is False
        assert s.needs_anchor is True          # sized rect + pivot armed first
        assert s.requires_anchor is True

    def test_rotation_has_a_single_angle_field(self):
        s = SCHEMAS["rotation"]
        assert [f.name for f in s.fields] == ["Angle"]
        # ANGLE (±180 heading), not SPAN — orientation is a signed heading.
        assert s.fields[0].kind is FieldKind.ANGLE
