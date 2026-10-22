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
    assert rows[0].toolTip(0) == "Hosted on B"


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


# -- G18 candidate order / tab-less pop / multi-select (T12 fix round) ----------------

def _gl_inst(ms):
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    return gl, _hosted(ms, gl)


def _copy_selected(m, key, inst):
    return m._views[key][0]._hosted_copies[id(inst)].isSelected()


def test_open_tab_beats_placed_section(mgr):
    m, ms, tabs = mgr
    gl, inst = _gl_inst(ms)
    m.place_section(QPointF(0, 0), QPointF(10000, 0))        # Section 1
    m.place_section(QPointF(0, 0), QPointF(10000, 0))        # Section 2
    m.open_section("Section 2")                              # only Section 2 has a tab
    assert m.focus_hosted(inst) is True
    assert m.open_names == ["Section 2"] and tabs.count() == 1
    assert _copy_selected(m, "Section 2", inst)


def test_open_nonparallel_tab_falls_through(mgr):
    m, ms, tabs = mgr
    gl, inst = _gl_inst(ms)
    m.place_section(QPointF(0, 0), QPointF(0, 10000))        # Section 1: vertical cut, open
    m.place_section(QPointF(0, 0), QPointF(10000, 0))        # Section 2: parallel, no tab
    m.open_section("Section 1")
    assert m.focus_hosted(inst) is True
    assert m.open_names == ["Section 1", "Section 2"]
    assert tabs.currentWidget() is m._views["Section 2"][1]
    assert _copy_selected(m, "Section 2", inst)
    assert id(inst) not in m._views["Section 1"][0]._hosted_copies


def test_cardinal_fallback_without_tab_or_placed(mgr):
    m, ms, tabs = mgr
    gl, inst = _gl_inst(ms)
    m.seed_cardinals()
    assert m.focus_hosted(inst) is True
    assert tabs.count() == 1 and len(m.open_names) == 1
    key = m.open_names[0]
    assert key in ("north", "south", "east", "west")
    assert _copy_selected(m, key, inst)


def test_cardinal_beats_placed_section(mgr):
    m, ms, tabs = mgr
    gl, inst = _gl_inst(ms)
    m.place_section(QPointF(0, 0), QPointF(10000, 0))        # placed, tab-less
    m.seed_cardinals()
    assert m.focus_hosted(inst) is True
    assert m.open_names[0] in ("north", "south", "east", "west")
    assert "Section 1" not in m.open_names


def test_first_parallel_placed_by_name_wins(mgr):
    m, ms, tabs = mgr
    gl, inst = _gl_inst(ms)
    m.place_section(QPointF(0, 0), QPointF(10000, 0))        # Section 1
    m.place_section(QPointF(0, 0), QPointF(10000, 0))        # Section 2
    m.rename_section("Section 2", "Alpha")                   # insertion order != name order
    assert m.focus_hosted(inst) is True
    assert m.open_names == ["Alpha"] and tabs.count() == 1


def test_rejected_tabless_candidate_is_dropped_hit_opens_one_tab(mgr):
    m, ms, tabs = mgr
    gl, inst = _gl_inst(ms)
    m.place_section(QPointF(10000, 0), QPointF(0, 0))        # Section 1: looks away from B
    m.place_section(QPointF(0, 0), QPointF(10000, 0))        # Section 2: shows B
    assert m.focus_hosted(inst) is True
    shown = m.open_names
    assert len(shown) == 1 and tabs.count() == 1
    rejected = ({"Section 1", "Section 2"} - set(shown)).pop()
    assert shown == ["Section 2"] and rejected == "Section 1"   # name order tried Section 1 first
    assert rejected not in m._views                          # test-built scene dropped again


def test_multiselect_plain_plus_hosted_selects_only_plain(mgr):
    m, ms, tabs = mgr
    gl, hosted = _gl_inst(ms)
    plain = ms.place_block_instance(defn(ms, "P").id, (500, 500))
    m.place_section(QPointF(0, 0), QPointF(10000, 0))
    br = _browser(ms)
    rows = _block_rows(br)
    assert len(rows) == 2
    emitted = []
    br.entitySelected.connect(emitted.append)
    for r in rows:
        r.setSelected(True)
    assert plain.isSelected()
    assert not hosted.isSelected()
    assert emitted and emitted[-1] is plain           # the hosted block never reaches the plain path


def test_hosted_click_clears_stale_plan_selection(mgr):
    m, ms, tabs = mgr
    gl, hosted = _gl_inst(ms)
    plain = ms.place_block_instance(defn(ms, "P").id, (500, 500))
    m.place_section(QPointF(0, 0), QPointF(10000, 0))
    plain.setSelected(True)
    br = _browser(ms)
    row = next(r for r in _block_rows(br) if r.data(0, _ROLE_ENTITY) == id(hosted))
    row.setSelected(True)
    assert ms.selectedItems() == []


def _press_delete(br):
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    assert br.eventFilter(br._tree, ev)          # the real Delete-key entry


def test_browser_delete_removes_hosted_block_one_undo(mgr):
    m, ms, tabs = mgr
    gl, hosted = _gl_inst(ms)
    ms.push_undo_state()
    br = _browser(ms)
    row = next(r for r in _block_rows(br) if r.data(0, _ROLE_ENTITY) == id(hosted))
    row.setSelected(True)
    p0 = ms._undo_pos
    _press_delete(br)
    assert ms._block_instances == []
    assert ms._undo_pos == p0 + 1
    ms.undo()
    assert len(ms._block_instances) == 1


def test_browser_delete_plain_plus_hosted_one_undo(mgr):
    m, ms, tabs = mgr
    gl, hosted = _gl_inst(ms)
    plain = ms.place_block_instance(defn(ms, "P").id, (500, 500))
    ms.push_undo_state()
    br = _browser(ms)
    for r in _block_rows(br):
        r.setSelected(True)
    p0 = ms._undo_pos
    _press_delete(br)
    assert ms._block_instances == []
    assert ms._undo_pos == p0 + 1
    ms.undo()
    assert len(ms._block_instances) == 2
