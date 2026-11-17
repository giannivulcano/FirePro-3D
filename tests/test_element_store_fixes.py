"""Element store drift fixes (docs/specs/element-store.md D6 commits 8-10; G6, G7)."""
from __future__ import annotations

from tests._ph1_helpers import add_block, add_roof, ph1_cleanup, scene  # noqa: F401


def test_g6_roof_has_scale_manager_after_undo(qapp):
    ms = scene()
    add_roof(ms)
    ms.push_undo_state()
    add_roof(ms)
    ms.push_undo_state()
    ms.undo()                                   # the real restore path
    assert ms._roofs and all(r._scale_manager_ref is ms.scale_manager for r in ms._roofs)


def test_g7b_block_paste_lands_on_the_active_level(qapp):
    """R5 ruling: Ctrl+V of a block follows the active level (like walls / rooms)."""
    from PyQt6.QtCore import QPointF
    ms = scene()
    inst = add_block(ms)
    src = inst.level
    other = ms._level_manager.add_level(elevation=3000.0).name
    ctl = ms._modify_ctl
    assert ctl.write_clipboard([inst], QPointF(0.0, 0.0))
    for target, dy in ((src, 500.0), (other, 1000.0)):
        ms.active_level = target
        assert ctl.begin_paste()
        ctl.commit_paste(QPointF(0.0, dy))
    copies = [b for b in ms._block_instances if b is not inst]
    assert sorted(b.level for b in copies) == sorted([src, other])


def test_g7_duplicate_level_copies_blocks_and_select_same_level_selects_them(qapp):
    from firepro3d.level_widget import LevelWidget
    ms = scene()
    inst = add_block(ms)
    src = inst.level
    lm = ms._level_manager
    lw = LevelWidget(lm, ms)
    lw.duplicateLevel.connect(ms.duplicate_level_entities)     # main.py wiring
    lw._duplicate_level_from(lm.get(src))                      # the real Duplicate path
    new_name = next(lv.name for lv in lm.levels if lv.name != src)
    assert [b.level for b in ms._block_instances].count(new_name) == 1
    ms.clearSelection()
    ms._select_same_level(src)                                 # Select Same Level
    assert inst.isSelected()
