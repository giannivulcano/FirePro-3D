"""WM3 G3 -- By Category: the Model "Blocks" colour on the canvas, the paper
"Blocks" category colour on sheets in every colour mode (design D3, AC3)."""
import pytest
from PyQt6.QtGui import QColor

from firepro3d import paper_display as pd
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.test_lt1_block_paper import _crop, _export, _render_model
from tests.wm3_support import (AUTHORED, OVR, composite_scene, lit_outside_origin,
                               pdf_colours, rgb)

_PAPER = "#808000"     # paper "Blocks" colour for these tests (no authored component uses it)
_MODEL = "#00ff00"     # Model "Blocks" colour (canvas only); also unused by the block
_TEXTFILL = AUTHORED["textfill"]   # R3: the "H" box fill keeps its authored colour


def _paper_blocks(colour):
    cats = pd.load_paper_categories()
    cats["Blocks"]["color"] = colour
    pd.save_paper_categories(cats)


def test_g3_factory_model_blocks_colour_is_automatic(qapp, shipped_hatches):
    assert pd.model_blocks_colour() == pd.model_blocks_factory_colour() == "token:auto"
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    twin, _ = composite_scene(shipped_hatches, colour="token:auto")
    assert _render_model(ms) == _render_model(twin)


def test_g3_by_category_canvas_is_model_blocks_colour(qapp, shipped_hatches):
    pd.set_model_blocks_colour(_MODEL)
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    twin, _ = composite_scene(shipped_hatches, colour=_MODEL)
    assert _render_model(ms) == _render_model(twin)


def test_g3_model_blocks_colour_is_read_live_at_paint(qapp, shipped_hatches):
    pd.set_model_blocks_colour(_MODEL)
    ms, inst = composite_scene(shipped_hatches, {"colour": "by_category"})
    ops = inst.render_ops()
    assert lit_outside_origin(_render_model(ms)) == {_MODEL, _TEXTFILL}
    pd.set_model_blocks_colour(OVR)
    assert inst.render_ops() is ops                       # memo stable (approach A)
    assert lit_outside_origin(_render_model(ms)) == {OVR, _TEXTFILL}


@pytest.mark.parametrize("bad", ["", None, "token:blocks", "token:bg", "garbage"])
def test_set_model_blocks_colour_rejects_unpickable_values(qapp, bad):
    pd.set_model_blocks_colour(_MODEL)
    pd.set_model_blocks_colour(bad)
    assert pd.model_blocks_colour() == "token:auto"       # -> factory


@pytest.mark.parametrize("mode", [PaperColorMode.FULL_COLOR, PaperColorMode.BW,
                                  PaperColorMode.CUSTOM])
def test_g3_by_category_on_a_sheet_is_paper_blocks_colour(qapp, shipped_hatches,
                                                          tmp_path, mode):
    save_paper_color_mode(mode)
    _paper_blocks(_PAPER)
    pd.set_model_blocks_colour(_MODEL)                    # must NOT reach paper
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    twin, _ = composite_scene(shipped_hatches, colour=_PAPER)
    got = pdf_colours(_export(tmp_path, ms, 0.02, "bc.pdf"))
    assert got == pdf_colours(_export(tmp_path, twin, 0.02, "tw.pdf"))
    assert set(got[0]) == {rgb(_PAPER)}
    assert set(got[1]) == {rgb(_PAPER), rgb(_TEXTFILL)}   # the text-box fill keeps its own (R3)


# -- unit tests of the pass-time cache (not G3 guards: _blocks_colour's
# fallback reads the same paper category, so the hook is unobservable in
# output -- it only keeps QSettings off the paint path during a pass) -------

def test_unit_paper_hook_is_set_for_the_pass_and_restored(qapp, shipped_hatches):
    _paper_blocks(_PAPER)
    ms, inst = composite_scene(shipped_hatches, {"colour": "by_category"})
    assert inst._paper_blocks_colour is None
    saved = pd.apply_paper_overrides(ms, _crop(0.02), paper_scale=0.02)
    try:
        assert inst._paper_blocks_colour == QColor(_PAPER)
    finally:
        pd.restore_model_display(saved)
    assert inst._paper_blocks_colour is None


def test_unit_non_blocks_apply_block_callers_never_set_the_hook(qapp):
    """M3: bound labels, marker / elevation heads, gridline bubbles and room
    tags go through _apply_block with their OWNER's category and restore only
    3-tuples, so the hook is set for the Blocks category branch alone (their
    token:blocks, if any, reads the paper "Blocks" category directly)."""
    from tests.wm2_support import scene_with, sprinkler_def
    d = sprinkler_def()
    ms, inst = scene_with([d], d.id)
    cat = pd.load_paper_categories()["Blocks"]
    pd._apply_block(inst, cat, PaperColorMode.FULL_COLOR, 0.18, 0.02)
    assert inst._paper_blocks_colour is None
    pd._apply_block(inst, cat, PaperColorMode.FULL_COLOR, 0.18, 0.02, blocks_hook=True)
    assert inst._paper_blocks_colour is not None
