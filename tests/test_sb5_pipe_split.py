"""SB5 Task 9 -- G-split (Q4, AC4): a block bound to a pipe follows the node1
half through the real split paths (sprinkler placement on a pipe; the pipe
tool's vertical split); the node2 half mints; no cascade. Q2 / Q3: deleting a
head keeps the node uid; a fitting carries no uid."""
from PyQt6.QtCore import QPointF

from firepro3d import marks
from firepro3d.node import Node
from firepro3d.sprinkler import Sprinkler
from tests._sb5_helpers import bound_tag, painted_values
from tests.test_sb2b_mint_sites import _pipe_template


def test_g_split_horizontal_keeps_the_uid_on_the_node1_half(qapp, shown_model_view):
    view, ms = shown_model_view
    a, b = ms.add_node(0.0, 0.0), ms.add_node(4000.0, 0.0)
    pipe = ms.add_pipe(a, b)
    tag = bound_tag(ms, pipe, "Pipe", {"M": "Mark"}, pos=(2000.0, -500.0))
    uid0 = pipe._uid
    ms.set_mode("sprinkler", Sprinkler(None))
    pt = QPointF(1000.0, 0.0)
    ms._press_sprinkler(None, pt, pt, pipe, None, pipe)    # sprinkler mode's click on a pipe
    assert pipe not in ms.sprinkler_system.pipes
    keep = next(p for p in ms.sprinkler_system.pipes if p.node1 is a)
    other = next(p for p in ms.sprinkler_system.pipes if p is not keep)
    assert keep._uid == uid0 and other._uid != uid0
    assert tag.scene() is ms and tag.element_host is keep  # no cascade
    assert painted_values(tag)["M"] == marks.get_mark(keep)


def test_g_split_vertical_keeps_the_uid_on_the_node1_half(qapp, shown_model_view):
    view, ms = shown_model_view
    na, nb = Node(0, 0), Node(0, 0)
    for n, z in ((na, 0.0), (nb, 3000.0)):
        ms.addItem(n)
        ms.sprinkler_system.add_node(n)
        n.z_pos = z
    pipe = ms.add_pipe(na, nb)                    # add_pipe never writes node elevation (Q4)
    tag = bound_tag(ms, pipe, "Pipe", {"M": "Mark"}, pos=(500.0, -500.0))
    uid0 = pipe._uid
    ms.push_undo_state()                                   # the pre-split snapshot
    mid = ms._pipe_ctl._find_or_split_vertical_at_z(QPointF(0, 0), 1500.0, _pipe_template())
    assert mid is not None
    keep = next(p for p in ms.sprinkler_system.pipes if p.node1 is na)
    other = next(p for p in ms.sprinkler_system.pipes if p is not keep)
    assert keep._uid == uid0 and other._uid != uid0
    assert tag.element_host is keep
    assert ms.element_by_uid(uid0) is keep                 # the uid index follows the node1 half
    ms.push_undo_state()                                   # the post-split snapshot
    ms.undo()                                              # back to the whole pipe
    assert ms.element_by_uid(uid0) in ms.sprinkler_system.pipes
    ms.redo()
    keep2 = ms.element_by_uid(uid0)
    assert keep2 is not None and keep2 in ms.sprinkler_system.pipes
    assert len(ms.sprinkler_system.pipes) == 2
    (tag2,) = ms._block_instances
    assert tag2.element_host is keep2                      # the bound tag re-links to the node1 half


def test_q2_head_delete_keeps_the_node_uid_and_q3_fitting_has_none(qapp, shown_model_view):
    view, ms = shown_model_view
    n = ms.add_node(0.0, 0.0)
    spr = ms.add_sprinkler(n)
    uid_n = n._uid
    assert spr._uid != uid_n
    ms.remove_sprinkler(n)
    assert n._uid == uid_n and ms.element_by_uid(uid_n) is n
    assert ms.element_by_uid(spr._uid) is None
    assert not hasattr(n.fitting, "_uid")
