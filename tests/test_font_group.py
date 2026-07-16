"""Tests for the ribbon Font group controller (firepro3d/font_group.py)."""
import pytest
from PyQt6.QtGui import QFont
from firepro3d.font_group import next_ladder_pt, prev_ladder_pt, FontGroupController
from firepro3d.constants import FONT_SIZE_LADDER_PT
from firepro3d.paper_space import (
    PaperScene, Sheet, TextAnnotationData, TextAnnotationItem, ViewResolver,
    _font_pt_from_mm,
)


def test_ladder_is_word_standard():
    assert FONT_SIZE_LADDER_PT == (
        8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)


@pytest.mark.parametrize("cur,expected", [
    (12, 14),      # on-ladder steps up
    (13, 14),      # off-ladder snaps to next step above
    (72, 72),      # top clamps
    (100, 100),    # above ladder stays put
    (5, 8),        # below ladder snaps to first step
])
def test_grow(cur, expected):
    assert next_ladder_pt(cur) == expected


@pytest.mark.parametrize("cur,expected", [
    (14, 12),      # on-ladder steps down
    (13, 12),      # off-ladder snaps to next step below
    (8, 8),        # bottom clamps
    (5, 5),        # below ladder stays put
    (100, 72),     # above ladder snaps to top step
])
def test_shrink(cur, expected):
    assert prev_ladder_pt(cur) == expected


# ---------------------------------------------------------------------------
# FontGroupController tests
# ---------------------------------------------------------------------------

def _stub_resolver():
    """Return a ViewResolver with all-None managers (safe for sheets with no views)."""
    return ViewResolver(None, None, None, None)


@pytest.fixture
def paper_text(qapp):
    """PaperScene with two attached text items; returns (scene, [item1, item2])."""
    sheet = Sheet.create_default()
    scene = PaperScene(sheet, _stub_resolver())
    item1 = scene.add_annotation(TextAnnotationData(text="Alpha"))
    item2 = scene.add_annotation(TextAnnotationData(text="Beta"))
    return scene, [item1, item2]


def _controller(targets):
    return FontGroupController(get_targets=lambda: targets)


def test_bold_commit_pushes_one_command_per_target_in_one_macro(paper_text):
    scene, items = paper_text
    c = _controller(items)
    before = scene.undo_stack.index()
    c._commit("Bold", True)
    assert all(it.data.bold for it in items)
    scene.undo_stack.undo()          # one macro = one undo step reverts both
    assert not any(it.data.bold for it in items)
    assert scene.undo_stack.index() == before


def test_size_commit_parses_pt_per_target(paper_text):
    scene, items = paper_text
    _controller(items).commit_size_text("18")
    for it in items:
        assert _font_pt_from_mm(it.data, it.data.height_mm) == pytest.approx(18, abs=0.1)


def test_grow_steps_ladder_per_target(paper_text):
    scene, items = paper_text
    c = _controller(items)
    c.commit_size_text("12")
    c.grow()
    for it in items:
        assert _font_pt_from_mm(it.data, it.data.height_mm) == pytest.approx(14, abs=0.1)


def test_sync_mixed_values_blank(paper_text):
    scene, items = paper_text
    # Give item0 different bold + font → mixed bold and mixed family
    items[0].set_property("Bold", True)
    items[0].set_property("Font", "Courier New")
    # Give items different heights so pt values differ → size goes blank
    from firepro3d.paper_space import _mm_from_font_pt
    items[0].set_property("Height", _mm_from_font_pt(items[0].data, 10))
    items[1].set_property("Height", _mm_from_font_pt(items[1].data, 18))
    c = _controller(items)
    c.sync()
    assert c.bold_btn.isChecked() is False          # mixed → unpressed (Word)
    assert c.family_combo.currentIndex() == -1       # mixed → blank
    assert c.size_combo.currentText() == ""          # mixed pt → blank


def test_sync_uniform_values_reflected(paper_text):
    scene, items = paper_text
    for it in items:
        it.set_property("Bold", True)
    c = _controller(items)
    c.sync()
    assert c.bold_btn.isChecked() is True


def test_template_target_writes_direct_no_undo(paper_text, qapp):
    scene, _ = paper_text
    template = TextAnnotationItem(TextAnnotationData())
    c = _controller([template])
    before = scene.undo_stack.count()
    c._commit("Italic", True)
    assert template.data.italic is True
    assert scene.undo_stack.count() == before        # off-scene: no command


def test_invalid_size_text_is_noop(paper_text):
    scene, items = paper_text
    heights = [it.data.height_mm for it in items]
    _controller(items).commit_size_text("garbage")
    assert [it.data.height_mm for it in items] == heights


def test_alignment_commit(paper_text):
    scene, items = paper_text
    _controller(items).commit_alignment("Center")
    assert all(it.data.align == "C" for it in items)


def test_repeat_bold_commit_adds_no_undo_entry(paper_text):
    scene, items = paper_text
    c = _controller(items)
    c._commit("Bold", True)
    idx = scene.undo_stack.index()
    c._commit("Bold", True)              # all already bold → no-op
    assert scene.undo_stack.index() == idx


def test_grow_at_top_is_noop(paper_text):
    scene, items = paper_text
    c = _controller(items)
    c.commit_size_text("72")
    idx = scene.undo_stack.index()
    c.grow()
    for it in items:
        assert _font_pt_from_mm(it.data, it.data.height_mm) == pytest.approx(72, abs=0.1)
    assert scene.undo_stack.index() == idx
