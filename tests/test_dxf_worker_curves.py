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


# ---------------------------------------------------------------------------
# Integration: _DialogExtractWorker end-to-end (proves the propagation chain)
# ---------------------------------------------------------------------------

def _doc_with_arc_and_spline():
    """Build an in-memory ezdxf doc with one ARC and one SPLINE in model space."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_arc(center=(0, 0, 0), radius=100, start_angle=30, end_angle=120)
    sp = msp.add_spline(fit_points=None, degree=3)
    sp.control_points = [(0, 0, 0), (10, 20, 0), (30, -20, 0), (40, 0, 0)]
    return doc


def _run_dialog_extract_worker_sync(doc, preserve_curves: bool) -> list:
    """Drive _DialogExtractWorker._run_inner() synchronously and return geoms.

    _run_inner() emits finished_geoms(geoms, layers) at the end. We connect
    a slot before calling _run_inner() directly (in-thread, no QThread.start())
    so the signal fires synchronously via a direct connection and we capture the
    payload without spinning an event loop.
    """
    from firepro3d.underlay_import_dialog import _DialogExtractWorker

    w = _DialogExtractWorker(doc, "Model", preserve_curves=preserve_curves)

    captured: list[list] = []

    def _slot(geoms, layers):
        captured.append(geoms)

    w.finished_geoms.connect(_slot)
    # Call _run_inner directly — this runs in the calling thread, so the signal
    # fires as a direct connection and _slot is invoked before _run_inner returns.
    w._run_inner()

    assert captured, "_DialogExtractWorker._run_inner() did not emit finished_geoms"
    return captured[0]


def test_dialog_extract_worker_propagates_preserve_curves_true(qapp):
    """Integration: _DialogExtractWorker with preserve_curves=True emits native
    arc and spline kinds — proves the propagation chain is wired correctly."""
    geoms = _run_dialog_extract_worker_sync(_doc_with_arc_and_spline(), preserve_curves=True)
    kinds = {g["kind"] for g in geoms}
    assert "arc" in kinds, f"expected 'arc' in kinds, got: {kinds}"
    assert "spline" in kinds, f"expected 'spline' in kinds, got: {kinds}"


def test_dialog_extract_worker_tessellates_when_preserve_curves_false(qapp):
    """Regression guard: _DialogExtractWorker with preserve_curves=False (the
    underlay default) tessellates arcs/splines to path_points, not native kinds."""
    geoms = _run_dialog_extract_worker_sync(_doc_with_arc_and_spline(), preserve_curves=False)
    kinds = {g["kind"] for g in geoms}
    assert "path_points" in kinds, f"expected 'path_points' in kinds, got: {kinds}"
    assert "arc" not in kinds, f"'arc' must not appear when preserve_curves=False"
