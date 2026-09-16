"""Worker curve-emission: native dicts under preserve_curves, tessellation without."""
import ezdxf
from firepro3d.dxf_import_worker import DxfImportWorker


def _worker(preserve):
    w = DxfImportWorker.__new__(DxfImportWorker)   # sync path — bypasses __init__
    w._layer_colors = {}
    w._preserve_curves = preserve
    return w


def _arc_entity():
    doc = ezdxf.new()
    msp = doc.modelspace()
    return msp.add_arc(center=(0, 0, 0), radius=100, start_angle=30, end_angle=120)


def test_arc_native_when_preserving():
    g = _worker(True)._extract_geometry(_arc_entity())
    assert g["kind"] == "arc"
    assert (round(g["rx"]), round(g["ry"]), round(g["rw"]), round(g["rh"])) == (-100, -100, 200, 200)
    assert round(g["start"]) == 30 and round(g["span"]) == 90


def test_arc_tessellated_when_not_preserving():
    g = _worker(False)._extract_geometry(_arc_entity())
    assert g["kind"] == "path_points"          # underlay regression guard: unchanged
    assert len(g["points"]) > 2
