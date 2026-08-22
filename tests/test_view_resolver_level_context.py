from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.paper_space import ViewResolver


class _DetailMgr:
    def __init__(self, markers): self._m = markers
    def get_marker(self, name): return self._m.get(name)
    @property
    def detail_names(self): return list(self._m)


class _Marker:
    def __init__(self, level_name, vh=None, vd=None):
        self.level_name = level_name
        self.view_height = vh
        self.view_depth = vd


def test_plan_context_returns_plan_view_cut_plane():
    lm = LevelManager()
    pvm = PlanViewManager()
    pv = pvm.create("Level 1", lm)
    r = ViewResolver(object(), pvm, _DetailMgr({}), None, level_manager=lm)
    ctx = r.resolve_level_context("plan", "Plan: Level 1")
    assert ctx == ("Level 1", pv.view_height, pv.view_depth)


def test_detail_context_uses_marker_level_and_explicit_cut_plane():
    lm = LevelManager()
    pvm = PlanViewManager()
    m = _Marker("Level 2", vh=5000.0, vd=3000.0)
    r = ViewResolver(object(), pvm, _DetailMgr({"D1": m}), None, level_manager=lm)
    assert r.resolve_level_context("detail", "D1") == ("Level 2", 5000.0, 3000.0)


def test_detail_context_inherits_plan_cut_plane_when_marker_unset():
    lm = LevelManager()
    pvm = PlanViewManager()
    pv = pvm.create("Level 2", lm)
    m = _Marker("Level 2", vh=None, vd=None)
    r = ViewResolver(object(), pvm, _DetailMgr({"D1": m}), None, level_manager=lm)
    assert r.resolve_level_context("detail", "D1") == ("Level 2", pv.view_height, pv.view_depth)


def test_elevation_and_missing_return_none():
    lm = LevelManager()
    r = ViewResolver(object(), PlanViewManager(), _DetailMgr({}), None, level_manager=lm)
    assert r.resolve_level_context("elevation", "North") is None
    assert r.resolve_level_context("plan", "Plan: Nope") is None


def test_no_level_manager_returns_none():
    r = ViewResolver(object(), PlanViewManager(), _DetailMgr({}), None)   # no level_manager
    assert r.resolve_level_context("plan", "Plan: Level 1") is None
