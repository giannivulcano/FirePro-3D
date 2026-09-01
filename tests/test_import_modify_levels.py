from firepro3d.underlay import Underlay, apply_import_params_preserving_management


def test_modify_overwrites_levels_and_verified():
    rec = Underlay(type="dxf", path="x.dxf", levels=["Level 1"], scale_verified=False,
                   colour="#abcdef")           # colour = preserved management field
    incoming = Underlay(type="dxf", path="x.dxf", levels=["Level 2", "Level 3"],
                        scale_verified=True)    # freshly built from params
    apply_import_params_preserving_management(rec, incoming)
    assert rec.levels == ["Level 2", "Level 3"]     # authored (copied from incoming)
    assert rec.scale_verified is True               # authored
    assert rec.colour == "#abcdef"                  # preserved
