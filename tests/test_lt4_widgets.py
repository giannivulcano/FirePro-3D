"""LT4 ui_kit widgets: PatternList + PaintSwatch (domain-free)."""
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QLineEdit, QToolButton

from firepro3d.ui_kit import PaintSwatch, PatternList


class _Field(QLineEdit):
    """Stand-in length field honouring the factory contract (value_mm + editingFinished)."""

    def __init__(self, mm):
        super().__init__(f"{mm}")

    def value_mm(self):
        return float(self.text())


def _make(rows, note="", sink=None):
    sink = sink if sink is not None else []
    return PatternList(rows, note=note, field_factory=_Field,
                       on_commit=sink.append), sink


def _btn(w, tip_start):
    return [b for b in w.findChildren(QToolButton) if b.toolTip().startswith(tip_start)]


def test_rows_render_and_edit_commits_whole_list(qapp):
    w, sink = _make([("dash", 6.0), ("gap", 2.0), ("dot", 0.0)])
    fields = w.findChildren(_Field)
    assert len(fields) == 2                      # a Dot has no length field
    fields[0].setText("8")
    fields[0].editingFinished.emit()
    assert sink == [[("dash", 8.0), ("gap", 2.0), ("dot", 0.0)]]


def test_move_remove_add(qapp):
    w, sink = _make([("dash", 6.0), ("gap", 2.0)])
    _btn(w, "Move down")[0].click()
    assert sink[-1] == [("gap", 2.0), ("dash", 6.0)]
    _btn(w, "Remove")[0].click()                 # remove the gap (the dash's ✕ is the last-mark tip)
    assert sink[-1] == [("dash", 6.0)]
    _btn(w, "Add a dot")[0].click()
    assert sink[-1] == [("dash", 6.0), ("gap", 2.0), ("dot", 0.0)]


def test_last_dash_or_dot_cannot_be_removed(qapp):
    w, _ = _make([("dash", 6.0), ("gap", 3.0)])
    last = _btn(w, "A linetype needs")
    assert len(last) == 1 and not last[0].isEnabled()
    rm = _btn(w, "Remove")
    assert len(rm) == 1 and rm[0].isEnabled()   # the gap's ✕


def test_read_only_shows_note_and_no_editors(qapp):
    w, _ = _make(None, note="Dashes overlap — edit on the canvas")
    assert not w.findChildren(_Field)
    assert not _btn(w, "Add")
    assert "Dashes overlap" in w.note_text()


def test_every_control_has_a_tooltip(qapp):
    w, _ = _make([("dash", 6.0), ("gap", 2.0), ("dot", 0.0)])
    for b in w.findChildren(QToolButton):
        assert b.toolTip()


def test_paint_swatch_calls_paint_with_its_rect(qapp):
    seen = []
    sw = PaintSwatch(lambda p, r: seen.append(QRectF(r)), height=64)
    sw.resize(200, 64)
    sw.grab()
    assert seen and seen[-1].height() == 64 and sw.height() == 64
