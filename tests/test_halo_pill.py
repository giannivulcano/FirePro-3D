import pytest
import main as _main_module
from firepro3d.view_3d import View3D          # heavy import required before MainWindow
_main_module.View3D = View3D                  # inject lazy global (mirrors multiview test)
from main import MainWindow


@pytest.fixture
def main_window(qapp):
    w = MainWindow()
    yield w
    w.close()


def test_halo_pill_toggles_scene_flag(main_window):
    w = main_window
    assert w.scene.halo_enabled is True         # default on
    w.footer.halo_pill.click()                  # drive the widget, not the slot
    assert w.scene.halo_enabled is False
    w.footer.halo_pill.click()
    assert w.scene.halo_enabled is True


def test_halo_pill_persists(main_window):
    w = main_window
    w.footer.halo_pill.setChecked(False)
    w._toggle_halo()
    assert w.settings.value("halo/enabled", True, type=bool) is False
