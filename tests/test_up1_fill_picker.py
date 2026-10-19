"""UP1 picker modes (AC1, G3, dialog half of G2). Dialog driven through its
real widgets; ``exec`` is replaced so the test drives the shown dialog."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

from firepro3d import colour_picker as cp
from firepro3d.fill_layers import NO_LAYER, BackgroundLayer, PatternLayer


def _dlg(qapp, **kw):
    d = cp.ColourPickerDialog(None, **kw)
    d.show()
    qapp.processEvents()
    return d


def _palette_chip(d, value):
    return next(c for c in d._chips if c.value == value)


def test_colour_mode_has_no_fill_block(qapp):
    d = _dlg(qapp, initial="#FF0000")
    assert d._opacity is None and d._scale is None and d._pattern_chips == []
    assert _palette_chip(d, cp.NO_FILL).isVisible()                    # G3


def test_fill_mode_shows_opacity_only(qapp):
    d = _dlg(qapp, initial=cp.NO_FILL, mode="fill")
    assert d._opacity is not None and d._opacity.isVisible()
    assert d._scale is None and d._pattern_chips == []
    assert d._opacity.value() == 100                                   # R10
    assert _palette_chip(d, cp.NO_FILL).isVisible()                    # = background off


def test_pattern_mode_shows_pattern_row_opacity_scale_and_hides_no_fill(qapp, shipped_hatches):
    reg = shipped_hatches(None)
    d = _dlg(qapp, initial="token:auto", mode="pattern", registry=reg)
    assert d._pattern_chips[0].value is None                           # None chip first
    assert len(d._pattern_chips) >= 2
    assert d._opacity.isVisible() and d._scale.isVisible()
    assert not _palette_chip(d, cp.NO_FILL).isVisible()


def test_more_button_lists_the_overflow_and_selects_it(qapp, monkeypatch, shipped_hatches):
    from firepro3d.hatch_patterns import tile_choices
    from firepro3d.theme import M
    monkeypatch.setattr(M, "COLOUR_PATTERN_ROW_MAX", 2)
    reg = shipped_hatches(None)
    choices = tile_choices(reg, ())
    d = _dlg(qapp, initial="token:auto", mode="pattern", registry=reg)
    assert [c.value for c in d._pattern_chips] == [None] + [r for _n, r in choices[:2]]
    acts = d._more_btn.menu().actions()
    assert [a.text() for a in acts] == [n for n, _r in choices[2:]]
    acts[0].trigger()
    assert d._pattern_ref == choices[2][1]
    assert d._more_btn.isChecked() and not any(c.selected for c in d._pattern_chips)


def test_fill_block_sits_below_recent_above_footer(qapp):
    d = _dlg(qapp, initial=cp.NO_FILL, mode="fill")
    y_recent = d._recent_row_chips[0].mapTo(d, d._recent_row_chips[0].rect().topLeft()).y()
    y_opacity = d._opacity.mapTo(d, d._opacity.rect().topLeft()).y()
    y_ok = d._ok_btn.mapTo(d, d._ok_btn.rect().topLeft()).y()
    assert y_recent < y_opacity < y_ok                                 # D3


def _accept_with(monkeypatch, drive):
    def _exec(self):
        self.show()
        drive(self)
        self.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(cp.ColourPickerDialog, "exec", _exec)


def test_pick_fill_pattern_mode_returns_all_four_fields(qapp, monkeypatch, shipped_hatches):
    reg = shipped_hatches(None)
    seen = {}
    def drive(d):
        chip = d._pattern_chips[1]
        seen["ref"] = chip.value
        QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
        QTest.mouseClick(_palette_chip(d, "#FF0000"), Qt.MouseButton.LeftButton)
        d._opacity.setValue(60)
        d._scale.setText("2.5")
    _accept_with(monkeypatch, drive)
    got = cp.pick_fill(None, None, pattern=True, context="Fill Pattern", registry=reg)
    assert got == PatternLayer(seen["ref"], "#ff0000", 0.6, 2.5)


def test_pick_fill_pattern_none_chip_is_no_layer(qapp, monkeypatch, shipped_hatches):
    reg = shipped_hatches(None)
    _accept_with(monkeypatch, lambda d: QTest.mouseClick(d._pattern_chips[0],
                                                         Qt.MouseButton.LeftButton))
    init = PatternLayer("builtin-hatch-diagonal", "#123456", 0.5, 3.0)
    assert cp.pick_fill(init, None, pattern=True, registry=reg) is NO_LAYER


def test_pick_fill_background_and_no_fill(qapp, monkeypatch):
    _accept_with(monkeypatch, lambda d: (QTest.mouseClick(_palette_chip(d, "#0000FF"),
                                                          Qt.MouseButton.LeftButton),
                                         d._opacity.setValue(40)))
    assert cp.pick_fill(None, None, pattern=False) == BackgroundLayer("#0000ff", 0.4)
    _accept_with(monkeypatch, lambda d: QTest.mouseClick(_palette_chip(d, cp.NO_FILL),
                                                         Qt.MouseButton.LeftButton))
    assert cp.pick_fill(BackgroundLayer("#0000ff", 0.4), None, pattern=False) is NO_LAYER


def test_pick_fill_cancel_is_none_and_initial_layer_seeds_fields(qapp, monkeypatch, shipped_hatches):
    reg = shipped_hatches(None)
    init = PatternLayer("builtin-hatch-diagonal", "#123456", 0.5, 3.0)
    seen = {}
    def _rej(self):
        seen.update(op=self._opacity.value(), sc=self._scale.text(),
                    sel=[c.value for c in self._pattern_chips if c.selected])
        self.reject()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(cp.ColourPickerDialog, "exec", _rej)
    assert cp.pick_fill(init, None, pattern=True, registry=reg) is None
    assert seen["op"] == 50 and float(seen["sc"]) == 3.0
    assert seen["sel"] == ["builtin-hatch-diagonal"]          # 5 shipped tiles fit the row


@pytest.mark.parametrize("text", ["0", "-1", "", "abc"])
def test_bad_scale_text_keeps_prior_scale(qapp, monkeypatch, shipped_hatches, text):
    reg = shipped_hatches(None)
    _accept_with(monkeypatch, lambda d: d._scale.setText(text))
    init = PatternLayer("builtin-hatch-diagonal", "#123456", 0.5, 3.0)
    assert cp.pick_fill(init, None, pattern=True, registry=reg).scale == 3.0


def test_unknown_initial_ref_is_kept_as_a_missing_chip(qapp, monkeypatch, shipped_hatches):
    reg = shipped_hatches(None)
    _accept_with(monkeypatch, lambda d: None)
    init = PatternLayer("no-such-tile", "#123456", 0.5, 1.0)
    assert cp.pick_fill(init, None, pattern=True, registry=reg).ref == "no-such-tile"  # D-A36


def test_recents_record_colour_only(qapp, monkeypatch):
    cp.clear_recents()
    _accept_with(monkeypatch, lambda d: QTest.mouseClick(_palette_chip(d, "#0000FF"),
                                                         Qt.MouseButton.LeftButton))
    cp.pick_fill(None, None, pattern=False)
    assert cp.load_recents() == ["#0000FF"]
