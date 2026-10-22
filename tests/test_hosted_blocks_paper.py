"""AC12: a hosted block plots on a sheet through the paper 'Blocks' row
(visibility included; there is no on-screen Blocks toggle). Real PDF export of
a SectionScene through a sheet viewport; selection by stroke geometry."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from tests._hosted_blocks_helpers import defn, gridline
from tests._section_paper_helpers import drawings, export_scene, strokes_near, to_paper
from tests.test_section_classification import _placed_scene

PLACE = QPointF(2500.0, -1200.0)     # section scene mm; the definition's line is
                                     # (0,0)->(100,0) (tests/_hosted_blocks_helpers.defn)
SCALE = 0.05                      # paper mm per scene mm (1:20); line = 5 mm


def _setup(section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 8000.0)
    gridline(ms, (0.0, -3000.0), (6000.0, -3000.0), "B")
    sec.rebuild()
    inst = sec.place_hosted_block(defn(ms).id, PLACE)
    assert inst is not None
    return ms, sec


def _line_rect():
    # The 100 mm primitive line at PLACE, projected through the viewport
    # (to_paper: VP centre + (pt - centre) * scale; viewport centred on PLACE).
    x0, y0 = to_paper(PLACE, PLACE, SCALE)
    x1, y1 = to_paper(QPointF(PLACE.x() + 100.0, PLACE.y()), PLACE, SCALE)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


@pytest.fixture
def blocks_row():
    """Set the paper 'Blocks' row Visible; restore the stored rows afterwards."""
    orig = pd.load_paper_categories()

    def set_visible(visible):
        cats = pd.load_paper_categories()
        cats["Blocks"]["visible"] = visible
        pd.save_paper_categories(cats)
    try:
        yield set_visible
    finally:
        pd.save_paper_categories(orig)


def test_plots_and_row_hides(qapp, tmp_path, section_scene_for, blocks_row):
    ms, sec = _setup(section_scene_for)
    blocks_row(True)
    pdf = export_scene(tmp_path, sec, SCALE, PLACE, "on.pdf")
    assert strokes_near(pdf, _line_rect())                  # plotted, at the placed spot
    blocks_row(False)
    pdf2 = export_scene(tmp_path, sec, SCALE, PLACE, "off.pdf")
    assert any("s" in d["type"] for d in drawings(pdf2))    # not an empty export
    assert not strokes_near(pdf2, _line_rect())             # the Blocks row hid it
