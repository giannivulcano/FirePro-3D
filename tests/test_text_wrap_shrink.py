"""Text Wrap / Shrink to fit (text-sizing design 2026-11-01, D4-D7, AC9-AC16).

Expected sizes come from a raw ``QTextDocument`` laid out the way the sizing
contract prescribes (D1: Arial at ``TEXT_METRIC_REF_PX``, scale = h / cap,
margin = padding / scale) -- never from ``TextItem`` itself.
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QTextDocument

from firepro3d.constants import TEXT_METRIC_REF_PX
from firepro3d.text_item import TextAnnotationData, TextItem

LONG = "alpha beta gamma delta epsilon zeta"


def _raw_doc(text, h=3.0, pad=1.0, wrap_mm=None):
    """Raw-Qt ground truth: ``(doc, scale)`` for *text* unwrapped (width =
    idealWidth) or wrapped at *wrap_mm* surface mm."""
    f = QFont("Arial")
    f.setPixelSize(TEXT_METRIC_REF_PX)
    s = h / QFontMetricsF(f).capHeight()
    doc = QTextDocument()
    doc.setDefaultFont(f)
    doc.setDocumentMargin(pad / s)
    doc.setPlainText(text)
    doc.setTextWidth(-1)
    doc.setTextWidth(doc.idealWidth() if wrap_mm is None else wrap_mm / s)
    return doc, s


def _lines(doc) -> int:
    doc.documentLayout().documentSize()
    n, b = 0, doc.begin()
    while b.isValid():
        n += b.layout().lineCount()
        b = b.next()
    return n


def _box(item) -> QRectF:
    """The drawn box in scene/paper mm (unrotated): grips TL..BR."""
    g = item.grip_points()
    return QRectF(g[0], g[4])


def _model(role="plan"):
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms = Model_Space(scene_role=role)
    ms._level_manager = LevelManager()
    return ms


def _add(ms, **kw):
    rec = dict(text=LONG, x=10.0, y=20.0, height_mm=3.0, cell_padding_mm=1.0)
    rec.update(kw)
    t = TextItem(TextAnnotationData(**rec))
    ms.addItem(t)
    ms._texts.append(t)
    ms.push_undo_state()
    return t


def _process():
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()


def _reformat(t):
    t.prepareGeometryChange()
    t._apply_format()


# ── T21: data model (D4) ────────────────────────────────────────────────────

@pytest.mark.parametrize("rec,wrap", [({"wrap_width_mm": 0.0}, False),
                                      ({"wrap_width_mm": 120.0}, True)])
def test_legacy_record_flags_are_absent_and_derived(qapp, rec, wrap):
    """AC15 / T-legacy: a pre-flag record loads with no stored flag; Wrap
    follows wrap_width_mm > 0, Shrink is off; nothing new is written."""
    d = TextAnnotationData.from_dict({"type": "text", "text": "Hi", **rec})
    assert (d.wrap, d.shrink) == (None, None)
    assert (d.wrap_on(), d.shrink_on()) == (wrap, False)
    out = d.to_dict()
    assert "wrap" not in out and "shrink" not in out


def test_bound_seed_is_shrink_on_wrap_off(qapp):
    """G12/G13: the bound-text legacy default is the hug (Shrink ON + Wrap
    OFF) even with an authored wrap width; off the block layer it is plain."""
    d = TextAnnotationData.from_dict({"text": "@[Name]", "wrap_width_mm": 13.9})
    assert (d.wrap_on(bound=True), d.shrink_on(bound=True)) == (False, True)
    assert (d.wrap_on(), d.shrink_on()) == (True, False)


@pytest.mark.parametrize("wrap,shrink", [(True, True), (True, False),
                                         (False, True), (False, False)])
def test_flags_round_trip_sparse(qapp, wrap, shrink):
    """AC16 / T-roundtrip: authored flags write and read back exactly."""
    d = TextAnnotationData(text="Hi", wrap_width_mm=30.0, wrap=wrap, shrink=shrink)
    out = d.to_dict()
    assert (out["wrap"], out["shrink"]) == (wrap, shrink)
    back = TextAnnotationData.from_dict(out)
    assert (back.wrap, back.shrink) == (wrap, shrink)
    item = TextItem.from_dict(out)
    assert (item.to_dict()["wrap"], item.to_dict()["shrink"]) == (wrap, shrink)
