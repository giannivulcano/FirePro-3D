"""D11: hosted blocks never show in plan, whatever level / view range, and no
plan consumer can pick one up (select-all, rubber band, click, snap)."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform

from tests._hosted_blocks_helpers import gridline, defn


def _hosted(ms):
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    d = defn(ms)
    inst = ms.place_block_instance(d.id, (0, 0), host={
        "gridline": gl._uid, "offset_mm": 0.0, "along_mm": 0.0,
        "elevation_mm": 0.0, "facing": 1})
    return ms, d, inst


def test_hosted_hidden_on_every_level(qapp, shown_model_view):
    _view, ms = shown_model_view
    ms, d, inst = _hosted(ms)
    plain = ms.place_block_instance(d.id, (0, 0))
    lm = ms._level_manager
    for lvl in [l.name for l in lm.levels]:
        lm.apply_to_scene(ms, active_level=lvl)
        assert inst.isVisible() is False
    lm.apply_to_scene(ms, active_level=plain.level)
    assert plain.isVisible() is True


def _scene_with_pair(shown_model_view):
    view, ms = shown_model_view
    ms, d, inst = _hosted(ms)
    # the hosted pos is derived from the gridline: put the plain twin on it
    plain = ms.place_block_instance(d.id, inst.block_pos())
    ms._level_manager.apply_to_scene(ms, active_level=plain.level)
    return view, ms, inst, plain


def test_select_all_skips_hosted(qapp, shown_model_view):
    view, ms, inst, plain = _scene_with_pair(shown_model_view)
    ms.clearSelection()
    view._select_all_items()          # the real Ctrl+A entry (Model_View)
    assert plain.isSelected() is True
    assert inst.isSelected() is False


def test_rubber_band_skips_hosted(qapp, shown_model_view):
    view, ms, inst, plain = _scene_with_pair(shown_model_view)
    ms.clearSelection()
    c = QPointF(*inst.block_pos())
    rect = QRectF(c.x() - 500, c.y() - 500, 1000, 1000)
    for crossing in (True, False):
        ms.clearSelection()
        ms.commit_rubber_band(rect, crossing, False, view.viewportTransform())
        assert inst.isSelected() is False
    ms.commit_rubber_band(rect, True, False, view.viewportTransform())
    assert plain.isSelected() is True


def test_click_pick_skips_hosted(qapp, shown_model_view):
    view, ms, inst, plain = _scene_with_pair(shown_model_view)
    cands = ms.halo_candidates_at(QPointF(inst.block_pos()[0] + 50, inst.block_pos()[1]), 20.0, view.viewportTransform())
    assert inst not in cands
    assert plain in cands


def test_snap_skips_hosted(qapp, shown_model_view):
    from firepro3d.snap_engine import SnapEngine
    view, ms, inst, plain = _scene_with_pair(shown_model_view)
    eng = SnapEngine()
    at = QPointF(*inst.block_pos())
    ctl = eng.find(at, ms, view.viewportTransform())
    assert ctl is not None and ctl.source_item is plain     # positive control
    ms.delete_items([plain])          # only the hosted block is left under the cursor
    res = eng.find(QPointF(*inst.block_pos()), ms, view.viewportTransform())
    assert res is None or res.source_item is not inst


def test_fresh_hosted_hidden_before_any_level_pass(qapp, shown_model_view):
    """A hosted block just placed (no apply_to_scene yet) is already hidden and
    cannot be selected from plan."""
    view, ms = shown_model_view
    ms, d, inst = _hosted(ms)
    assert inst.isVisible() is False
    view._select_all_items()
    assert inst.isSelected() is False


def test_browser_show_cannot_reshow_hosted(qapp, shown_model_view):
    view, ms, inst, plain = _scene_with_pair(shown_model_view)
    ms._hide_items([inst, plain])
    assert plain.isVisible() is False
    ms._show_items([inst, plain])
    assert plain.isVisible() is True            # positive control
    assert inst.isVisible() is False
    ms.clearSelection()
    view._select_all_items()
    assert inst.isSelected() is False
    ms._hide_items([inst])
    ms._show_all_hidden()
    assert inst.isVisible() is False
