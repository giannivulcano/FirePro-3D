"""Blocks browser matches the sibling browsers' tree chrome (smoke 2026-09-23):
bold Library/Series folder rows, 16px indentation + decorated root (chevron
cells), no frame, the same margins — and it keeps the user's expand state
across the refresh every block change triggers."""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame

from firepro3d.block_definition import BlockDefinition


def _def(name, library, series):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [10, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def _browser(model_space):
    from firepro3d.blocks_browser import BlocksBrowser
    for n, lib, ser in (("Gate Valve", "Fire", "Valves"), ("Check", "Fire", "Valves"),
                        ("Pendent", "Fire", "Heads"), ("Tee", "Civil", "Pipes")):
        model_space.register_block_definition(_def(n, lib, ser))
    return BlocksBrowser(model_space)


def test_blocks_browser_tree_chrome_matches_siblings(model_space, qapp):
    from firepro3d.feature_browser import FeatureBrowser
    b = _browser(model_space)
    fb = FeatureBrowser()
    ref = fb._tree
    t = b._tree
    assert t.indentation() == ref.indentation() == 16
    assert t.rootIsDecorated() and t.frameShape() == QFrame.Shape.NoFrame
    assert b.layout().contentsMargins() == fb.layout().contentsMargins()
    assert t.font().pointSizeF() == ref.font().pointSizeF()
    libs = [t.topLevelItem(i) for i in range(t.topLevelItemCount())]
    assert [l.text(0) for l in libs] == ["Civil", "Fire"]
    for lib in libs:
        assert lib.font(0).bold(), "Library rows are bold"
        for i in range(lib.childCount()):
            ser = lib.child(i)
            assert ser.font(0).bold(), "Series rows are bold"
            for j in range(ser.childCount()):
                assert not ser.child(j).font(0).bold(), "block leaves are regular"


def test_blocks_browser_keeps_expand_state_across_refresh(model_space, qapp):
    b = _browser(model_space)
    t = b._tree
    fire = next(t.topLevelItem(i) for i in range(t.topLevelItemCount())
                if t.topLevelItem(i).text(0) == "Fire")
    heads = next(fire.child(i) for i in range(fire.childCount())
                 if fire.child(i).text(0) == "Heads")
    assert fire.isExpanded() and heads.isExpanded()        # default: open
    heads.setExpanded(False)
    model_space.register_block_definition(_def("Upright", "Fire", "Heads"))
    b.refresh()
    fire = next(t.topLevelItem(i) for i in range(t.topLevelItemCount())
                if t.topLevelItem(i).text(0) == "Fire")
    heads = next(fire.child(i) for i in range(fire.childCount())
                 if fire.child(i).text(0) == "Heads")
    assert not heads.isExpanded(), "a collapsed folder stays collapsed"
    assert heads.childCount() == 2
