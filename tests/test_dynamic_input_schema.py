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
)


class TestRegistry:

    def test_six_schemas_registered(self):
        assert set(SCHEMAS) == {
            "line", "rectangle", "circle",
            "displacement", "distance", "spacing_count",
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


class TestRectangle:

    def test_resolve_is_y_up(self):
        out = resolve_rectangle(QPointF(0, 0), {"X": 30.0, "Y": 40.0})
        assert out.x() == pytest.approx(30.0)
        assert out.y() == pytest.approx(-40.0)

    def test_seed_uses_absolute_extents(self):
        vals = seed_rectangle(QPointF(0, 0), QPointF(-30, 40))
        assert vals["X"] == pytest.approx(30.0)
        assert vals["Y"] == pytest.approx(40.0)


class TestCircle:

    def test_resolve_returns_point_at_radius(self):
        out = resolve_circle(QPointF(5, 5), {"Radius": 12.0})
        assert math.hypot(out.x() - 5, out.y() - 5) == pytest.approx(12.0)

    def test_seed_is_distance_from_centre(self):
        vals = seed_circle(QPointF(0, 0), QPointF(3, 4))
        assert vals["Radius"] == pytest.approx(5.0)


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
