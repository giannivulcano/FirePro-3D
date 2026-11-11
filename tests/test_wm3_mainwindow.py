"""WM3 G7 -- real MainWindow: a Colour pick on an already-painted placed block
repaints it in the picked colour and is ONE undo step; undo restores it."""
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest

from tests.test_constraint_pick_ribbon import _plan_index, mw  # noqa: F401
from tests.test_lt1_block_paper import _render_model
from tests.wm2_support import ROWS, sprinkler_def
from tests.wm3_support import OVR, box_colours

_BOXES = [(300, r - 3, 340, r + 4) for r in ROWS.values()]   # the three Sprinkler lines


class _Paints(QObject):
    """Counts Paint events reaching a widget (the observable repaint)."""

    def __init__(self):
        super().__init__()
        self.n = 0

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Paint:
            self.n += 1
        return False


def _line_colours(ms):
    img = _render_model(ms)
    return [box_colours(img, b) for b in _BOXES]


def test_g7_panel_colour_pick_repaints_and_is_one_undo_step(mw, qapp, monkeypatch):
    from firepro3d import colour_picker, theme
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: OVR)
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    ms = mw.scene
    ms.set_mode("select")
    d = sprinkler_def()
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    ms.push_undo_state()
    vp = ms._snap_view().viewport()
    f = _Paints()
    vp.installEventFilter(f)
    try:
        ink = QColor(theme.detect().ink).name()            # sprinkler_def lines: Automatic
        assert _line_colours(ms) == [{ink}] * 3              # painted before the pick
        ms.clearSelection()
        inst.setSelected(True)
        qapp.processEvents()
        pm = mw.prop_manager
        assert pm._targets == [inst]
        before = ms._undo_pos
        # push_undo_state's sceneModified starts a 200 ms single-shot view
        # refresh (main.py _on_scene_modified): let it land, then prove idle.
        QTest.qWait(300)
        f.n = 0
        QTest.qWait(250)
        assert f.n == 0                                      # composition: idle view paints nothing
        pm._prop_widgets["Colour"].setCurrentText("Pick colour\u2026")   # the real combo
        QTest.qWait(100)
        assert inst.overrides["colour"] == OVR
        assert ms._undo_pos == before + 1                    # ONE step
        assert f.n >= 1                                      # the plan view repainted
        ms.clearSelection()                                  # selection accent sits above
        qapp.processEvents()
        assert _line_colours(ms) == [{OVR}] * 3
        ms.undo()
        qapp.processEvents()
        restored = [i for i in ms._block_instances if i.block_id == d.id]
        assert len(restored) == 1
        assert restored[0].overrides["colour"] == "as_authored"
        assert _line_colours(ms) == [{ink}] * 3
    finally:
        vp.removeEventFilter(f)
        ms.clearSelection()
        for i in [i for i in ms._block_instances if i.block_id == d.id]:
            ms.remove_block_instance(i)
        mw._modified = False
        qapp.processEvents()
