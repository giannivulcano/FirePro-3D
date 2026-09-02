"""DXF $INSUNITS auto-scale: the factor stored is source-unit -> mm (mm per
source unit), consistent with the app's ``scale = real_mm / source_units``.
A previous table stored source-unit -> inches, making a mm DXF ~25.4x off.
"""
import ezdxf

from firepro3d.underlay_import_dialog import _DXF_INSUNITS, UnderlayImportDialog


def test_insunits_factors_are_source_to_mm():
    assert _DXF_INSUNITS[1][1] == 25.4
    assert _DXF_INSUNITS[2][1] == 304.8
    assert _DXF_INSUNITS[4][1] == 1.0
    assert _DXF_INSUNITS[5][1] == 10.0
    assert _DXF_INSUNITS[6][1] == 1000.0


def test_detect_dxf_units_feet_fills_scale_and_label(qapp):
    """The real detect path: a $INSUNITS=2 (feet) doc pre-fills the custom
    scale edit with 304.8 mm/unit and shows the 'Feet' units label."""
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 2  # Feet

    dlg = UnderlayImportDialog(None, levels=["Level 1"],
                               current_level="Level 1")
    dlg._detect_dxf_units(doc)

    assert dlg._custom_scale_edit.text() == "304.8"
    assert "Feet" in dlg._units_info_lbl.text()

    dlg.deleteLater()
