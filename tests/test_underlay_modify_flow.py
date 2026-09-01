import pytest

from firepro3d.underlay import Underlay


class _StubParams:
    """Minimal stand-in for underlay_import_dialog.ImportParams — carries only the
    attributes Model_Space.replace_underlay reads."""

    def __init__(self, **kw):
        self.file_type = kw.get("file_type", "dxf")
        self.file_path = kw.get("file_path", "new.dxf")
        self.geom_list = kw.get("geom_list", [])
        self.scale = kw.get("scale", 1.0)
        self.base_x = kw.get("base_x", 0.0)
        self.base_y = kw.get("base_y", 0.0)
        self.selected_layers = kw.get("selected_layers", None)
        self.rotation = kw.get("rotation", 0.0)
        self.pdf_page = kw.get("pdf_page", 0)
        self.pdf_dpi = kw.get("pdf_dpi", 150)
        self.import_mode = kw.get("import_mode", "auto")
        self.layout = kw.get("layout", "")
        self.import_bounds = kw.get("import_bounds", None)


def _managed_record():
    r = Underlay(type="dxf", path="old.dxf", levels=["L1", "L3"],
                 snap=False, colour="#ff0000", line_weight_name="Medium",
                 visible=True)
    r.layer_overrides = {"WALLS": {"colour": "#00ff00"}}
    r.hidden_layers = ["GRID"]
    return r


def test_apply_import_params_preserves_management_fields():
    from firepro3d.underlay import apply_import_params_preserving_management
    rec = _managed_record()
    incoming = Underlay(type="dxf", path="new.dxf", levels=["Level 1"],
                        snap=True, colour="#c0c0c0", scale=2.0, rotation=90.0,
                        x=10.0, y=20.0)
    apply_import_params_preserving_management(rec, incoming)
    # geometry/placement overwritten:
    assert rec.path == "new.dxf"
    assert rec.scale == 2.0
    assert rec.rotation == 90.0
    assert rec.x == 10.0 and rec.y == 20.0
    # management preserved:
    assert rec.levels == ["L1", "L3"]
    assert rec.snap is False
    assert rec.colour == "#ff0000"
    assert rec.line_weight_name == "Medium"
    assert rec.layer_overrides == {"WALLS": {"colour": "#00ff00"}}
    assert rec.visible is True


def test_layer_overrides_reconciled_by_name_on_modify():
    from firepro3d.underlay import apply_import_params_preserving_management
    rec = _managed_record()  # WALLS override, GRID hidden
    incoming = Underlay(type="dxf", path="new.dxf")
    apply_import_params_preserving_management(
        rec, incoming, new_layer_names=["WALLS", "DOORS"])  # GRID gone
    assert "WALLS" in rec.layer_overrides       # kept
    assert "GRID" not in rec.hidden_layers      # dropped (layer vanished)


def test_preserves_locked_and_opacity_and_snap():
    from firepro3d.underlay import apply_import_params_preserving_management
    rec = Underlay(type="dxf", path="old.dxf", locked=True, opacity=0.5, snap=False)
    incoming = Underlay(type="dxf", path="new.dxf", locked=False, opacity=1.0, snap=True)
    apply_import_params_preserving_management(rec, incoming)
    assert rec.locked is True
    assert rec.opacity == 0.5
    assert rec.snap is False
    assert rec.path == "new.dxf"


# ─────────────────────────────────────────────────────────────────────────────
# Model_Space.replace_underlay + refresh_underlay(sync_from_item=) — DXF (async)
# ─────────────────────────────────────────────────────────────────────────────

def _build_underlay_group(scene, layers=None, x=0.0, y=0.0):
    """Build a DXF-like underlay group (mirrors test_underlay_integration)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath
    from PyQt6.QtWidgets import QGraphicsPathItem
    from firepro3d.constants import Z_UNDERLAY

    if layers is None:
        layers = ["A-WALL", "A-DOOR"]
    items = []
    for layer_name in layers:
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(100, 100)
        item = QGraphicsPathItem(path)
        pen = QPen(QColor("#c0c0c0"), 1.5)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setZValue(Z_UNDERLAY)
        item.setData(1, layer_name)
        scene.addItem(item)
        items.append(item)
    group = scene.createItemGroup(items)
    group.setZValue(Z_UNDERLAY)
    group.setPos(x, y)
    group.setData(0, "DXF Underlay")
    group.setData(2, sorted(set(layers)))
    return group


def _cleanup_worker(scene):
    worker = getattr(scene, "_dxf_worker", None)
    if worker is not None:
        worker.cancel()
        worker.quit()
        worker.wait(2000)


def _drain_dxf_worker(scene):
    """Block until the async DXF worker finishes and its queued
    finished_data → _on_dxf_finished slot has run on the main thread."""
    from PyQt6.QtWidgets import QApplication
    worker = getattr(scene, "_dxf_worker", None)
    if worker is None:
        return
    worker.wait(5000)
    # Pump the event loop so the queued finished_data signal is delivered.
    for _ in range(50):
        QApplication.processEvents()
        if getattr(scene, "_dxf_worker", None) is None:
            break


def test_replace_underlay_preserves_management_and_identity(qapp, tmp_path):
    """replace_underlay overwrites geometry/placement from params while the
    SAME record object stays in scene.underlays with its management fields
    intact. Exercises the DXF (async) path — field preservation is synchronous
    (happens before the async rebuild kicks off)."""
    import ezdxf
    from firepro3d.model_space import Model_Space

    dxf_file = tmp_path / "modify.dxf"
    doc = ezdxf.new()
    doc.layers.add("A-WALL")
    doc.modelspace().add_line((0, 0), (100, 100), dxfattribs={"layer": "A-WALL"})
    doc.saveas(str(dxf_file))

    scene = Model_Space()
    group = _build_underlay_group(scene, x=42.0, y=17.0)
    record = Underlay(type="dxf", path="old.dxf", x=42.0, y=17.0,
                      import_scale=1.0)
    record.colour = "#ff0000"
    record.levels = ["L1", "L3"]
    record.snap = False
    record.layer_overrides = {"WALLS": {"colour": "#00ff00"}}
    scene.underlays.append((record, group))

    params = _StubParams(
        file_type="dxf", file_path=str(dxf_file),
        scale=2.5, base_x=1.0, base_y=2.0,
        selected_layers=["A-WALL"], rotation=0.0,
        geom_list=[{"kind": "line", "layer": "A-WALL",
                    "x1": 0, "y1": 0, "x2": 10, "y2": 10}],
    )

    scene.replace_underlay(record, params)

    # Field preservation is SYNCHRONOUS (before the async rebuild kicks off).
    # Geometry/placement overwritten from params.
    assert record.path == str(dxf_file)
    assert record.import_scale == pytest.approx(2.5)
    assert record.import_base_x == pytest.approx(1.0)
    assert record.import_base_y == pytest.approx(2.0)
    assert record.x == pytest.approx(42.0)   # on-canvas anchor preserved
    assert record.y == pytest.approx(17.0)
    # Management fields preserved.
    assert record.colour == "#ff0000"
    assert record.levels == ["L1", "L3"]
    assert record.snap is False
    # WALLS override pruned (not in the new geom_list's single A-WALL layer).
    assert "WALLS" not in record.layer_overrides

    # Drive the async DXF rebuild to completion so the record re-registers.
    _drain_dxf_worker(scene)

    # Identity: the SAME record object is tracked after the async rebuild.
    assert any(d is record for d, _ in scene.underlays)


def test_refresh_underlay_sync_flag_skips_transform_sync(qapp, tmp_path):
    """refresh_underlay(sync_from_item=False) must NOT overwrite the record's
    scale/rotation from the item's live transform (the Modify flow relies on
    the NEW values already on the record surviving the rebuild)."""
    import ezdxf
    from firepro3d.model_space import Model_Space

    dxf_file = tmp_path / "syncflag.dxf"
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (50, 50))
    doc.saveas(str(dxf_file))

    scene = Model_Space()
    group = _build_underlay_group(scene, x=5.0, y=6.0)
    group.setScale(3.0)       # item transform differs from the record sentinel
    group.setRotation(15.0)
    record = Underlay(type="dxf", path=str(dxf_file),
                      scale=1.25, rotation=90.0)  # sentinels
    scene.underlays.append((record, group))

    scene.refresh_underlay(record, group, sync_from_item=False)

    # Sentinels survive — item's 3.0/15.0 were NOT synced back.
    assert record.scale == pytest.approx(1.25)
    assert record.rotation == pytest.approx(90.0)

    _cleanup_worker(scene)


# ─────────────────────────────────────────────────────────────────────────────
# UnderlayImportDialog prefill (Modify mode)
# ─────────────────────────────────────────────────────────────────────────────

def test_dialog_modify_prefill_sets_widgets(qapp):
    """Constructing the dialog with modify_record pre-fills the scale/rotation/
    dpi/mode widgets and retitles the window. Uses a non-existent path so the
    file load fails gracefully (no hang)."""
    from firepro3d.underlay_import_dialog import UnderlayImportDialog

    record = Underlay(type="dxf", path="/nonexistent/modify.dxf",
                      import_scale=0.5, rotation=45.0, dpi=300,
                      import_mode="vectors")
    dlg = UnderlayImportDialog(None, modify_record=record)
    try:
        assert "Modify" in dlg.windowTitle()
        assert dlg._custom_scale_edit.text() == "0.5"
        assert dlg._get_rotation() == pytest.approx(45.0)
        assert dlg._dpi_combo.currentText() == "300"
        assert dlg._mode_combo.currentText() == "Vectors"
    finally:
        dlg.deleteLater()
