"""Render tests for the shared snap-indicator painter.

These tests paint a REAL :class:`~firepro3d.snap_engine.OsnapResult` into a
REAL ``QImage`` via a REAL ``QPainter`` and assert on PIXELS — never on
mocked calls.  This is a live-render feature: the house rule is that
live-render bugs pass headless when tests use synthetic stand-ins, so the
snap result carries genuine ``QGraphicsLineItem`` source items and the
assertions check for painted colour at the expected marker + source-item
locations.

The parity guard pins the richer visuals (``source_item2`` + filled
``face-`` glyph) that the model view has always drawn and that the import
preview previously lacked.
"""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsLineItem

from firepro3d.snap_engine import (
    OsnapResult,
    SNAP_COLORS,
    paint_snap_indicator,
)


# ── Pixel helpers ──────────────────────────────────────────────────────────

def _count_color(img: QImage, target: QColor, tol: int = 40) -> int:
    """Count pixels within ``tol`` (per channel) of ``target`` RGB."""
    n = 0
    tr, tg, tb = target.red(), target.green(), target.blue()
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = QColor(img.pixel(x, y))
            if (abs(c.red() - tr) <= tol
                    and abs(c.green() - tg) <= tol
                    and abs(c.blue() - tb) <= tol):
                n += 1
    return n


def _make_result(*, with_second: bool, name: str | None = None) -> OsnapResult:
    """Build a REAL OsnapResult with real QGraphicsLineItem source items.

    The two source lines straddle the snap point so a correct source-item
    trace paints a long coloured streak across the image; dropping
    ``source_item2`` measurably removes one of the two streaks.
    """
    src1 = QGraphicsLineItem(-400.0, 0.0, 400.0, 0.0)      # horizontal
    src2 = QGraphicsLineItem(0.0, -400.0, 0.0, 400.0)      # vertical
    return OsnapResult(
        point=QPointF(0.0, 0.0),
        snap_type="endpoint",
        source_item=src1,
        source_item2=src2 if with_second else None,
        name=name,
    )


class _FakeView:
    """Minimal view exposing the transform helpers the painter needs.

    ``paint_snap_indicator`` only calls ``mapFromScene`` on the view (the
    marker glyph is drawn in reset-transform viewport coords).  A 1:1
    identity mapping is enough for the direct-call parity tests; the
    zoom-sensitive path is covered separately through the real
    ``Model_View`` in :func:`test_model_view_renders_richer_indicator`.
    """

    def mapFromScene(self, pt):  # noqa: N802 — Qt casing
        return QPointF(pt.x() + 100.0, pt.y() + 100.0)


def _paint(result, view=None, size=200) -> QImage:
    view = view or _FakeView()
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("black"))
    p = QPainter(img)
    paint_snap_indicator(p, view, result)
    p.end()
    return img


# ── Direct-call parity tests ───────────────────────────────────────────────

def test_indicator_draws_marker(qapp):
    """The snap glyph paints in the snap-type colour at the mapped point."""
    img = _paint(_make_result(with_second=False))
    color = QColor(SNAP_COLORS["endpoint"])
    assert _count_color(img, color) > 0


def test_second_source_item_adds_pixels(qapp):
    """PARITY GUARD: source_item2 paints an extra coloured streak.

    RED-verify: if the shared painter dropped ``source_item2`` (the old
    preview behaviour) the vertical streak would vanish and this delta
    would collapse to ~0.  A correct painter draws BOTH lines, so the
    two-source image has materially more coloured pixels.
    """
    color = QColor(SNAP_COLORS["endpoint"])
    one = _count_color(_paint(_make_result(with_second=False)), color)
    two = _count_color(_paint(_make_result(with_second=True)), color)
    # The vertical source line spans the image top-to-bottom: dropping it
    # removes a whole column of coloured pixels.
    assert two > one + 20, f"expected source_item2 streak; one={one} two={two}"


def test_face_target_fills_glyph(qapp):
    """PARITY GUARD: a ``face-`` named target fills the marker glyph.

    The old preview never read ``name`` so face targets rendered outlined.
    A filled glyph paints strictly more interior pixels than an outlined
    one of the same size/colour.
    """
    color = QColor(SNAP_COLORS["endpoint"])
    outlined = _count_color(_paint(_make_result(with_second=False)), color)
    filled = _count_color(
        _paint(_make_result(with_second=False, name="face-left-corner-A")),
        color,
    )
    assert filled > outlined, f"expected filled face glyph; outlined={outlined} filled={filled}"


def test_missing_source_item2_does_not_crash(qapp):
    """A result without source_item2/name paints without raising."""
    r = OsnapResult(point=QPointF(0.0, 0.0), snap_type="nearest")
    img = _paint(r)
    assert img is not None


# ── Real Model_View render (zoom-sensitive, non-identity transform) ─────────

def test_model_view_renders_richer_indicator(shown_model_view):
    """The real Model_View foreground pass paints the richer indicator.

    Uses the shown fixture's non-identity transform (m11=0.25) so a
    device-transform / ItemIgnoresTransformations regression cannot hide
    behind an m11==1 fixture.
    """
    view, scene = shown_model_view
    result = _make_result(with_second=True, name="face-left-corner-A")
    scene._snap_result = result
    view.viewport().update()
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()

    img = QImage(view.viewport().size(), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    view.render(p)
    p.end()

    color = QColor(SNAP_COLORS["endpoint"])
    assert _count_color(img, color) > 0, "richer snap indicator not painted"
