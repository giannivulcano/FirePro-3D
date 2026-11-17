"""Element store drift fixes (docs/specs/element-store.md D6 commits 8-10; G6, G7)."""
from __future__ import annotations

from tests._ph1_helpers import (add_block, add_roof, block_definition,  # noqa: F401
                                ph1_cleanup, scene)


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


def test_g7c_duplicate_level_skips_notes_and_gridline_hosted_blocks(qapp):
    """R5 seam rulings (2026-11-17): Duplicate Level leaves out view-owned Notes
    (a copy would re-key to the current view and stack on the source plan) and
    gridline-hosted blocks (gridlines are level-less and not copied, so a copy
    would keep the original host and absolute elevation, exactly on top)."""
    import os
    from firepro3d.assets import system_blocks_path
    from firepro3d.block_library import load_block_file
    from firepro3d.level_widget import LevelWidget
    from firepro3d.system_blocks import NOTE_BLOCK_ID
    from tests._hosted_blocks_helpers import gridline
    ms = scene()
    plain = add_block(ms)                                      # positive control
    src = plain.level
    ms.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    ms.active_view_key = "plan:Plan: Level 1"
    note = ms.place_block_instance(
        NOTE_BLOCK_ID, (0.0, 0.0), note={"view": "plan:Plan: Level 1",
                                         "wrap_width_mm": 40.0, "box_height_mm": 8.0})
    gl = gridline(ms, (0.0, -5000.0), (0.0, 5000.0), "A")
    hosted = ms.place_block_instance(
        block_definition(ms).id, (0, 0), host={"gridline": gl._uid, "offset_mm": 200.0, "along_mm": 1500.0,
                      "elevation_mm": 0.0, "facing": 1})
    assert note.level == src and hosted.level == src
    lm = ms._level_manager
    lw = LevelWidget(lm, ms)
    lw.duplicateLevel.connect(ms.duplicate_level_entities)     # main.py wiring
    lw._duplicate_level_from(lm.get(src))                      # the real Duplicate path
    new_name = next(lv.name for lv in lm.levels if lv.name != src)
    copies = [b for b in ms._block_instances if b.level == new_name]
    assert len(copies) == 1                                    # the plain block only
    assert not copies[0].note and not copies[0].host
    assert len(ms._block_instances) == 4
