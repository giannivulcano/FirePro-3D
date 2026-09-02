"""When the user picks a layout of a multi-layout DXF, the preview info area
reads 'Loading <layout>…' at the moment extraction is kicked off (instead of
sitting on the static 'Select a layout to preview.' hint until the worker
delivers). The finished/summary path then overwrites it with the entity count.
"""
from __future__ import annotations

import ezdxf

from firepro3d.underlay_import_dialog import UnderlayImportDialog


def _multi_layout_doc():
    """A DXF doc with a paper-space layout named 'Basement' plus Model."""
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (10, 0))
    lay = doc.layouts.new("Basement")
    lay.add_line((0, 0), (5, 5))
    return doc


def test_layout_switch_shows_loading_placeholder(qapp):
    doc = _multi_layout_doc()

    dlg = UnderlayImportDialog(None, levels=["Level 1"],
                               current_level="Level 1")
    dlg._file_type = "dxf"
    dlg._on_dxf_read("plan.dxf", doc)

    # Kick off extraction for the paper-space layout. The worker starts on a
    # thread; we do NOT pump the loop, so the finished callback (which rewrites
    # the label with the entity count) has not run yet.
    dlg._extract_for_layout("Basement")

    assert "Loading" in dlg._info_lbl.text()
    assert "Basement" in dlg._info_lbl.text()

    dlg.deleteLater()
