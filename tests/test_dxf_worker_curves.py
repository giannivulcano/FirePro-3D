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


def _spline_entity():
    doc = ezdxf.new()
    msp = doc.modelspace()
    # add_spline(fit_points=...) leaves control_points empty until the CAD app
    # constructs them, so build the entity directly with control_points assigned.
    ent = msp.add_spline(fit_points=None, degree=3)
    ent.control_points = [(0, 0, 0), (10, 20, 0), (30, -20, 0), (40, 0, 0)]
    return ent


def test_spline_native_when_preserving():
    g = _worker(True)._extract_geometry(_spline_entity())
    assert g["kind"] == "spline"
    assert len(g["control_points"]) >= 2
    assert g["degree"] >= 1


def test_spline_tessellated_when_not_preserving():
    g = _worker(False)._extract_geometry(_spline_entity())
    assert g["kind"] == "path_points"     # underlay regression guard


def test_block_import_dialog_sets_preserve_curves(qapp):
    from firepro3d.block_import_dialog import BlockImportDialog
    dlg = BlockImportDialog(None)
    try:
        assert dlg._preserve_curves is True
    finally:
        dlg.deleteLater()


def test_underlay_import_dialog_defaults_no_preserve(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None)
    try:
        assert dlg._preserve_curves is False
    finally:
        dlg.deleteLater()
