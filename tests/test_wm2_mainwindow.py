"""WM2 G12 -- real MainWindow: a panel pick on an already-painted placed block
repaints it at the picked weight and is ONE undo step; undo restores it."""
from firepro3d.stroke_style import canvas_px
from tests.test_constraint_pick_ribbon import _plan_index, mw  # noqa: F401
from tests.test_lt1_block_paper import _render_model
from tests.test_lt2_canvas_paper import _run_near
from tests.wm2_support import COL, ROWS, SPRINKLER, sprinkler_def


def _runs(ms):
    img = _render_model(ms)
    return {c: _run_near(img, COL, r) for c, r in ROWS.items()}


def test_g12_panel_pick_repaints_and_is_one_undo_step(mw, qapp):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    ms = mw.scene
    ms.set_mode("select")
    d = sprinkler_def()
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    ms.push_undo_state()
    try:
        authored = {c: round(canvas_px(w)) for c, (_y, w) in SPRINKLER.items()}
        thick = round(canvas_px("Thick"))
        assert thick not in authored.values()          # composition: distinguishable
        assert _runs(ms) == authored                   # painted before the pick
        ms.clearSelection()
        inst.setSelected(True)
        qapp.processEvents()
        pm = mw.prop_manager
        assert pm._targets == [inst]
        before = ms._undo_pos
        pm._prop_widgets["Weight"].setCurrentText("Thick")   # the real combo
        qapp.processEvents()
        assert inst.overrides["weight"] == "Thick"
        assert ms._undo_pos == before + 1                    # ONE step
        assert set(_runs(ms).values()) == {thick}            # repainted
        ms.undo()
        qapp.processEvents()
        restored = [i for i in ms._block_instances if i.block_id == d.id]
        assert len(restored) == 1
        assert restored[0].overrides["weight"] == "as_authored"
        assert _runs(ms) == authored
    finally:
        ms.clearSelection()
        for i in [i for i in ms._block_instances if i.block_id == d.id]:
            ms.remove_block_instance(i)
        mw._modified = False
        qapp.processEvents()
