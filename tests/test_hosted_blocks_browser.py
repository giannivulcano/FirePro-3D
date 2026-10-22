"""G18: '(on B)' label; click focuses a view showing the block."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget
from firepro3d.level_manager import LevelManager
from firepro3d.model_browser import ModelBrowser, _ROLE_ENTITY
from firepro3d.model_space import Model_Space
from firepro3d.scale_manager import ScaleManager
from firepro3d.section_manager import SectionManager
from tests._hosted_blocks_helpers import gridline, defn


@pytest.fixture
def mgr(qapp):
    ms = Model_Space(); lm = LevelManager(); ms._level_manager = lm
    sm = ScaleManager(); ms.scale_manager = sm
    tabs = QTabWidget(); m = SectionManager(ms, lm, sm, tabs); ms._section_manager = m
    yield m, ms, tabs
    m.close_all()


def _hosted(ms, gl):
    return ms.place_block_instance(defn(ms).id, (0, 0), host={
        "gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1000.0,
        "elevation_mm": 0.0, "facing": 1})


def _browser(ms):
    br = ModelBrowser()
    br.set_scene(ms)
    br.refresh()
    return br


def _block_rows(br):
    root = br._tree.invisibleRootItem()
    for i in range(root.childCount()):
        top = root.child(i)
        if top.text(0).startswith("Blocks ("):
            return [top.child(j) for j in range(top.childCount())]
    return []


def test_label_suffix(mgr):
    m, ms, tabs = mgr
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    _hosted(ms, gl)
    br = _browser(ms)
    rows = _block_rows(br)
    assert [r.text(0) for r in rows] == ["A (on B)"]


def test_plain_block_keeps_plain_label(mgr):
    m, ms, tabs = mgr
    ms.place_block_instance(defn(ms).id, (0, 0))
    br = _browser(ms)
    rows = _block_rows(br)
    assert [r.text(0) for r in rows] == ["A"]


def test_focus_hosted_selects_copy_in_placed_parallel_section(mgr):
    m, ms, tabs = mgr
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    inst = _hosted(ms, gl)
    m.place_section(QPointF(0, 0), QPointF(10000, 0))
    assert m.focus_hosted(inst) is True
    sec = tabs.currentWidget().scene()
    assert sec._hosted_copies[id(inst)].isSelected()


def test_click_row_focuses_view_not_plan(mgr):
    m, ms, tabs = mgr
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    inst = _hosted(ms, gl)
    m.place_section(QPointF(0, 0), QPointF(10000, 0))
    br = _browser(ms)
    row = _block_rows(br)[0]
    assert row.data(0, _ROLE_ENTITY) == id(inst)
    row.setSelected(True)                         # the browser's real selection handler
    sec = tabs.currentWidget().scene()
    assert sec._hosted_copies[id(inst)].isSelected()
    assert not inst.isSelected()                  # plan-hidden: never selected in plan


def test_click_no_view_status(mgr):
    m, ms, tabs = mgr
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    inst = _hosted(ms, gl)
    gl.manip_rotate(30.0, QPointF(0, -3000))      # parallel to no cardinal / section
    msgs = []
    ms._show_status = lambda t, *a, **k: msgs.append(t)
    br = _browser(ms)
    _block_rows(br)[0].setSelected(True)
    assert msgs[-1] == "No section shows this block (its gridline B isn't parallel to any view)."
    assert tabs.count() == 0
    assert m.focus_hosted(inst) is False
