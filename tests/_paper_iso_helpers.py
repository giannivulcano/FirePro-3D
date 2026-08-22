"""Shared builders for per-viewport isolation / clip tests. REAL domain items only."""
from PyQt6.QtCore import QPointF, QRectF
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment
from firepro3d.gridline import GridlineItem
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.paper_space import ViewResolver


def make_wall(scene, p1, p2, level):
    """Create a real WallSegment on *level*, registered so apply_to_scene governs it."""
    w = WallSegment(QPointF(*p1), QPointF(*p2))
    w.level = level
    scene._walls.append(w)
    scene.addItem(w)
    return w


def make_gridline(scene, p1, p2, label, level="Level 1"):
    gl = GridlineItem(QPointF(*p1), QPointF(*p2), label=label)
    if hasattr(gl, "level"):
        gl.level = level
    scene._gridlines.append(gl)
    scene.addItem(gl)
    return gl


class _DetailMgrStub:
    def __init__(self, markers=None): self._m = markers or {}
    def get_marker(self, name): return self._m.get(name)
    @property
    def detail_names(self): return list(self._m)


def build_isolation_fixture():
    """Model_Space + LevelManager with a wall ONLY on Level 1 and ONLY on Level 3,
    plus a real plan-view manager with cut-plane contexts. Returns a dict."""
    ms = Model_Space()
    lm = LevelManager()                       # DEFAULT_LEVELS: Level 1/2/3
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    pvm.create("Level 3", lm)
    # Walls at the SAME xy so their pixels land in the same place — only the level differs.
    w1 = make_wall(ms, (0, 0), (4000, 0), "Level 1")
    w3 = make_wall(ms, (0, 0), (4000, 0), "Level 3")
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)
    return dict(scene=ms, lm=lm, pvm=pvm, resolver=resolver, w1=w1, w3=w3)
