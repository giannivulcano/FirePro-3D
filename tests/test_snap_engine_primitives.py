"""Layer-1 unit tests for SnapEngine geometric primitives.

Covers the three pure static methods in ``firepro3d/snap_engine.py``:

- ``_line_line_intersect`` (line 625)
- ``_line_circle_intersect`` (line 643)
- ``_project_to_segment`` (line 789)

Per ``docs/specs/snapping-engine.md`` §10.1 (roadmap item in ``todo.md``).

These tests pin the **current** contract of the primitives, including
behavior that is surprising but intentional (e.g. tangent returning two
identical points, projection clamping to the segment). Do not "fix" a
test to match intuition — if you believe a primitive is wrong, file a
follow-up in ``todo.md`` and mark the affected test ``xfail``.

No ``QApplication`` is required: ``QPointF`` is a pure data type.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.snap_engine import SnapEngine


# Engine epsilons — mirrors the literals used inside snap_engine.py.
# If snap_engine.py ever extracts these to named constants, update here.
LINE_LINE_DENOM_EPS = 1e-10
DEGENERATE_EPS = 1e-12


def _approx_point(expected: QPointF, abs_tol: float = 1e-9):
    """Return a matcher for a QPointF comparison via ``pytest.approx``.

    Compares x and y independently so failure messages stay readable.
    """
    return (pytest.approx(expected.x(), abs=abs_tol),
            pytest.approx(expected.y(), abs=abs_tol))


def _xy(pt: QPointF) -> tuple[float, float]:
    return (pt.x(), pt.y())


def test_smoke_primitives_are_importable():
    """Sanity check: all three primitives exist and are callable."""
    assert callable(SnapEngine._line_line_intersect)
    assert callable(SnapEngine._line_circle_intersect)
    assert callable(SnapEngine._project_to_segment)
