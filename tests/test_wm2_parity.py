"""WM2 G7 -- a file with no override fields renders identically (WM-9).
Parity guard: passes at base 7f97f687 and at HEAD."""
import os

import fitz

from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.test_lt1_block_paper import _export, _render_model
from tests.test_lt1_block_paper import _line_def, _nested

# Golden recorded at base 7f97f687 by running this test there with
# WM2_RECORD=1 (prints the repr): (canvas pixel sum, lit-pixel count,
# sorted PDF strokes (width pt, x0, y0)). (0.51, 212.49, 198.32) is the
# block line (75 mm, 70 mm on the A4 sheet); the rest are sheet chrome.
_GOLDEN = (7751073330, 462, ((0.51, 212.49, 198.32), (0.7083, 186.99, 315.9),
                             (0.8499, 0.0, 0.0), (0.8499, 184.15, 84.99),
                             (0.8499, 203.99, 324.39), (1.4166, 28.33, 28.33)))


def _legacy_scene():
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.model_space import Model_Space
    c = _line_def("C")
    h = BlockDefinition.new(name="H", library="L", series="S",
                            primitives=[_nested(c.id)], origin=(0.0, 0.0))
    ms = Model_Space()
    for d in (c, h):
        ms.register_block_definition(BlockDefinition.from_dict(d.to_dict()))
    ms.place_block_instance(h.id, (0.0, 0.0), level=ms.active_level)
    return ms


def test_g7_canvas_and_pdf_match_golden(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    img = _render_model(_legacy_scene())
    pdf = _export(tmp_path, _legacy_scene(), 0.02, "g7.pdf")
    doc = fitz.open(str(pdf))
    try:
        strokes = sorted((round(d["width"], 4), round(d["rect"].x0, 2),
                          round(d["rect"].y0, 2))
                         for d in doc[0].get_drawings() if "s" in (d.get("type") or ""))
    finally:
        doc.close()
    # Every pixel: a 3-px grid misses the 1-px block line at row 200.
    px = [img.pixel(x, y) & 0xFFFFFF for x in range(400) for y in range(400)]
    sig = (sum(px), sum(1 for p in px if p), tuple(strokes))
    assert sig[1] > 0                     # the canvas really drew the block
    if os.environ.get("WM2_RECORD"):
        print("GOLDEN", repr(sig))
        return
    assert sig == _GOLDEN
