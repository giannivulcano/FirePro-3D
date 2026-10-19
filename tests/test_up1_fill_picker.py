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


@pytest.mark.parametrize("mode", ["fill", "pattern"])
def test_no_layer_seed_opens_with_defaults(qapp, shipped_hatches, mode):
    """layer=NO_LAYER (what a cleared swatch hands back) seeds opacity 100 / scale 1."""
    reg = shipped_hatches(None)
    d = _dlg(qapp, initial=cp.NO_FILL, mode=mode, layer=NO_LAYER, registry=reg)
    assert d._opacity.value() == 100
    if mode == "pattern":
        assert d._scale.text() == "1"


def test_recents_record_colour_only(qapp, monkeypatch):
    cp.clear_recents()
    _accept_with(monkeypatch, lambda d: QTest.mouseClick(_palette_chip(d, "#0000FF"),
                                                         Qt.MouseButton.LeftButton))
    cp.pick_fill(None, None, pattern=False)
    assert cp.load_recents() == ["#0000FF"]


# ── T5 review round: locale, needs_load, default colour, exclude, dbl-click ──

def test_scale_field_is_locale_independent(qapp, monkeypatch, shipped_hatches):
    from PyQt6.QtCore import QLocale
    reg = shipped_hatches(None)
    prior = QLocale()
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    try:
        def drive(d):
            QTest.mouseClick(d._pattern_chips[1], Qt.MouseButton.LeftButton)
            d._scale.clear()
            d._scale.setFocus()
            QTest.keyClicks(d._scale, "2.5")
            seen["acceptable"] = d._scale.hasAcceptableInput()
        seen = {}
        _accept_with(monkeypatch, drive)
        got = cp.pick_fill(None, None, pattern=True, registry=reg)
    finally:
        QLocale.setDefault(prior)
    # a German validator leaves "2.5" Intermediate (and accepts "2,5", which
    # float() cannot parse): the field must treat "." as the decimal point
    assert seen["acceptable"]
    assert isinstance(got, PatternLayer) and got.scale == 2.5


def test_pattern_needs_load_cases(qapp, tmp_path):
    from PyQt6.QtCore import QPointF, QSettings
    from firepro3d import app_data, block_library as bl, hatch_patterns as hp
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    root = tmp_path / "patterns_root"
    root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.HATCH_DIR_KEY, str(root))
    pat = BlockDefinition.new(
        name="Zig", library="System", series="Hatches", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})
    bl.save_to_library(pat, root=str(root))
    ms = Model_Space()
    assert hp.pattern_needs_load(pat.id, ms) is True            # library-only
    assert hp.pattern_needs_load(None, ms) is False
    assert hp.pattern_needs_load(pat.id, None) is False
    assert hp.ensure_pattern_available(pat.id, ms) is True      # loads it
    assert hp.pattern_needs_load(pat.id, ms) is False           # now in registry


def test_pick_fill_pattern_default_colour_is_auto(qapp, monkeypatch, shipped_hatches):
    reg = shipped_hatches(None)
    seen = {}
    def drive(d):
        seen["ref"] = d._pattern_chips[1].value
        QTest.mouseClick(d._pattern_chips[1], Qt.MouseButton.LeftButton)   # no colour click
    _accept_with(monkeypatch, drive)
    got = cp.pick_fill(None, None, pattern=True, registry=reg)
    assert got == PatternLayer(seen["ref"], "token:auto", 1.0, 1.0)        # D2


def test_exclude_removes_ref_from_chips_and_more_menu(qapp, monkeypatch, shipped_hatches):
    from firepro3d.hatch_patterns import tile_choices
    from firepro3d.theme import M
    monkeypatch.setattr(M, "COLOUR_PATTERN_ROW_MAX", 2)
    reg = shipped_hatches(None)
    choices = tile_choices(reg, ())
    in_row, in_menu = choices[0], choices[2]
    d = _dlg(qapp, initial="token:auto", mode="pattern", registry=reg,
             exclude=(in_row[1], in_menu[1]))
    assert in_row[1] not in [c.value for c in d._pattern_chips]
    assert in_menu[0] not in [a.text() for a in d._more_btn.menu().actions()]
    assert len(d._pattern_chips) == 1 + 2                       # None + still a full row


def test_pattern_chip_double_click_accepts_with_that_pattern(qapp, monkeypatch, shipped_hatches):
    reg = shipped_hatches(None)
    d = _dlg(qapp, initial="token:auto", mode="pattern", registry=reg)
    chip = d._pattern_chips[2]
    QTest.mouseDClick(chip, Qt.MouseButton.LeftButton)
    assert d.result() == QDialog.DialogCode.Accepted
    assert d.result_layer() == PatternLayer(chip.value, "token:auto", 1.0, 1.0)
