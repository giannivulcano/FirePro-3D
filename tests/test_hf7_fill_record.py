"""HF7 D1: the fill record through the shared geom helpers."""
import pytest

from firepro3d import dwg_converter as dc
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _fill():
    return {
        "kind": "fill", "layer": "A", "color": "#112233",
        "solid": False, "mask": False, "tone": False,
        "loops": [[{"kind": "path_points", "layer": "A", "color": "#112233",
                    "points": [(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0)],
                    "closed": True}]],
        "exact_loops": [[{"kind": "circle", "layer": "A", "color": "#112233",
                          "x": 10.0, "y": 0.0, "w": 10.0, "h": 10.0}]],
        "lines": [[11.0, 1.0, 19.0, 9.0]],
        "pattern": {"name": "ANSI31", "families": [
            {"angle": -45.0, "base": [2.0, 3.0], "offset": [1.0, 1.0], "dashes": [4.0, -2.0]}]},
    }


def test_geom_children_only_for_fill():
    assert [c["kind"] for c in dc.geom_children(_fill())] == ["path_points"]
    assert dc.geom_children({"kind": "line"}) == []


def test_expand_fills_keeps_list_identity_without_a_fill():
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1}]
    assert dc.expand_fills(geoms) is geoms


def test_rep_points_and_bounds_recurse():
    assert (10.0, 0.0) in dc.geom_rep_points(_fill())
    assert dc.compute_geom_bounds([_fill()]) == [10.0, 0.0, 20.0, 10.0]


def test_import_transform_moves_every_part():
    out = dc.apply_import_transform([_fill()], 2.0, 10.0, 0.0)[0]
    assert out["loops"][0][0]["points"][0] == (0.0, 0.0)
    assert out["exact_loops"][0][0]["x"] == 0.0 and out["exact_loops"][0][0]["w"] == 20.0
    assert out["lines"] == [[2.0, 2.0, 18.0, 18.0]]
    fam = out["pattern"]["families"][0]
    assert fam["base"] == [-16.0, 6.0]
    assert fam["offset"] == [2.0, 2.0] and fam["dashes"] == [8.0, -4.0]
    assert fam["angle"] == -45.0


def test_import_transform_rotates_families_literals():
    out = dc.apply_import_transform([_fill()], 1.0, 0.0, 0.0, 90.0)[0]
    fam = out["pattern"]["families"][0]
    assert fam["angle"] == pytest.approx(45.0)
    assert fam["offset"] == pytest.approx([-1.0, 1.0])
    assert fam["base"] == pytest.approx([-3.0, 2.0])


def _along_family_fill():
    """A fill whose line runs along its family direction (-45 degrees)."""
    f = _fill()
    f["lines"] = [[0.0, 0.0, 10.0, -10.0]]
    return f


@pytest.mark.parametrize("rot", [90.0, 30.0])
@pytest.mark.parametrize("s", [1.0, 2.0])
def test_family_angle_follows_the_rotated_lines(rot, s):
    import math
    src = _along_family_fill()
    out = dc.apply_import_transform([src], s, 0.0, 0.0, rot)[0]
    x1, y1, x2, y2 = out["lines"][0]
    line_deg = math.degrees(math.atan2(y2 - y1, x2 - x1))
    fam = out["pattern"]["families"][0]
    assert (fam["angle"] - line_deg) % 180.0 == pytest.approx(0.0, abs=1e-9) \
        or (fam["angle"] - line_deg) % 180.0 == pytest.approx(180.0, abs=1e-9)
    # Spacing: the offset's perpendicular distance to the line direction is
    # the source's, scaled by s, and its length is scaled by s.
    def perp(off, d_deg):
        r = math.radians(d_deg)
        return abs(-off[0] * math.sin(r) + off[1] * math.cos(r))
    src_fam = src["pattern"]["families"][0]
    assert perp(fam["offset"], line_deg) == pytest.approx(
        perp(src_fam["offset"], -45.0) * s)
    assert math.hypot(*fam["offset"]) == pytest.approx(
        math.hypot(*src_fam["offset"]) * s)


def test_unknown_family_keys_survive_a_transform():
    src = _fill()
    src["pattern"]["families"][0]["tag"] = "keep-me"
    out = dc.apply_import_transform([src], 2.0, 1.0, 1.0, 30.0)[0]
    assert out["pattern"]["families"][0]["tag"] == "keep-me"


_FILL_BOX = {
    "kind": "fill", "layer": "A", "color": "#112233",
    "solid": True, "mask": False, "tone": False,
    "loops": [[{"kind": "path_points", "layer": "A", "color": "#112233",
                "points": [(1000.0, 2000.0), (1100.0, 2000.0),
                           (1100.0, 2050.0), (1000.0, 2050.0)],
                "closed": True}]],
    "lines": [], "pattern": None,
}


def test_place_import_bounds_see_a_fill_only_import(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.underlay_import_dialog import ImportParams
    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    p = ImportParams()
    p.file_path = "synthetic.dxf"
    p.file_type = "dxf"
    p.geom_list = [dict(_FILL_BOX)]
    p.scale = 2.0
    p.base_x, p.base_y, p.rotation = 1000.0, 2000.0, 0.0
    scene.begin_place_import(p)
    r = scene._place_import_bounds
    assert (r.x(), r.y(), r.width(), r.height()) == (0.0, 0.0, 200.0, 100.0)
    scene.set_mode(None)
    scene.cleanup()


def test_dialog_pdf_base_point_sees_a_fill_only_page(qapp):
    from PyQt6.QtCore import QObject, pyqtSignal
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    class _Worker(QObject):
        done = pyqtSignal(list, list)

    dlg = UnderlayImportDialog()
    w = _Worker()
    dlg._pdf_worker = w
    dlg._pdf_extract_ctx = {"path": "x.pdf", "page": 0, "dpi": 150,
                            "mode": "auto", "reset_base": True}
    w.done.connect(dlg._on_pdf_extract_finished)
    w.done.emit([dict(_FILL_BOX)], ["A"])
    assert dlg._base_x_edit.value_mm() == pytest.approx(1000.0)
    assert dlg._base_y_edit.value_mm() == pytest.approx(2050.0)
