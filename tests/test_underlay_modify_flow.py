from firepro3d.underlay import Underlay


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
