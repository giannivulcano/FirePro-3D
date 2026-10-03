"""Hatch D-A39 "Blocks only": the five patterns ship as real ``.fpdb`` blocks,
seed the Hatch patterns folder once, load into a project on new / open
outside the undo history, and are real block dependencies. No code table.
"""
from __future__ import annotations

import json
import math
import os

import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath

from firepro3d import app_data
from firepro3d import block_library as bl
from firepro3d import hatch_patterns as hp
from firepro3d import hatch_render as hr
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import RectangleItem
from firepro3d.model_space import Model_Space

_D = 3.0 * math.sqrt(2.0)       # Diagonal / Cross Hatch cell: 3 mm printed spacing

# (a) The shipped content, pinned independently of any generator.
_EXPECTED = {
    "Diagonal.fpdb": ("builtin-hatch-diagonal", "Diagonal",
                      {"w": _D, "h": _D, "row_shift": 0.0, "size": "drafting"},
                      [("draw_line", (0.0, 0.0, _D, -_D))]),
    "Cross Hatch.fpdb": ("builtin-hatch-cross-hatch", "Cross Hatch",
                         {"w": _D, "h": _D, "row_shift": 0.0, "size": "drafting"},
                         [("draw_line", (0.0, 0.0, _D, -_D)),
                          ("draw_line", (0.0, -_D, _D, 0.0))]),
    "Horizontal.fpdb": ("builtin-hatch-horizontal", "Horizontal",
                        {"w": 3.0, "h": 3.0, "row_shift": 0.0, "size": "drafting"},
                        [("draw_line", (0.0, 0.0, 3.0, 0.0))]),
    "Concrete.fpdb": ("builtin-hatch-concrete", "Concrete",
                      {"w": 6.0, "h": 6.0, "row_shift": 0.0, "size": "drafting"},
                      [("draw_line", (1.0, -1.0, 2.0, -1.2)),
                       ("draw_line", (2.0, -1.2, 1.4, -2.0)),
                       ("draw_line", (1.4, -2.0, 1.0, -1.0)),
                       ("draw_line", (4.0, -3.5, 5.0, -3.8)),
                       ("draw_line", (5.0, -3.8, 4.3, -4.6)),
                       ("draw_line", (4.3, -4.6, 4.0, -3.5)),
                       ("draw_circle", (3.0, -1.5, 0.2)),
                       ("draw_circle", (1.5, -4.5, 0.2)),
                       ("draw_circle", (5.0, -1.0, 0.2)),
                       ("draw_circle", (2.6, -5.2, 0.2))]),
    "Brick.fpdb": ("builtin-hatch-brick", "Brick",
                   {"w": 225.0, "h": 75.0, "row_shift": 112.5, "size": "model"},
                   [("draw_line", (0.0, 0.0, 225.0, 0.0)),
                    ("draw_line", (0.0, 0.0, 0.0, -75.0))]),
}


def _geom(p):
    if p["type"] == "draw_line":
        return ("draw_line", (*p["pt1"], *p["pt2"]))
    if p["type"] == "draw_circle":
        return ("draw_circle", (p["cx"], p["cy"], p["radius"]))
    return (p["type"], None)


def test_shipped_files_hold_the_five_patterns():
    folder = hp.shipped_patterns_dir()
    files = sorted(n for n in os.listdir(folder) if n.endswith(".fpdb"))
    assert files == sorted(_EXPECTED)
    idx = json.load(open(os.path.join(folder, "index.json"), encoding="utf-8"))
    for fname, (bid, name, tile, prims) in _EXPECTED.items():
        data = json.load(open(os.path.join(folder, fname), encoding="utf-8"))
        assert (data["id"], data["name"]) == (bid, name)
        assert (data["library"], data["series"]) == ("System", "Hatches")
        assert data["tile"]["size"] == tile["size"]
        for k in ("w", "h", "row_shift"):
            assert data["tile"][k] == pytest.approx(tile[k], abs=1e-9), (fname, k)
        got = [_geom(p) for p in data["primitives"]]
        assert [g[0] for g in got] == [e[0] for e in prims], fname
        for (_t, gv), (_t2, ev) in zip(got, prims):
            assert gv == pytest.approx(ev, abs=1e-9), fname
        assert idx[fname] == {"id": bid, "name": name, "version": data["version"],
                              "thumbnail": None, "tile": True}
    # Legacy names still alias to the frozen ids the files carry (D-A29).
    ids = {v[0] for v in _EXPECTED.values()}
    assert set(hp.LEGACY_ALIAS.values()) <= ids


# ── (b) seeding ─────────────────────────────────────────────────────────────

def _ids_in(folder):
    return {json.load(open(os.path.join(folder, n), encoding="utf-8"))["id"]
            for n in os.listdir(folder) if n.endswith(".fpdb")}


def test_seed_copies_missing_once_keeps_edits_and_never_reseeds(qapp, tmp_path):
    folder = tmp_path / "Hatches"
    folder.mkdir()
    # The user's edited Diagonal, under another file name: same id, new content.
    edited = json.load(open(os.path.join(hp.shipped_patterns_dir(), "Diagonal.fpdb"),
                            encoding="utf-8"))
    edited["primitives"] = edited["primitives"] * 2
    edited["version"] = 7
    (folder / "My diagonal.fpdb").write_text(json.dumps(edited), encoding="utf-8")

    copied = hp.seed_hatch_folder(str(folder))
    assert sorted(copied) == sorted(v[0] for v in _EXPECTED.values()
                                    if v[0] != hp.BUILTIN_DIAGONAL)
    assert not (folder / "Diagonal.fpdb").exists()          # edit not shadowed
    mine = json.loads((folder / "My diagonal.fpdb").read_text(encoding="utf-8"))
    assert mine["version"] == 7 and len(mine["primitives"]) == 2
    idx = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    assert all(idx[f]["tile"] is True for f in ("Brick.fpdb", "Concrete.fpdb",
                                                "Cross Hatch.fpdb", "Horizontal.fpdb"))
    # Every shipped pattern is now offered by the folder scan (pickers).
    assert {bid for _n, bid, _p in hp.library_patterns(str(folder))} == \
        {v[0] for v in _EXPECTED.values()}

    # Deleted shipped pattern is not re-seeded: the folder is seeded once.
    os.remove(folder / "Brick.fpdb")
    assert hp.seed_hatch_folder(str(folder)) == []
    assert hp.BUILTIN_BRICK not in _ids_in(str(folder))

    # Another folder is its own first run.
    other = tmp_path / "Other"
    assert len(hp.seed_hatch_folder(str(other))) == 5
    assert _ids_in(str(other)) == {v[0] for v in _EXPECTED.values()}


def test_seed_defaults_to_the_configured_hatch_folder(qapp):
    folder = app_data.hatch_patterns_dir()
    assert hp.seed_hatch_folder() and len(_ids_in(folder)) == 5
    assert QSettings("GV", "FirePro3D").value(hp.HATCH_SEEDED_KEY)


# ── (e) code table gone ─────────────────────────────────────────────────────

def _red(img, x, y):
    c = QColor(img.pixel(x, y))
    return c.red() > 200 and c.green() < 90 and c.blue() < 90


def test_no_code_table_unloaded_ref_draws_the_tone(qapp):
    assert hp.resolve_tile("diagonal", None) is None
    assert hp.resolve_tile(hp.BUILTIN_BRICK, Model_Space().block_registry) is None
    for gone in ("builtin_tiles", "_builtin_specs", "BUILTIN_IDS", "is_builtin_ref"):
        assert not hasattr(hp, gone), gone

    class _Canvas:
        _hatch_paper_scale = None
        block_registry = Model_Space().block_registry      # empty project

    img = QImage(200, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(0.05, 0.05)                                    # 424 mm cells → ~21 px
    clip = QPainterPath()
    clip.addRect(QRectF(0, 0, 4000, 4000))
    hr.paint_fill(p, clip, scene=_Canvas(), tile_ref="diagonal",
                  colour=QColor("#ff0000"))
    p.end()
    tone = QColor(img.pixel(100, 100))
    assert tone != QColor("white")                         # never vanish (D-A36)
    assert all(QColor(img.pixel(x, y)) == tone             # uniform: no lines
               for x in range(10, 190, 7) for y in range(10, 190, 7))


# ── (f) a pattern is a real dependency ──────────────────────────────────────

def test_host_block_bundles_the_shipped_pattern(qapp, tmp_path, shipped_hatches):
    sc = Model_Space()
    shipped_hatches(sc)
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type, r.fill_pattern = "hatch", "diagonal"      # legacy name
    host = BlockDefinition.new(name="Slab", library="Mine", series="S",
                               origin=(0.0, 0.0), primitives=[r.to_dict()])
    sc.register_block_definition(host)
    reg = sc.block_registry
    bundle = reg.bundle_for(host.id)
    assert set(bundle) == {hp.BUILTIN_DIAGONAL}
    assert bundle[hp.BUILTIN_DIAGONAL]["tile"]["size"] == "drafting"
    assert host.id in reg.users_of(hp.BUILTIN_DIAGONAL)
    assert reg.would_cycle(hp.BUILTIN_DIAGONAL, host.id)
    # Through the library file: the saved host carries the pattern, so a
    # project without the folder pattern still gets it with the host.
    path = bl.save_to_library(host, root=str(tmp_path), bundled=bundle)
    fresh = Model_Space()
    fresh.load_blocks_from_files([path], root=str(tmp_path))
    assert hp.resolve_tile("diagonal", fresh.block_registry) is not None


# ── (c) / (d) new + open through the real MainWindow paths ──────────────────

@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow (isolated QSettings / block library via conftest)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d import snap_engine
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    w._modified = False
    w.close()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _render(scene, rect, px_w, px_h):
    img = QImage(px_w, px_h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, px_w, px_h), rect)
    p.end()
    return img


def _ink_runs(img, y, x0, x1):
    """Runs of non-white pixels along row *y* (hatch lines: many; tone: one)."""
    white = QColor("white").rgb()
    runs, prev = 0, False
    for x in range(x0, x1):
        cur = img.pixel(x, y) != white
        runs += cur and not prev
        prev = cur
    return runs


def _assert_unloadable_by_undo(scene):
    assert not scene.can_undo()                            # no step was added
    assert hp.BUILTIN_DIAGONAL in scene._undo_stack[0]["block_definitions"]
    scene.push_undo_state()                                # a user edit
    while scene.can_undo():
        scene.undo()
    assert hp.BUILTIN_DIAGONAL in scene._block_definitions


def test_new_project_section_cut_wall_renders_hatch(mw):
    from tests._paper_iso_helpers import make_wall
    win = mw
    assert hp.library_patterns()                           # startup seeded the folder
    win.new_file()                                         # File > New
    sc = win.scene
    w = make_wall(sc, (0, 0), (4000, 0), "Level 1")
    w._display_color = "#ff0000"
    w._display_section_color = None                        # lines only, no body
    w._is_section_cut = True
    sc.update()
    br = w.sceneBoundingRect()
    rect = QRectF(-200, br.center().y() - 600, 4400, 1200)
    img = _render(sc, rect, 880, 240)                      # 0.2 px / mm
    # A row inside the wall band, clear of the default gridline at y = 0.
    y = int((br.center().y() - rect.top()) * 0.2) - 8
    assert _ink_runs(img, y, 60, 820) >= 6                 # hatch lines, not tone
    assert sum(_red(img, x, y) for x in range(60, 820)) >= 4
    assert hp.BUILTIN_DIAGONAL in sc._block_definitions
    _assert_unloadable_by_undo(sc)


def test_opening_an_old_file_loads_its_legacy_pattern(mw, tmp_path):
    # An old file: a block whose fill says "diagonal", no pattern definition.
    src = Model_Space()
    r = RectangleItem(QPointF(-500, -500), QPointF(500, 500))
    r.fill_type, r.fill_pattern = "hatch", hp.BUILTIN_DIAGONAL
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    rec = r.to_dict()
    rec["fill"]["pattern"] = "diagonal"                    # legacy name in the file
    host = BlockDefinition.new(name="Slab", library="Mine", series="S",
                               origin=(0.0, 0.0), primitives=[rec])
    src.register_block_definition(host)
    src.place_block_instance(host.id, (0.0, 0.0))
    path = str(tmp_path / "old.fpd")
    src.save_to_file(path)
    payload = json.load(open(path, encoding="utf-8"))
    assert set(payload["block_definitions"]) == {host.id}  # no pattern embedded
    assert payload["block_definitions"][host.id]["primitives"][0]["fill"]["pattern"] \
        == "diagonal"

    win = mw
    win._load_project(path)
    sc = win.scene
    img = _render(sc, QRectF(-700, -700, 1400, 1400), 700, 700)
    inside = sum(_red(img, x, y) for x in range(150, 550, 2) for y in range(150, 550, 2))
    assert inside > 20                                     # hatch lines, not tone
    assert hp.BUILTIN_DIAGONAL in sc._block_definitions
    _assert_unloadable_by_undo(sc)


# ── wiring: DM category change, sheets, folder setting change ───────────────

def _picked(dm, ref):
    class _Picked:                       # the user picks *ref* and presses OK
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return dm.QDialog.DialogCode.Accepted

        def get_result(self):
            return "#666666", ref, 1.0
    return _Picked


def test_dm_category_pattern_loads_on_ok_into_the_baseline(qapp, monkeypatch):
    from firepro3d import display_manager as dm
    hp.seed_hatch_folder()
    sc = Model_Space()
    dlg = dm.DisplayManager(sc)
    monkeypatch.setattr(dm, "SectionPatternDialog", _picked(dm, hp.BUILTIN_BRICK))
    try:
        dlg._pick_section("Wall", is_category=True)
        assert hp.BUILTIN_BRICK not in sc._block_definitions    # not before OK
        dlg.accept()
        assert QSettings("GV", "FirePro3D").value(
            "display/Wall/section_pattern") == hp.BUILTIN_BRICK
        assert hp.resolve_tile(hp.BUILTIN_BRICK, sc.block_registry) is not None
        assert not sc.can_undo()
        assert hp.BUILTIN_BRICK in sc._undo_stack[0]["block_definitions"]
    finally:
        dlg.close()


def test_dm_category_pattern_cancel_loads_nothing(qapp, monkeypatch):
    from firepro3d import display_manager as dm
    hp.seed_hatch_folder()
    sc = Model_Space()
    dlg = dm.DisplayManager(sc)
    monkeypatch.setattr(dm, "SectionPatternDialog", _picked(dm, hp.BUILTIN_BRICK))
    try:
        dlg._pick_section("Wall", is_category=True)
        dlg.reject()
        assert hp.BUILTIN_BRICK not in sc._block_definitions
    finally:
        dlg.close()


def test_sheet_2d_fill_resolves_through_the_project(qapp, shipped_hatches):
    from firepro3d.level_manager import LevelManager, PlanViewManager
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from tests._paper_iso_helpers import _DetailMgrStub
    ms = Model_Space()
    shipped_hatches(ms)
    lm, pvm = LevelManager(), PlanViewManager()
    paper = PaperScene(Sheet.create_default(),
                       ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm))
    r = RectangleItem(QPointF(0, 0), QPointF(60, 60))      # printed mm on a sheet
    r.fill_type, r.fill_pattern = "hatch", "horizontal"
    r._display_fill_color, r.fill_opacity = "#ff0000", 1.0
    paper.addItem(r)
    img = QImage(300, 300, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    paper.render(p, QRectF(0, 0, 300, 300), QRectF(0, 0, 60, 60))   # 5 px / mm
    p.end()
    ys, prev = [], False
    for y in range(5, 295):                                # down the middle column
        cur = _red(img, 150, y)
        if cur and not prev:
            ys.append(y)
        prev = cur
    gaps = sorted(b - a for a, b in zip(ys, ys[1:]))
    assert len(ys) >= 10 and gaps[len(gaps) // 2] == 15    # 3 mm printed rows
    assert paper.block_registry is ms.block_registry


def test_settings_change_seeds_a_new_hatch_folder(qapp, make_model_space, tmp_path):
    from firepro3d.settings.system_settings_dialog import SystemSettingsDialog
    scene = make_model_space()
    dlg = SystemSettingsDialog(scene=scene, view=getattr(scene, "_view_for_test", None),
                               snap_toolbar=None)
    try:
        target = tmp_path / "Team hatches"
        dlg._panes["general"]._hatch_dir_edit.setText(str(target))
        dlg._apply_all()
        assert app_data.hatch_patterns_dir() == str(target)
        assert _ids_in(str(target)) == {v[0] for v in _EXPECTED.values()}
    finally:
        dlg.deleteLater()


def _seeded(folder):
    return os.path.normcase(os.path.abspath(str(folder))) in hp._seeded_folders()


def test_seed_never_rewrites_an_unreadable_index(qapp, tmp_path):
    folder = tmp_path / "Hatches"
    folder.mkdir()
    corrupt = b'{"Mine.fpdb": {"id": "x", "name": "Mine"'      # truncated JSON
    (folder / "index.json").write_bytes(corrupt)
    copied = hp.seed_hatch_folder(str(folder))
    assert (folder / "index.json").read_bytes() == corrupt      # user entries kept
    assert len(copied) == 5 and _ids_in(str(folder)) == {v[0] for v in _EXPECTED.values()}
    assert not _seeded(folder)                                  # retried next time


def test_seed_marks_the_folder_only_when_complete(qapp, tmp_path, monkeypatch):
    folder = tmp_path / "Hatches"
    real_copy = hp.shutil.copyfile

    def flaky(src, dst):
        if os.path.basename(src) == "Brick.fpdb":
            raise OSError("locked by antivirus")
        return real_copy(src, dst)

    monkeypatch.setattr(hp.shutil, "copyfile", flaky)
    assert hp.BUILTIN_BRICK not in hp.seed_hatch_folder(str(folder))
    assert not _seeded(folder)
    monkeypatch.setattr(hp.shutil, "copyfile", real_copy)
    assert hp.seed_hatch_folder(str(folder)) == [hp.BUILTIN_BRICK]   # retried
    assert _seeded(folder)


def test_shipped_files_are_read_once_per_process(qapp, monkeypatch):
    first = hp.shipped_pattern_files()
    reads = []
    real = hp._read_json
    monkeypatch.setattr(hp, "_read_json", lambda p: reads.append(p) or real(p))
    assert hp.shipped_pattern_files() == first and len(first) == 5
    assert reads == []
