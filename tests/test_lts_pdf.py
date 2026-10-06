"""G-LTS3 -- a Fixed linetype prints at its authored mm (sheets / PDF)."""
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.lt3_support import make_linetype
from tests.test_lt1_block_paper import _export
from tests.test_lt3_pdf import _viewport_hlines


def _fixed_scene():
    ms = Model_Space()
    lt = make_linetype(screen="fixed")
    ms.register_block_definition(lt)
    ln = LineItem(QPointF(-1500, 0), QPointF(1500, 0))
    ln.style["linetype"] = lt.id
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    return ms


def test_g_lts3_fixed_linetype_prints_authored_mm(qapp, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    pdf = _export(tmp_path, _fixed_scene(), 0.01, "lts_fixed.pdf")      # 1:100
    full = [x1 - x0 for x0, x1, _ in _viewport_hlines(pdf) if 0.5 < x1 - x0]
    inner = full[1:-1]
    assert inner and all(abs(L - 6.0) <= 0.05 for L in inner), full
