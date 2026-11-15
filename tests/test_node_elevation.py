"""Node elevation (todo "Node owns its node elevation"): Q9 guards that fail at base.

Each guard drives the real path (duplicate, paste records, the property panel,
copy-to-level) and asserts the copied / edited node's ceiling level, offset, z
and fitting type.
"""
import pytest
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.node import Node
from firepro3d.property_manager import PropertyManager
from firepro3d.sprinkler import Sprinkler

_panels = []


@pytest.fixture
def ms(qapp):
    s = Model_Space()
    s._level_manager = LevelManager()
    s.push_undo_state()
    yield s
    for pm in _panels:          # a dropped panel's pending refresh can abort pytest
        pm._refresh_timer.stop()
        pm.deleteLater()
    _panels.clear()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    s.cleanup()


def _node(s, x, y, level="Level 1", offset=-50.8):
    n = Node(x, y)
    s.addItem(n)
    s.sprinkler_system.add_node(n)
    n.ceiling_level = level
    n.ceiling_offset = offset
    n.z_pos = s._level_manager.get(level).elevation + offset
    return n


def _pair(s, off_a=-300.0, off_b=-600.0):
    """Two nodes on Level 1 with distinct offsets, joined by one pipe."""
    a = _node(s, 0, 0, offset=off_a)
    b = _node(s, 3000, 0, offset=off_b)
    p = s.add_pipe(a, b, None)
    return a, b, p


def _copy_of(s, src, dx, dy=0.0):
    want = src.scenePos() + QPointF(dx, dy)
    hits = [n for n in s.sprinkler_system.nodes
            if n is not src and (n.scenePos() - want).manhattanLength() < 1e-6]
    assert len(hits) == 1, f"expected one copy at {want}, found {len(hits)}"
    return hits[0]


def test_duplicate_keeps_each_node_offset(ms):
    a, b, p = _pair(ms)
    ms.clearSelection()
    for it in (a, b, p):
        it.setSelected(True)
    ms._modify_ctl.commit_duplicate(QPointF(0, 5000))
    for src in (a, b):
        cp = _copy_of(ms, src, 0, 5000)
        assert (cp.ceiling_level, cp.ceiling_offset) == (src.ceiling_level, src.ceiling_offset)
        assert cp.z_pos == pytest.approx(src.z_pos)


@pytest.mark.parametrize("order", ["ab", "ba"])
def test_far_end_node_takes_its_own_record(ms, order):
    a, b, p = _pair(ms)
    items = [a, b, p] if order == "ab" else [b, a, p]
    data = ms._clipboard_item_dicts(items)
    ms.paste_items(QPointF(0, 5000), data=data)
    for src in (a, b):
        cp = _copy_of(ms, src, 0, 5000)
        assert cp.ceiling_offset == pytest.approx(src.ceiling_offset)
        assert cp.z_pos == pytest.approx(src.z_pos)


def _hub_stack_with_head(s):
    low = _node(s, 0, 0, offset=0.0)
    hub = _node(s, 0, 0)
    high = _node(s, 0, 0, offset=6000.0)
    s.add_pipe(low, hub, None)
    s.add_pipe(hub, high, None)
    s.add_sprinkler(hub, Sprinkler(None))     # at base the template re-hosts the node,
    hub.ceiling_offset, hub.z_pos = 3000.0, 3000.0   # so host it after the head lands
    hub.fitting.update()
    return hub


@pytest.mark.parametrize("key,value,z", [("Ceiling Offset", "7000", 7000.0),
                                         ("Ceiling Level", "High", 8000.0)])
def test_sprinkler_panel_ceiling_edit_refreshes_fitting(ms, key, value, z):
    """The head's fitting type is re-derived from the new z, not left stale."""
    hub = _hub_stack_with_head(ms)
    ms._level_manager.add_level("High", 5000.0)
    before = hub.fitting.type
    pm = PropertyManager()
    _panels.append(pm)
    pm.show_properties(hub.sprinkler)
    pm._apply_property(key, value)
    assert hub.z_pos == pytest.approx(z)
    after = hub.fitting.type
    hub.fitting.update()                    # what a refresh derives from the new z
    assert hub.fitting.type != before       # the edit does change the type
    assert after == hub.fitting.type


def test_copy_to_level_retargets_the_ceiling(ms):
    from firepro3d.level_manager import PlanViewManager
    ms._level_manager.get("Level 2").elevation = 3000.0   # default Level 2 exists (3048)
    pvm = PlanViewManager()                 # the target level's view range, as in the app
    for name in ("Level 1", "Level 2"):
        pvm.create(name, ms._level_manager)
    ms._plan_view_manager = pvm
    a, b, p = _pair(ms)
    ms.copy_items_to_level([a, b, p], "Level 2")
    for src in (a, b):
        copies = [n for n in ms.sprinkler_system.nodes if n is not src
                  and (n.scenePos() - src.scenePos()).manhattanLength() < 1e-6]
        assert [c.ceiling_level for c in copies] == ["Level 2"]
        cp = copies[0]
        assert cp.ceiling_offset == pytest.approx(src.ceiling_offset)
        assert cp.z_pos == pytest.approx(3000.0 + src.ceiling_offset)


def test_drawing_onto_an_existing_node_keeps_its_ceiling(shown_model_view):
    """Q14: an existing node at the template z on another ceiling level is
    joined, never re-hosted."""
    from firepro3d.pipe import Pipe
    view, s = shown_model_view
    s._level_manager.get("Level 2").elevation = 3000.0   # default Level 2 exists (3048)
    s.set_mode("pipe", Pipe(None, None))           # template N1 = N2 = Level 1 / -50.8
    end = _node(s, 3000, 0, level="Level 2", offset=-3050.8)   # z -50.8
    s._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert s._pipe_ctl._commit_pipe_at(QPointF(3000, 0), None) is True
    assert end.pipes, "the pipe joins the existing node"
    assert (end.ceiling_level, end.ceiling_offset) == ("Level 2", -3050.8)
    assert end.z_pos == pytest.approx(-50.8)
