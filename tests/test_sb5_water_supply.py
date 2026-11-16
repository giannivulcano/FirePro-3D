"""SB5 VC9 fix M1 -- re-placing the water supply keeps its identity, so a block
bound to the old supply follows it (the replacement takes the old uid, as the
pipe split does, Q4). The re-place is one undo step; Undo restores the old
supply as the tag's host."""
from tests._ph1_helpers import ph1_cleanup, scene  # noqa: F401
from tests._sb5_helpers import bound_tag


def _place(ms, node):
    """The real press path: the controller's water-supply press on *node*."""
    p = node.scenePos()
    ms._spr_ctl.press_water_supply(None, p, p, node, None, None)


def test_replacing_the_water_supply_keeps_the_uid_and_the_bound_tag(qapp):
    ms = scene()
    a, b = ms.add_node(0.0, 0.0), ms.add_node(3000.0, 0.0)
    ms.add_pipe(a, b)
    _place(ms, a)
    old = ms.water_supply_node
    old_uid = old._uid
    tag = bound_tag(ms, old, "Water Supply", {"N": "Name"}, pos=(0.0, -500.0))
    assert tag.element_host is old
    ms.push_undo_state()
    p0 = ms._undo_pos

    _place(ms, b)                                          # re-place on another node

    ws = ms.water_supply_node
    assert ws is not old and ws.scene() is ms and old.scene() is None
    assert ws._uid == old_uid
    assert tag.element_host is ws
    assert ms._undo_pos == p0 + 1                          # one undo step

    ms.undo()
    (back,) = ms._block_instances
    host = back.element_host
    assert host is ms.water_supply_node and host is not None
    assert host._uid == old_uid
    assert (host.pos().x(), host.pos().y()) == (0.0, 0.0)  # the old supply, on node a
