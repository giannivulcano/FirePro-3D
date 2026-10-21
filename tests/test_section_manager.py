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
