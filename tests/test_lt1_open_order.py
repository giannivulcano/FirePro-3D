"""LT1 seam: opening a project bakes underlay pens with the FILE's weight table.

``load_from_file`` builds cached underlays (pens baked via
``underlay_layer_pen``) before ``apply_paper_display_from_project`` installs
the file's weight table; ``_apply_loaded_file`` must re-pen afterwards.
Drives the real ``MainWindow._load_project`` end to end.
"""
import os

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsPathItem

import main as _main_module
from firepro3d.view_3d import View3D          # heavy import required before MainWindow
_main_module.View3D = View3D
from main import MainWindow

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef
from firepro3d.underlay import Underlay
from firepro3d.underlay_cache import cache_dir_for_project, write_cache


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    # Keep the real ~/.firepro3d autosave untouched (open cleans it up) and
    # skip the post-open template-push offer (a possible modal).
    recovery = str(tmp_path / "autosave" / "recovery.FPD")
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: recovery))
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push",
                        lambda self: None)
    w = MainWindow()
    yield w
    w._modified = False
    w.close()


def test_open_bakes_underlay_with_files_table(main_window, tmp_path):
    w = main_window
    src = tmp_path / "plan.dxf"
    src.write_bytes(b"x")
    proj = tmp_path / "p.fpd"
    rec = Underlay(type="dxf", path=str(src), line_weight_name="Bold")
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 0,
              "layer": "A"}]
    grp, _ = w.scene._build_batched_underlay_group(geoms, rec)
    w.scene.addItem(grp)
    w.scene.underlays.append((rec, grp))
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("Bold", 1.0)])
    assert w.scene.save_to_file(str(proj))
    write_cache(cache_dir_for_project(str(proj)), rec.cache_key(), geoms,
                source_mtime=os.path.getmtime(src))
    # The previous project's table lacks "Bold" (falls back when resolved).
    pd.set_project_line_weights(list(pd.FACTORY_LINE_WEIGHTS))
    w._load_project(str(proj))
    assert pd.resolve_line_weight_mm("Bold") == 1.0       # file table live
    _r2, g2 = w.scene.underlays[-1]
    widths = [c.pen().widthF() for c in g2.childItems()
              if isinstance(c, QGraphicsPathItem)
              and c.pen().style() != Qt.PenStyle.NoPen]
    assert widths == [pytest.approx(pd.canvas_weight_px(1.0))]
