"""Preview zoom cap: the import dialog preview clamps zoom to [25%, 2000%] of
fit (raised from the old 1200% ceiling).
"""
from firepro3d.underlay_import_dialog import _PreviewView
from PyQt6.QtWidgets import QGraphicsScene


def test_zoom_max_is_2000_percent(qapp):
    view = _PreviewView(QGraphicsScene())
    assert _PreviewView._ZOOM_MAX == 20.0
    view.resize(400, 300)
    view._fit_scale = 1.0
    view._apply_zoom(1000.0)          # blow past the cap
    assert view.transform().m11() <= 20.0 + 1e-6
