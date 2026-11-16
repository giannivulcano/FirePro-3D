"""SB6 AC9 / D14 / G3 -- tags print at their authored size in sheet viewports at two
scales, and an elevation / section builds no copy of them. Raw: the WallTag hexagon is
10 mm across its corners (vertices +/-5 mm in WallTag.fpdb). Export idiom copied from
tests/test_sb1c_paper.py (not imported)."""
from unittest.mock import MagicMock

import fitz
import pytest
from PyQt6.QtCore import QRectF

from tests._sb6_helpers import add_wall, place_tag, tags_of
from tests.paper_mode_shim import set_paper_mode

_VP_X, _VP_Y, _VP_W = 65.0, 30.0, 80.0


def _scene():
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    ms._level_manager = LevelManager()
    w = add_wall(ms, p1=(-3000.0, 0.0), p2=(3000.0, 0.0))
    ms.push_undo_state()
    place_tag(ms, w, u=0.0, v=-1000.0)        # 20 mm (1:50) / 5 mm (1:200) above the sheet view's centre
    return ms


def _export(tmp_path, ms, scale, name):
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    half = _VP_W / 2.0 / scale
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"
    sheet.sheet_views = [SheetViewData("plan", "Plan: Level 1", "P", scale,
                                       _VP_X, _VP_Y, _VP_W, _VP_W)]
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (ms, QRectF(-half, -half, 2 * half, 2 * half))
    out = tmp_path / name
    paper_export.export_pdf([sheet], resolver, str(out), dpi=300)
    return out


def _hexagon_widths(pdf):
    """x-extent (mm) of stroked drawings inside the viewport sized like the hexagon
    (8-12 mm wide, 7-10 mm tall); the wall is far longer or far thinner at both scales."""
    pt = 25.4 / 72.0
    doc = fitz.open(str(pdf))
    try:
        out = []
        for d in doc[0].get_drawings():
            if "s" not in (d.get("type") or ""):
                continue
            r = d["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            inside = (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                      and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1)
            if inside and 8.0 < x1 - x0 < 12.0 and 7.0 < y1 - y0 < 10.0:
                out.append(x1 - x0)
        return out
    finally:
        doc.close()


@pytest.mark.parametrize("scale", [0.02, 0.005])              # 1:50, 1:200
def test_g3_tag_prints_at_its_authored_size(qapp, tmp_path, real_system_library, scale):
    set_paper_mode("bw")
    ms = _scene()
    try:
        widths = _hexagon_widths(_export(tmp_path, ms, scale, f"t{int(1 / scale)}.pdf"))
        assert len(widths) == 1, widths
        assert abs(widths[0] - 10.0) < 0.3, widths              # authored 10 mm at both scales
    finally:
        ms.cleanup()


def test_d14_elevation_builds_no_copy_of_a_tag(qapp, section_scene_for, real_system_library):
    from firepro3d.section_scene import _ROLE_SOURCE
    ms, sec = section_scene_for("north")
    w = add_wall(ms)
    ms.push_undo_state()
    tag = place_tag(ms, w)
    sec.rebuild()
    assert id(tag) not in sec._hosted_copies
    assert not any(it.data(_ROLE_SOURCE) is tag for it in sec.items())
    assert tags_of(ms) == [tag]                                  # the plan keeps it


def test_d14_a_section_scene_refuses_tag_mode(qapp, section_scene_for):
    """GC2: sections cannot host tags -- ``set_mode("tag")`` leaves the mode where it was."""
    _ms, sec = section_scene_for("north")
    sec.set_mode(None)
    sec.set_mode("tag")
    assert sec.mode in (None, "select")                           # [RED: "tag" in _HOST_EXTRA_MODES]
