"""SectionManager + consumers: seeding, placing, opening, identity (S4), 560
public accessors, D8 label, D5 ribbon button, browser Sections group."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtWidgets import QTabWidget

from firepro3d.section_marker import SectionMarker, CARDINALS


@pytest.fixture
def mgr(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    ms = Model_Space()
    lm = LevelManager(); ms._level_manager = lm
    sm = ScaleManager(); ms.scale_manager = sm
    tabs = QTabWidget()
    m = SectionManager(ms, lm, sm, tabs)
    ms._section_manager = m
    yield m, ms, tabs
    m.close_all()


def test_seed_cardinals_creates_four_once_and_adds_to_scene(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    assert set(m.markers) == set(CARDINALS)
    assert all(m.markers[c].scene() is ms and m.markers[c].cardinal == c for c in CARDINALS)
    m.seed_cardinals()
    assert len(m.markers) == 4                                   # idempotent


def test_place_section_names_and_depth_seed(mgr):
    m, ms, tabs = mgr
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0.0, -6000.0), QPointF(4000.0, -6000.0))   # building 6 m scene-up of the cut
    ms._walls.append(w); ms.addItem(w)
    s1 = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    s2 = m.place_section(QPointF(0.0, 1000.0), QPointF(5000.0, 1000.0))
    assert (s1.name, s2.name) == ("Section 1", "Section 2")
    assert s1.look_sign == 1 and s1.scene() is ms and not s1.auto_extent
    # depth = max((c - A) . N) over the building bbox corners (N_s = (0, -1) here) = the
    # wall's own scene bounding rect reaching scene-up from the cut (no CROP_MARGIN padding).
    assert s1.depth == pytest.approx(-w.sceneBoundingRect().top(), abs=1.0)
    assert s1.depth > 6000.0
    s3 = m.place_section(QPointF(0.0, -20000.0), QPointF(5000.0, -20000.0))  # look side (scene-up) is empty
    assert s3.name == "Section 3" and s3.depth == 10000.0                 # -> 10 000 mm fallback (s9)


def test_open_section_tab_titles_and_identity(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    v = m.open_section("north")
    assert tabs.tabText(tabs.currentIndex()) == "Elevation: North"
    assert m.get_scene("north").marker is m.markers["north"]
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    m.open_section(s.name)
    assert tabs.tabText(tabs.currentIndex()) == "Section: Section 1"
    assert m.open_names == ["north", "Section 1"]
    assert m.open_section("north") is v and tabs.count() == 2         # re-open switches


def test_cardinal_identity_is_elevation(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    assert m.markers["north"].view_type == "elevation" and m.markers["north"].view_name == "north"
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    assert s.view_type == "section" and s.view_name == "Section 1"


def test_open_scenes_public_and_live_scenes_uses_it(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals(); m.open_section("north")
    assert [sc.marker.name for sc in m.open_scenes] == ["North"]
    import inspect, main as _main
    src = inspect.getsource(_main.MainWindow._live_scenes)
    assert "open_scenes" in src and "._views" not in src              # 560: no private read
    assert "._scenes" not in src                                      # nor the schematic manager's


def test_schematic_manager_scenes_property_is_public_read_only(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.schematic_scene import SchematicSceneManager
    mgr = SchematicSceneManager(Model_Space())
    sentinel = object()
    mgr._scenes["bid"] = sentinel
    assert mgr.scenes == [sentinel]
    mgr.scenes.clear()                                                # a copy: the store is untouched
    assert mgr._scenes == {"bid": sentinel}
    with pytest.raises(AttributeError):
        mgr.scenes = []


def test_get_or_build_scene_without_tab(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    sc = m.get_or_build_scene("south")
    assert sc is not None and tabs.count() == 0 and m.get_scene("south") is None
    assert m.get_or_build_scene("south") is sc                          # cached
    m.open_section("south")
    assert m.get_scene("south") is sc                                   # the tab adopts the built scene


def test_delete_rename_cascade(mgr):
    m, ms, tabs = mgr
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0)); m.open_section("Section 1")
    changed = []
    m.sectionsChanged.connect(lambda: changed.append(1))
    m.rename_section("Section 1", "Stair")
    assert "Stair" in m.markers and "Section 1" not in m.markers
    assert tabs.tabText(0) == "Section: Stair" and m.open_names == ["Stair"]
    m.delete_section("Stair")
    assert tabs.count() == 0 and m.markers == {} and s.scene() is None
    assert len(changed) == 2
    m.seed_cardinals()
    with pytest.raises(ValueError):
        m.delete_section("north")                                       # cardinals permanent (D5b)


def test_marker_grip_rebuilds_open_scene(mgr):
    m, ms, tabs = mgr
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0)); m.open_section("Section 1")
    sc = m.get_scene("Section 1")
    sc._rebuild_timer.stop()
    s.apply_grip(2, QPointF(2500.0, -4000.0))
    assert sc._rebuild_timer.isActive()                                 # scheduled by on_marker_geometry_changed


def test_dm_row_label_section_marker_key_unchanged():
    from firepro3d.display_manager import _CATEGORY_MAP, category_label
    assert "Elevation Marker" in _CATEGORY_MAP and "Section Marker" not in _CATEGORY_MAP
    assert category_label("Elevation Marker") == "Section Marker"
    assert category_label("Wall") == "Wall"


def test_dm_and_paper_display_categorise_section_marker(qapp):
    from firepro3d.display_manager import _is_elevation_marker
    from firepro3d.paper_display import _category_for_item
    m = SectionMarker("Section 1", QPointF(0, 0), QPointF(100, 0))
    assert _is_elevation_marker(m) and _category_for_item(m) == "Elevation Marker"


def test_ribbon_section_button_enters_section_mode(qapp):
    from firepro3d.view_3d import View3D  # noqa: F401 -- heavy import before MainWindow (HF1 pattern)
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    from tests._mainwindow_helpers import dispose_main_window
    win = MainWindow()
    try:
        btn = win._mode_buttons["section"]
        assert btn.text() == "Section"
        btn.click()
        assert win.scene.mode == "section"
        assert win.section_manager is win.scene._section_manager
        assert set(win.section_manager.markers) == set(CARDINALS)       # seeded at startup
        assert "Sections" in [win.project_browser._sections_root.text(0)]
    finally:
        dispose_main_window(win)


def test_empty_project_depth_is_fallback(mgr):
    m, ms, tabs = mgr
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))     # nothing in the project
    assert s.depth == 10000.0


def test_next_name_skips_taken_names(mgr):
    m, ms, tabs = mgr
    m.from_list([SectionMarker("Section 2", QPointF(0, 0), QPointF(5000, 0)).to_dict()])
    assert m.place_section(QPointF(0, 0), QPointF(5000, 0)).name == "Section 3"


def test_from_list_skips_unbuildable_records_and_cardinal_reseeds(mgr):
    """Hand-edited file (spec s13): a zero-length cut, a zero depth, a missing key
    and a duplicate name never reach a SectionScene; a bad cardinal is re-seeded."""
    m, ms, tabs = mgr
    good = SectionMarker("Section 1", QPointF(0, 0), QPointF(5000, 0)).to_dict()
    short = dict(good, name="Section 2", cut_b=[10.0, 0.0])
    flat = dict(good, name="Section 3", depth=0.0)
    broken = {"name": "Section 4"}
    dup = dict(good)
    bad_north = SectionMarker.for_cardinal("north", QRectF(0, 0, 100, 100)).to_dict()
    bad_north["depth"] = -5.0
    m.from_list([good, short, flat, broken, dup, bad_north])
    assert set(m.markers) == {"Section 1"}
    m.seed_cardinals()
    assert set(m.markers) == {"Section 1"} | set(CARDINALS)
    m.get_or_build_scene("north")                                   # builds without raising
    m.get_or_build_scene("Section 1")


def test_restore_from_list_updates_survivor_in_place(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    s = m.place_section(QPointF(0, 0), QPointF(5000, 0))
    snap = m.to_list()
    s.set_geometry(QPointF(0, 0), QPointF(5000, 3000), 1234.0)
    s.flip()
    gone = m.place_section(QPointF(0, 500), QPointF(5000, 500))
    m.restore_from_list(snap)
    assert m.markers["Section 1"] is s and s.cut_b == QPointF(5000, 0) and s.look_sign == 1
    assert "Section 2" not in m.markers and gone.scene() is None


def _main_window():
    from firepro3d.view_3d import View3D  # noqa: F401 -- heavy import before MainWindow (HF1 pattern)
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    return MainWindow()


def test_views_wired_once_on_every_open_path(qapp):
    """F1: close + reopen a cardinal tab must not double-connect entitySelected, and a
    section opened by the placement tool's path (place_section + open_section) gets
    the footer cursor feed and the property-panel routing."""
    from tests._mainwindow_helpers import dispose_main_window
    win = _main_window()
    try:
        props, coords = [], []
        win.prop_manager.show_properties = lambda *a: props.append(a)   # looked up at connect time
        win.footer.set_coord = lambda text: coords.append(text)
        sm = win.section_manager
        win._activate_elevation("north")
        idx = next(i for i in range(win.central_tabs.count())
                   if win.central_tabs.tabText(i) == "Elevation: North")
        win._on_tab_close_requested(idx)                                 # user closes the tab
        assert "north" not in sm.open_names
        win._activate_elevation("north")                                 # ... and reopens it
        scene = sm.get_scene("north")
        props.clear()                                                    # opening may emit None selections
        scene.entitySelected.emit("probe")
        assert props == [("probe",)]                                     # once, not twice
        # Placement path: the manager is driven directly, main's _activate_* never runs.
        marker = sm.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        sm.open_section(marker.view_name)
        sec_scene, sec_view = sm.get_scene("Section 1"), sm.get_view("Section 1")
        props.clear(); coords.clear()
        sec_scene.entitySelected.emit("sec")
        sec_view.cursorMoved.emit("H: 1  Z: 2")
        assert props == [("sec",)]
        assert coords == ["H: 1  Z: 2"]
    finally:
        dispose_main_window(win)


def test_rename_refuses_cardinal_names(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    for bad in ("North", "north", "EAST"):
        m.rename_section("Section 1", bad)
        assert s.name == "Section 1" and "Section 1" in m.markers


def test_from_list_skips_placed_record_named_like_a_cardinal(mgr):
    m, ms, tabs = mgr
    rec = SectionMarker("North", QPointF(0, 0), QPointF(5000, 0)).to_dict()   # cardinal null
    m.from_list([rec])
    assert m.markers == {}


def test_undo_restore_pairs_a_rename_and_keeps_tab_marker_and_sheet_binding(mgr):
    """F3: undo across a rename is a rename back, not delete + re-add."""
    m, ms, tabs = mgr
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    view = m.open_section("Section 1")
    class _VP:
        source_view_type, source_view_name = "section", "Section 1"
    class _Sheet:
        sheet_views = [_VP]
    vp = _VP
    ms._sheets = [_Sheet]
    before = m.to_list()
    m.rename_section("Section 1", "Stair")
    after = m.to_list()
    assert vp.source_view_name == "Stair"
    m.restore_from_list(before)
    assert m.markers["Section 1"] is s and "Stair" not in m.markers
    assert m.get_view("Section 1") is view and tabs.count() == 1
    assert tabs.tabText(0) == "Section: Section 1" and vp.source_view_name == "Section 1"
    m.restore_from_list(after)                                       # redo
    assert m.markers["Stair"] is s and m.get_view("Stair") is view
    assert tabs.tabText(0) == "Section: Stair" and vp.source_view_name == "Stair"


def test_restore_recomputes_the_name_counter(mgr):
    m, ms, tabs = mgr
    snap = m.to_list()
    m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    m.restore_from_list(snap)
    assert m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0)).name == "Section 1"
