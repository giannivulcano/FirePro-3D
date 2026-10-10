"""ET1 G7 -- the app-level tooltip filter: a long plain tip shows a label no
wider than the cap (+ padding) with word wrap and a <br> per newline; a short
tip's label is byte-identical to today's; every tip this task authors has no
line wider than the cap."""
import gc

import pytest
from PyQt6.QtCore import QEvent, QPoint
from PyQt6.QtGui import QFontMetrics, QHelpEvent
from PyQt6.QtWidgets import QApplication, QToolTip, QWidget

from firepro3d import capability_panel, geometry_2d, theme, tooltips
from firepro3d.constants import TOOLTIP_MAX_PX

LONG = ("How this end sizes on model canvases (plan, detail, Block Editor).\n"
        "Fixed size: a constant 6 px per printed mm at any zoom, which is a long "
        "line of text that must wrap because it is wider than the cap.")
SHORT = "Show this end's end type.\nOff draws a plain end but keeps the pick."


def _tip():
    for w in QApplication.allWidgets():
        if w.metaObject().className() == "QTipLabel":
            return (w.width(), w.height(), w.wordWrap(), w.text())
    return None


def _send(qapp, host):
    QToolTip.hideText()
    qapp.processEvents()
    ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(10, 10), host.mapToGlobal(QPoint(10, 10)))
    qapp.sendEvent(host, ev)
    for _ in range(5):
        qapp.processEvents()
    return _tip()


def _flush(qapp):
    """Settle earlier tests' widgets before an app-wide stylesheet repolish
    walks every widget: collect dropped wrappers, then run the pending
    deleteLater()s (processEvents alone never delivers DeferredDelete)."""
    gc.collect()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def host(qapp):
    """A shown widget under the app stylesheet; the previous stylesheet is
    restored, the tip hidden and the widget closed afterwards."""
    prev = qapp.styleSheet()
    _flush(qapp)
    qapp.setStyleSheet(theme.build_app_qss(theme.detect()))
    w = QWidget()
    try:
        w.resize(200, 100)
        w.show()
        qapp.processEvents()
        yield w
    finally:
        QToolTip.hideText()
        w.close()
        w.deleteLater()
        _flush(qapp)
        qapp.setStyleSheet(prev)
        qapp.processEvents()


def test_g7_long_tip_wraps_at_the_cap_and_short_tip_is_plain(tooltips_installed, host):
    qapp = tooltips_installed
    host.setToolTip(LONG)
    long_ = _send(qapp, host)
    host.setToolTip(SHORT)
    short = _send(qapp, host)
    assert long_[2] is True and long_[0] <= TOOLTIP_MAX_PX + 40
    assert long_[1] > short[1]                       # wrapped: more lines than SHORT's two
    assert "<br>" in long_[3] and "&lt;" not in long_[3]
    assert short[2] is False and short[3] == SHORT   # left to the widget


def test_g7_install_is_idempotent_and_uninstall_restores(qapp, host):
    """main() installs once; a second install (e.g. a test fixture on the
    same app) adds no second filter -- one wrap, and uninstall leaves none.
    A short tip's label is byte-identical with and without the filter."""
    host.setToolTip(LONG)
    tooltips.install(qapp)
    tooltips.install(qapp)
    try:
        assert len(tooltips._FILTERS) == 1
        wrapped = _send(qapp, host)
        host.setToolTip(SHORT)
        short_on = _send(qapp, host)
    finally:
        tooltips.uninstall(qapp)
    assert wrapped[2] is True and wrapped[0] <= TOOLTIP_MAX_PX + 40
    assert tooltips._FILTERS == {}
    short_off = _send(qapp, host)
    assert short_on == short_off
    host.setToolTip(LONG)
    plain = _send(qapp, host)
    assert plain[2] is False and plain[0] > TOOLTIP_MAX_PX + 40
    assert wrapped[1] > plain[1]


def test_g7_wrap_rules():
    fm = QFontMetrics(QToolTip.font())
    assert tooltips.wrap(SHORT, TOOLTIP_MAX_PX) is None
    rich = tooltips.wrap(LONG, TOOLTIP_MAX_PX)
    assert rich.startswith(f"<table width='{TOOLTIP_MAX_PX}'>") and "<br>" in rich
    assert tooltips.wrap("<b>already rich</b> " * 20, TOOLTIP_MAX_PX) is None
    assert tooltips.wrap("", TOOLTIP_MAX_PX) is None
    assert tooltips.wrap("a < b & c", TOOLTIP_MAX_PX) is None       # short: untouched
    assert fm.horizontalAdvance("x") > 0


def test_g7_trailing_newline_adds_no_trailing_break():
    rich = tooltips.wrap(LONG + "\n", TOOLTIP_MAX_PX)
    assert rich == tooltips.wrap(LONG, TOOLTIP_MAX_PX), rich
    assert "<br></td>" not in rich


def test_g7_authored_tips_have_no_line_over_the_cap(qapp):
    fm = QFontMetrics(QToolTip.font())
    tips = [v for n, v in vars(geometry_2d).items() if n.endswith("_TIP") and isinstance(v, str)]
    tips += [v for n, v in vars(capability_panel).items() if n.endswith("_TIP") and isinstance(v, str)]
    assert any("Multiplies" in t for t in tips)                     # composition: the ET1 tips are in
    for t in tips:
        for line in t.split("\n"):
            assert fm.horizontalAdvance(line) <= TOOLTIP_MAX_PX, line
