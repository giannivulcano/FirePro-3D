"""SB4g T14 -- AC5 / G7: changing a System symbol's definition (Reload, the
path Workbench Promote / Reload end in: _swap_block_definition +
blockDefinitionsChanged) repaints every element using it. Raw sources: the
edit below is a 3000 mm line (+-1500 mm, written here), against sprinkler0's
579.85 mm centre-line circle (r 9.51192 x 30.48, R14) -- so the old extent
radius is about 290 mm."""
import json
import shutil
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF

from firepro3d import block_library
from firepro3d.geometry_2d import LineItem
from tests._sb4g_helpers import BG, SPR_IDS, WS_ID, head, render, scene, water_supply

# A real primitive record (LineItem.to_dict -> "draw_line"), not a hand-typed dict.
LINE = [LineItem(QPointF(-1500.0, 0.0), QPointF(1500.0, 1.0)).to_dict()]


def _edit_seed(root: Path, rel: str):
    f = root / "Symbols" / rel
    raw = json.loads(f.read_text(encoding="utf-8"))
    assert "primitives" in raw
    raw["primitives"] = LINE
    f.write_text(json.dumps(raw), encoding="utf-8")


def _lit(ms, x, y):
    """Any non-background pixel in a 9 x 9 px window round model (x, y)."""
    img = render(ms, QRectF(x - 20.0, y - 20.0, 40.0, 40.0), 9, 9)
    return any(img.pixel(i, j) != BG for i in range(9) for j in range(9))


def test_g7_reloading_a_system_symbol_redraws_every_element(qapp, tmp_path,
                                                            real_system_library):
    root = tmp_path / "system"
    shutil.copytree(real_system_library, root)
    block_library.set_system_root(str(root))      # the autouse fixture restores it
    ms = scene()
    na, a = head(ms, 0.0, 0.0)
    nb, b = head(ms, 0.0, 4000.0)
    ws = water_supply(ms, 0.0, 8000.0)
    assert a.definition().id == b.definition().id == SPR_IDS[0]
    assert ws.definition().id == WS_ID
    assert a.extent_radius() < 400.0 and not _lit(ms, 1200.0, 0.0)
    _edit_seed(root, "Sprinkler0.fpdb")
    _edit_seed(root, "Water Supply.fpdb")
    assert ms.reload_block_definition(SPR_IDS[0])
    assert ms.reload_block_definition(WS_ID)
    for item in (a, b, ws):
        assert item.extent_radius() >= 1400.0               # the new 3000 mm line
    for y in (0.0, 4000.0, 8000.0):
        assert _lit(ms, 1200.0, y)                          # drawn where the old symbol never was
    assert na.boundingRect().width() >= 2800.0               # AC6: node bounds follow
