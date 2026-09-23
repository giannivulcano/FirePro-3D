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


def _browser(model_space, root):
    from firepro3d.blocks_browser import BlocksBrowser
    for n, lib, ser in (("Gate Valve", "Fire", "Valves"), ("Check", "Fire", "Valves"),
                        ("Pendent", "Fire", "Heads"), ("Tee", "Civil", "Pipes")):
        model_space.register_block_definition(_def(n, lib, ser))
    return BlocksBrowser(model_space, root=root)


def test_blocks_browser_tree_chrome_matches_siblings(model_space, qapp, tmp_path):
    from firepro3d.feature_browser import FeatureBrowser
    b = _browser(model_space, str(tmp_path))
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


def test_blocks_browser_keeps_expand_state_across_refresh(model_space, qapp, tmp_path):
    b = _browser(model_space, str(tmp_path))
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


# ── The browser shows the on-disk library (smoke 2026-09-23) ────────────────

def _tree_rows(t):
    out = []
    def walk(item, depth):
        f = item.font(0)
        out.append(("  " * depth + item.text(0), f.bold(), f.italic()))
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)
    for i in range(t.topLevelItemCount()):
        walk(t.topLevelItem(i), 0)
    return out


def _lib(tmp_path):
    from firepro3d import block_library as bl
    root = str(tmp_path)
    gate = _def("Gate Valve", "Fire", "Valves")
    check = _def("Check Valve", "Fire", "Valves")
    bl.save_to_library(gate, root=root)
    bl.save_to_library(check, root=root)
    bl.create_folder("Mech", root=root)
    return root, gate, check


def test_startup_shows_library_folders_and_blocks(model_space, qapp, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    root, gate, check = _lib(tmp_path)
    b = BlocksBrowser(model_space, root=root)          # empty project
    assert _tree_rows(b._tree) == [
        ("Fire", True, False),
        ("  Valves", True, False),
        ("    Check Valve", False, True),               # library-only: italic
        ("    Gate Valve", False, True),
        ("Mech", True, False),                           # empty folder shows
    ]


def test_project_blocks_merge_with_library(model_space, qapp, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    root, gate, check = _lib(tmp_path)
    model_space.register_block_definition(gate)                      # also on disk
    model_space.register_block_definition(_def("Tee", "Civil", "Pipes"))  # project-only
    b = BlocksBrowser(model_space, root=root)
    rows = _tree_rows(b._tree)
    assert ("    Gate Valve", False, False) in rows       # in project: regular
    assert ("    Check Valve", False, True) in rows       # still library-only
    assert [r for r in rows if r[0].strip() == "Gate Valve"] == [("    Gate Valve", False, False)]
    assert ("    Tee", False, False) in rows


def test_double_click_library_block_loads_and_places(model_space, qapp, tmp_path,
                                                      monkeypatch):
    from firepro3d.blocks_browser import BlocksBrowser
    import firepro3d.themed_message as tm
    monkeypatch.setattr(tm, "themed_info", lambda *a, **k: None)   # never block
    root, gate, check = _lib(tmp_path)
    b = BlocksBrowser(model_space, root=root)
    got = []
    b.blockActivated.connect(got.append)
    t = b._tree
    fire = t.topLevelItem(0)
    leaf = fire.child(0).child(0)                         # Check Valve
    assert leaf.text(0) == "Check Valve" and leaf.toolTip(0)
    t.itemDoubleClicked.emit(leaf, 0)
    assert check.id in model_space._block_definitions, "loaded into the project"
    assert got == [check.id], "placement starts on the loaded block"


def test_library_writes_refresh_the_browser(model_space, qapp, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    from firepro3d import block_library as bl
    root, gate, check = _lib(tmp_path)
    b = BlocksBrowser(model_space, root=root)
    bl.save_to_library(_def("Hanger", "Mech", "Supports"), root=root)
    assert ("    Hanger", False, True) in _tree_rows(b._tree)
