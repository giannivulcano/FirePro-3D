"""D9: placing in a section (AC1, AC2, AC11)."""
import json
import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from firepro3d.mime_types import MIME_BLOCK
from firepro3d.section_scene import HOSTED_REFUSAL
from tests._hosted_blocks_helpers import gridline, defn
from tests.test_section_classification import _placed_scene


def _scene(section_scene_for, with_gl=True):
    # FAR is created BEFORE B: nearest (B) and first-in-model-order (FAR) disagree.
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    far = gridline(ms, (0, -5000), (6000, -5000), "FAR")
    if not with_gl:
        far.translate(0, -10000)                             # FAR out of depth
    gl = gridline(ms, (0, -3000), (6000, -3000), "B") if with_gl else None
    sec.rebuild()
    return ms, sec, gl


def test_place_hosts_on_nearest_parallel(qapp, section_scene_for):
    ms, sec, gl = _scene(section_scene_for)
    d = defn(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    inst = sec.place_hosted_block(d.id, QPointF(2500.0, -1200.0))
    assert inst.host == {"gridline": gl._uid, "offset_mm": 0.0,
                         "along_mm": pytest.approx(2500.0),
                         "elevation_mm": pytest.approx(1200.0), "facing": 1}
    assert inst.isVisible() is False                             # plan-hidden (D11)
    assert id(inst) in sec._hosted_copies                        # drawn after the rebuild
    assert ms._undo_pos == depth0 + 1
    ms.undo()
    assert not ms.hosted_blocks_on(gl)


def test_refused_without_parallel_gridline(qapp, section_scene_for):
    ms, sec, _ = _scene(section_scene_for, with_gl=False)
    d = defn(ms)
    msgs = []
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    n = len(ms._block_instances)
    assert sec.can_host_at(QPointF(2500.0, -1200.0)) is False
    assert sec.place_hosted_block(d.id, QPointF(2500.0, -1200.0)) is None
    assert len(ms._block_instances) == n and msgs[-1] == HOSTED_REFUSAL


def _mime(block_id):
    m = QMimeData()
    m.setData(MIME_BLOCK, json.dumps({"id": block_id, "path": None}).encode())
    return m


def test_drop_into_section_view(qapp, section_scene_for):
    from firepro3d.elevation_view import SectionView
    ms, sec, gl = _scene(section_scene_for)
    d = defn(ms)
    view = SectionView(sec)
    view.resize(900, 700)
    view.show()
    QTest.qWaitForWindowExposed(view)
    vp, pt = view.viewport(), QPointF(view.mapFromScene(QPointF(2500.0, -1200.0)))
    act = Qt.DropAction.CopyAction
    mods = (Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    mime = _mime(d.id)
    enter = QDragEnterEvent(pt.toPoint(), act, mime, *mods)
    QApplication.sendEvent(vp, enter)
    assert enter.isAccepted()
    move = QDragMoveEvent(pt.toPoint(), act, mime, *mods)
    QApplication.sendEvent(vp, move)
    assert move.isAccepted()
    QApplication.sendEvent(vp, QDropEvent(pt, act, mime, *mods))
    (inst,) = ms.hosted_blocks_on(gl)
    assert inst.host["along_mm"] == pytest.approx(2500.0, abs=50.0)
    view.close()


def test_drop_refused_without_host_is_no_drop(qapp, section_scene_for):
    """AC2: dragging over a section with no parallel gridline shows no-drop and
    a drop places nothing."""
    from firepro3d.elevation_view import SectionView
    ms, sec, _ = _scene(section_scene_for, with_gl=False)
    d = defn(ms)
    view = SectionView(sec)
    view.resize(900, 700)
    view.show()
    QTest.qWaitForWindowExposed(view)
    vp, pt = view.viewport(), QPointF(view.mapFromScene(QPointF(2500.0, -1200.0)))
    act = Qt.DropAction.CopyAction
    mods = (Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    mime = _mime(d.id)
    n = len(ms._block_instances)
    QApplication.sendEvent(vp, QDragEnterEvent(pt.toPoint(), act, mime, *mods))
    move = QDragMoveEvent(pt.toPoint(), act, mime, *mods)
    move.accept()
    QApplication.sendEvent(vp, move)
    assert not move.isAccepted()
    QApplication.sendEvent(vp, QDropEvent(pt, act, mime, *mods))
    assert len(ms._block_instances) == n
    view.close()


def test_place_from_the_far_side_hosts_facing_minus_one(qapp, section_scene_for):
    """A section looking the other way (A/B reversed) stamps facing -1."""
    ms, sec = _placed_scene(section_scene_for, (10000, -8000), (0, -8000), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    sec.rebuild()
    b = sec.basis
    d = defn(ms)
    h = 0.5 * (b.h_min + b.h_max)
    inst = sec.place_hosted_block(d.id, QPointF(h, -1200.0))
    assert inst is not None and inst.host["gridline"] == gl._uid
    assert inst.host["facing"] == -1
