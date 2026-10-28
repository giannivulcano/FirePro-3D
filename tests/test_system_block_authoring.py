"""System-block authoring guards (block-system.md "System library tier",
authoring path 2026-10-27: Workbench + dev gate + Promote to System)."""
import json
import os

import pytest

from firepro3d import block_library


def _fpdb(path, block_id, *, library="Workbench", series="Hatches",
          name=None, version=1, **extra):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {"schema": 1, "id": block_id, "library": library, "series": series,
           "name": name or os.path.basename(path)[:-5], "version": version,
           "primitives": [], **extra}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    return path


def test_dev_gate_reads_dot_git_file_or_dir(tmp_path):
    pkg = tmp_path / "firepro3d"
    pkg.mkdir()
    assert block_library._dev_gate_at(str(pkg)) is False
    (tmp_path / ".git").write_text("gitdir: elsewhere")   # a worktree's .git is a FILE
    assert block_library._dev_gate_at(str(pkg)) is True


def test_dev_gate_override_and_default_off_in_tests():
    assert block_library.dev_gate() is False              # conftest autouse
    block_library.set_dev_gate(True)
    try:
        assert block_library.dev_gate() is True
    finally:
        block_library.set_dev_gate(False)


def test_workbench_is_an_ordinary_writable_library():
    assert block_library.WORKBENCH_LIBRARY == "Workbench"
    assert not block_library.is_reserved_library("Workbench")
    assert block_library.is_reserved_library("System")


@pytest.fixture
def tiers(tmp_path):
    sysroot, user = tmp_path / "sys", tmp_path / "lib"
    shipped = _fpdb(str(sysroot / "Hatches" / "Brick.fpdb"), "system-hatches-brick",
                    library="System", version=2)
    wb = _fpdb(str(user / "Workbench" / "Hatches" / "Brick.fpdb"),
               "system-hatches-brick", version=3)
    block_library.set_system_root(str(sysroot))
    yield str(user), shipped, wb
    block_library.set_system_root(None)


def test_gate_off_system_owns_the_clash(tiers):
    root, shipped, wb = tiers
    found = block_library._find_by_id("system-hatches-brick", root)
    assert found[3]["path"] == shipped
    assert block_library.is_system_block("system-hatches-brick", root)


def test_gate_on_workbench_owns_the_clash(tiers):
    root, shipped, wb = tiers
    block_library.set_dev_gate(True)
    found = block_library._find_by_id("system-hatches-brick", root)
    assert found[3]["path"] == wb and found[3]["version"] == 3
    assert not block_library.is_system_block("system-hatches-brick", root)
    entries = {e["path"]: e for e in block_library.list_library(root)}
    assert entries[shipped]["duplicate"] and entries[shipped]["tier"] == "system"


def test_gate_on_other_user_folders_still_lose(tiers):
    root, shipped, wb = tiers
    _fpdb(os.path.join(root, "Styles", "Hatches", "Brick.fpdb"),
          "system-hatches-brick", library="Styles")
    block_library.set_dev_gate(True)
    assert block_library._find_by_id("system-hatches-brick", root)[3]["path"] == wb
    os.remove(wb)
    assert block_library._find_by_id("system-hatches-brick", root)[3]["path"] == shipped


def test_shipped_index_lists_system_tier_only(tiers):
    root, shipped, wb = tiers
    assert block_library.shipped_index() == {"system-hatches-brick": shipped}


def test_dev_gate_detects_beside_the_package(tmp_path, monkeypatch):
    pkg = tmp_path / "firepro3d"
    pkg.mkdir()
    monkeypatch.setattr(block_library, "__file__", str(pkg / "block_library.py"))
    block_library.set_dev_gate(None)
    try:
        assert block_library.dev_gate() is False
        (tmp_path / ".git").mkdir()
        assert block_library.dev_gate() is True
    finally:
        block_library.set_dev_gate(False)


def _cap(path, block_id, cap, **kw):
    # read_meta flags a capability by a truthy record (capability_folder.FLAGS)
    extra = {"repeat": {"pieces": []}} if cap == "repeat" else (
        {"end": {"size": 1.0}} if cap == "end" else {"tile": {"width": 1.0}})
    return _fpdb(path, block_id, **extra, **kw)


def test_linetype_and_end_pickers_list_system(tmp_path, monkeypatch):
    sysroot = tmp_path / "sys"
    _cap(str(sysroot / "Linetypes" / "Dash.fpdb"), "system-linetypes-dash",
         "repeat", library="System", series="Linetypes")
    _cap(str(sysroot / "End Types" / "Arrow.fpdb"), "system-end-types-arrow",
         "end", library="System", series="End Types")
    block_library.set_system_root(str(sysroot))
    monkeypatch.setattr("firepro3d.app_data.linetypes_dir", lambda: str(tmp_path / "u1"))
    monkeypatch.setattr("firepro3d.app_data.end_types_dir", lambda: str(tmp_path / "u2"))
    try:
        from firepro3d import capabilities, linetype_choices
        assert [r[1] for r in linetype_choices._folder_linetypes()] == ["system-linetypes-dash"]
        assert [r[1] for r in capabilities._folder_ends()] == ["system-end-types-arrow"]
    finally:
        block_library.set_system_root(None)


def test_scan_tiered_user_wins_only_under_gate(tmp_path):
    from firepro3d.capability_folder import scan_tiered
    sysroot, user = tmp_path / "sys", tmp_path / "wb"
    s = _cap(str(sysroot / "Linetypes" / "Dash.fpdb"), "lt-dash", "repeat", library="System")
    u = _cap(str(user / "Dash.fpdb"), "lt-dash", "repeat")
    block_library.set_system_root(str(sysroot))
    try:
        assert [r[2] for r in scan_tiered(str(user), "repeat")] == [os.path.abspath(s)]
        block_library.set_dev_gate(True)
        assert [r[2] for r in scan_tiered(str(user), "repeat")] == [os.path.abspath(u)]
    finally:
        block_library.set_system_root(None)


def test_gate_on_workbench_copy_file_does_not_steal_the_id(tiers):
    root, shipped, wb = tiers
    copy_ = _fpdb(os.path.join(root, "Workbench", "Hatches", "Brick - Copy.fpdb"),
                  "system-hatches-brick", name="Brick")    # sorts before Brick.fpdb
    block_library.set_dev_gate(True)
    assert block_library._find_by_id("system-hatches-brick", root)[3]["path"] == wb
    assert block_library.is_copy(copy_, "system-hatches-brick", root)


from firepro3d import system_promote  # noqa: E402


@pytest.fixture
def gate(tmp_path):
    sysroot, root = tmp_path / "sys", tmp_path / "lib"
    sysroot.mkdir()
    block_library.set_system_root(str(sysroot))
    block_library.set_dev_gate(True)
    yield str(sysroot), str(root)
    block_library.set_system_root(None)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_first_promote_mints_slug_and_writes_both(gate):
    sysroot, root = gate
    wb = _fpdb(os.path.join(root, "Workbench", "Line Types", "Fire Main.fpdb"),
               "uuid-1", series="Line Types", version=4)
    res = system_promote.promote("uuid-1", root)
    assert res.new_id == "system-line-types-fire-main" and res.version == 4
    shipped = _read(res.shipped_path)
    assert res.shipped_path == os.path.join(sysroot, "Line Types", "Fire Main.fpdb")
    assert (shipped["id"], shipped["library"], shipped["version"]) == (
        "system-line-types-fire-main", "System", 4)
    w = _read(wb)
    assert (w["id"], w["library"], w["version"]) == (
        "system-line-types-fire-main", "Workbench", 4)


def test_repromote_keeps_id_and_bumps_shipped_version(gate):
    sysroot, root = gate
    _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick",
          library="System", version=2)
    _fpdb(os.path.join(root, "Workbench", "Hatches", "Brick.fpdb"),
          "system-hatches-brick", version=2)
    res = system_promote.promote("system-hatches-brick", root)
    assert (res.new_id, res.version) == ("system-hatches-brick", 3)
    assert _read(res.shipped_path)["version"] == 3


def test_repromote_after_rename_moves_the_shipped_file(gate):
    sysroot, root = gate
    old = _fpdb(os.path.join(sysroot, "Hatches", "Brick.fpdb"), "system-hatches-brick",
                library="System", version=2)
    _fpdb(os.path.join(root, "Workbench", "Hatches", "Red Brick.fpdb"),
          "system-hatches-brick", version=2)
    res = system_promote.promote("system-hatches-brick", root)
    assert res.removed_path == old and not os.path.exists(old)
    assert _read(os.path.join(sysroot, "Hatches", "Red Brick.fpdb"))["version"] == 3


def test_filename_clash_adopts_shipped_id(gate):            # D1
    sysroot, root = gate
    _fpdb(os.path.join(sysroot, "Hatches", "Concrete.fpdb"),
          "builtin-hatch-concrete", library="System", version=1)
    wb = _fpdb(os.path.join(root, "Workbench", "Hatches", "Concrete.fpdb"),
               "uuid-c", version=5)
    res = system_promote.promote("uuid-c", root)
    assert (res.old_id, res.new_id, res.version) == ("uuid-c", "builtin-hatch-concrete", 2)
    assert _read(wb)["id"] == "builtin-hatch-concrete"
    assert _read(res.shipped_path)["version"] == 2


def test_refusals_write_nothing(gate):
    sysroot, root = gate
    _fpdb(os.path.join(root, "Styles", "Hatches", "Mine.fpdb"), "uuid-m", library="Styles")
    with pytest.raises(system_promote.PromoteRefused, match="Workbench"):
        system_promote.promote("uuid-m", root)
    _fpdb(os.path.join(root, "Workbench", "Symbols", "Valve.fpdb"), "uuid-v",
          series="Symbols",
          primitives=[{"type": "block_instance", "block_id": "uuid-not-shipped"}])
    with pytest.raises(system_promote.PromoteRefused, match="uuid-not-shipped"):
        system_promote.promote("uuid-v", root)
    block_library.set_dev_gate(False)
    with pytest.raises(system_promote.PromoteRefused, match="source checkout"):
        system_promote.promote("uuid-v", root)
    assert os.listdir(sysroot) == []


def test_unsaved_project_copy_refused(gate):
    sysroot, root = gate
    path = _fpdb(os.path.join(root, "Workbench", "Hatches", "Dots.fpdb"), "uuid-d", version=2)
    defn = block_library.load_block_file(path)
    defn.version = 3                                       # edited in the project, not saved
    with pytest.raises(system_promote.PromoteRefused, match="Save the block"):
        system_promote.promote("uuid-d", root, project_def=defn)
    assert os.listdir(sysroot) == []


def test_write_shipped_refused_without_gate(gate):
    sysroot, root = gate
    block_library.set_dev_gate(False)
    with pytest.raises(block_library.SystemLibraryReadOnly):
        block_library.write_shipped(os.path.join(sysroot, "X.fpdb"), {})


def _committed(ms, name, *, repeat=None, end=None, prims=None):
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    d = ms.commit_block_definition(
        block_id=None, name=name, library="Lib", series="S",
        primitives=prims or [LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()],
        origin=(0.0, 0.0), place_instance=False)
    if repeat is not None:
        d.set_repeat(repeat)
    if end is not None:
        d.set_end(end)
    return d.id


def test_retarget_follows_linetype_and_end_refs(qapp):          # D2
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    e_old = _committed(ms, "EndOld", end={"trim": 0.0})
    e_new = _committed(ms, "EndNew", end={"trim": 0.0})
    lt_old = _committed(ms, "LtOld", repeat={"length": 10.0})
    lt_new = _committed(ms, "LtNew", repeat={"length": 10.0})
    lt3 = _committed(ms, "Lt3", repeat={"length": 10.0,
                                        "ends": {"start": e_old, "finish": e_old}})
    sym = _committed(ms, "Sym")
    styled = LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()
    styled["style"] = {"linetype": lt_old, "start": {"end": e_old}}
    host = _committed(ms, "Host", prims=[styled])
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    ms.addItem(line)
    line.style = {**line.style, "linetype": lt_old,
                  "start": {**line.style["start"], "end": e_old}}
    inst = ms.place_block_instance(sym, (0.0, 0.0), overrides={"linetype": lt_old})
    ms.push_undo_state()
    assert ms.retarget_block_refs(lt_old, lt_new) >= 3
    assert line.style["linetype"] == lt_new
    assert inst.overrides["linetype"] == lt_new
    assert ms._block_definitions[host].primitives[0]["style"]["linetype"] == lt_new
    assert ms.retarget_block_refs(e_old, e_new) >= 3
    assert line.style["start"]["end"] == e_new
    assert ms._block_definitions[host].primitives[0]["style"]["start"]["end"] == e_new
    assert ms._block_definitions[lt3].repeat["ends"] == {"start": e_new, "finish": e_new}


def test_adopt_refused_when_another_workbench_file_holds_the_shipped_id(gate):
    sysroot, root = gate
    _fpdb(os.path.join(sysroot, "Hatches", "Concrete.fpdb"),
          "builtin-hatch-concrete", library="System", version=1)
    _fpdb(os.path.join(root, "Workbench", "Hatches", "Concrete.fpdb"), "uuid-c")
    _fpdb(os.path.join(root, "Workbench", "Hatches", "Old Concrete.fpdb"),
          "builtin-hatch-concrete")
    with pytest.raises(system_promote.PromoteRefused, match="Old Concrete.fpdb"):
        system_promote.promote("uuid-c", root)


def _browser_leaf(browser, block_id, top_text=None):
    from firepro3d.blocks_browser import _ROLE_ID

    def walk(it):
        if it.data(0, _ROLE_ID) == block_id:
            return it
        for i in range(it.childCount()):
            r = walk(it.child(i))
            if r is not None:
                return r
    t = browser._tree
    for i in range(t.topLevelItemCount()):
        top = t.topLevelItem(i)
        if top_text is not None and top.text(0) != top_text:
            continue
        r = walk(top)
        if r is not None:
            return r


def _wb_browser(model_space, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    root = str(tmp_path / "lib")
    wb = _fpdb(os.path.join(root, "Workbench", "Hatches", "Dots.fpdb"), "uuid-dots",
               tile={"width": 1.0})
    return BlocksBrowser(model_space, root=root), wb


def test_promote_verb_on_workbench_leaf_under_gate(model_space, qapp, tmp_path):
    block_library.set_dev_gate(True)
    b, wb = _wb_browser(model_space, tmp_path)
    got = []
    b.promoteRequested.connect(lambda i, p: got.append((i, p)))
    menu = b._build_context_menu(_browser_leaf(b, "uuid-dots"))
    acts = {a.text(): a for a in menu.actions()}
    assert "Promote to System..." in acts
    acts["Promote to System..."].trigger()
    assert got == [("uuid-dots", wb)]


def test_no_promote_verb_without_gate(model_space, qapp, tmp_path):
    b, _wb = _wb_browser(model_space, tmp_path)
    menu = b._build_context_menu(_browser_leaf(b, "uuid-dots"))
    assert "Promote to System..." not in [a.text() for a in menu.actions()]


def test_shipped_leaf_keeps_duplicate_when_workbench_owns_id(model_space, qapp, tiers):
    from firepro3d.blocks_browser import BlocksBrowser
    root, shipped, wb = tiers
    block_library.set_dev_gate(True)
    b = BlocksBrowser(model_space, root=root)
    leaf = _browser_leaf(b, "system-hatches-brick", top_text=block_library.SYSTEM_LIBRARY)
    texts = [a.text() for a in b._build_context_menu(leaf).actions()]
    assert "Duplicate to library..." in texts
    assert "Promote to System..." not in texts     # promote from the Workbench leaf


def test_refile_prefill_is_workbench_for_a_workbench_file(monkeypatch, tmp_path):
    from firepro3d import block_editor
    from firepro3d.block_definition import BlockDefinition
    root = str(tmp_path / "lib")
    seen = []
    monkeypatch.setattr(block_editor, "_ask_library_target",
                        lambda scene, parent, r, mode, initial, **kw: seen.append(initial))
    d = BlockDefinition.new(name="X", library="System", series="Hatches",
                            primitives=[], origin=(0.0, 0.0))
    d.source_path = os.path.join(root, "Workbench", "Hatches", "X.fpdb")
    block_editor.run_refile_dialog(None, d, None, root=root)
    d.source_path = os.path.join(root, "Styles", "Hatches", "X.fpdb")
    block_editor.run_refile_dialog(None, d, None, root=root)
    assert [i[1] for i in seen] == ["Workbench", "Styles"]
