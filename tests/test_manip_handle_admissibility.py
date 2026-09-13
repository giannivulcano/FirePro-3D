"""U2: the Handle lifecycle admits a live-apply (U3-style) drag,
manip_handles() consumption is live, and legacy grip seams are untouched.

Three goals (no production code modified):
  1. The manipulator's gesture lifecycle ADMITS a live-apply drag — a handle
     that edits on every on_drag() call and never uses the held-preview _apply.
  2. An item exposing manip_handles() -> [Handle] makes _active_handles() return
     that handle and a pooled _HandleItem host renders+hit-tests it.
  3. The legacy grip seams (_is_box_native_single, _find_grip_hit) still behave
     identically for a box-native RectangleItem.
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QCursor, QPainter, QPainterPath, QPen, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem

from firepro3d.manip_handle import Handle
from firepro3d.manip_math import HandleRole


# ---------------------------------------------------------------------------
# Minimal scene_and_view fixture (replicated locally to keep the 6 parity
# files byte-unmodified; the session-scoped qapp comes from conftest.py).
# ---------------------------------------------------------------------------

@pytest.fixture
def scene_and_view(qapp):
    """A shown Model_View over a Model_Space, pinned to identity zoom.

    Mirrors the fixture in test_selection_manipulator.py exactly so all test
    coordinates map correctly at m11==1.
    """
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.model_view import Model_View

    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    view = Model_View(scene)
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.centerOn(150, 50)
    view.setFocus()
    qapp.processEvents()
    yield scene, view
    view.close()


# ---------------------------------------------------------------------------
# Live-apply handle stub
# ---------------------------------------------------------------------------

class _FakeLiveHandle(Handle):
    """A live-apply handle: calls a scene edit on every drag, never uses
    the held-preview _apply.  Modelling the U3 parametric pattern."""

    role = HandleRole.TOP_LEFT
    gesture_mode = "resize"    # routes through the resize branch in _begin
    hud_schema = None

    def __init__(self):
        self.edits = 0
        self.commits = 0

    def scene_position(self, rect: QRectF) -> QPointF:
        return rect.topLeft()

    def shape(self, *, size: float, grab_pad: float) -> QPainterPath:
        half = size / 2.0 + grab_pad
        p = QPainterPath()
        p.addRect(QRectF(-half, -half, 2 * half, 2 * half))
        return p

    def paint(self, painter: QPainter, *, size, border, fill, hover,
              border_width) -> None:
        pass  # headless-safe no-op

    def cursor(self, m) -> QCursor:
        return QCursor(Qt.CursorShape.ArrowCursor)

    def visible(self, m) -> bool:
        return True

    # -- lifecycle --

    def on_press(self, m) -> None:
        pass

    def on_drag(self, m, scene_pos: QPointF, mods) -> None:
        # LIVE edit each move — deliberately does NOT call m._apply so the
        # items keep their pre-drag transforms throughout the gesture.
        self.edits += 1

    def on_release(self, m, scene_pos: QPointF, mods) -> None:
        self.commits += 1
        m._end_drag()     # clears _mode so is_dragging() returns False

    def on_cancel(self, m) -> None:
        pass

    def commit_typed(self, m, values: dict) -> None:
        pass


# ---------------------------------------------------------------------------
# Test 1: lifecycle admits a live-apply drag
# ---------------------------------------------------------------------------

def test_lifecycle_admits_live_apply(qapp, scene_and_view):
    """_begin/_update/_finish route correctly to a live-apply handle.

    Wiring: call _begin("resize", ..., HandleRole.TOP_LEFT) to enter the resize
    branch (which arm _active_handle = self._rigid[TOP_LEFT]).  Then OVERWRITE
    manip._active_handle = fake BEFORE the first _update.  This is honest
    because _update checks ``if self._active_handle is not None`` and calls
    ``self._active_handle.on_drag(...)`` — our fake is that object.  The key
    observable is that, after 3 drag updates, the items' transforms are
    IDENTICAL to what they were right before the gesture (no held transform was
    applied, proving live-apply not held-preview), and edits==3 / commits==1.
    """
    from firepro3d.selection_manipulator import SelectionManipulator
    from firepro3d.construction_geometry import RectangleItem

    scene, view = scene_and_view

    # A selectable rect with manip_scale (box-native) so rebake keeps it.
    r = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(r)
    r.setSelected(True)
    qapp.processEvents()

    manip = next(i for i in scene.items() if isinstance(i, SelectionManipulator))

    # Press point and screen point (screen_pos drives the drag-threshold check).
    press_scene = QPointF(200, 150)   # bottom-right corner
    press_screen = QPointF(200, 150)  # identity zoom => scene ≈ screen

    # Begin the resize gesture for TOP_LEFT role (rigid handle installed).
    manip._begin("resize", press_scene, press_screen, HandleRole.TOP_LEFT)
    assert manip.is_dragging()
    assert manip._active_handle is manip._rigid[HandleRole.TOP_LEFT]

    # Inject the live-apply fake — this is the canonical injection point.
    # _update routes to self._active_handle.on_drag(...) so the fake receives
    # every call.  _finish routes to self._active_handle.on_release(...).
    fake = _FakeLiveHandle()
    manip._active_handle = fake

    # Capture pre-drag item transforms (should stay the same through all updates
    # since fake.on_drag never calls _apply).
    pre_transforms = {id(it): QTransform(it.transform()) for it in manip._items}

    # Drive 3 drag updates.  screen_pos must be > startDragDistance() (4 px)
    # from press_screen to cross the threshold and arm _moved=True.
    drag_points = [
        QPointF(press_scene.x() + 20, press_scene.y()),
        QPointF(press_scene.x() + 35, press_scene.y()),
        QPointF(press_scene.x() + 50, press_scene.y()),
    ]
    # screen_pos for each: sufficiently far from press_screen to pass threshold.
    drag_screens = [
        QPointF(press_screen.x() + 20, press_screen.y()),
        QPointF(press_screen.x() + 35, press_screen.y()),
        QPointF(press_screen.x() + 50, press_screen.y()),
    ]
    for sp, scr in zip(drag_points, drag_screens):
        manip._update(sp, Qt.KeyboardModifier.NoModifier, scr)

    # Prove live-apply: items retain their pre-drag transforms (no _apply called).
    for it in manip._items:
        t_now = it.transform()
        t_pre = pre_transforms[id(it)]
        assert t_now == t_pre, (
            f"Item transform changed during live-apply drag: {t_now} != {t_pre}"
        )

    # 3 updates all crossed the threshold after the first one armed _moved=True.
    assert fake.edits == 3, f"Expected 3 on_drag calls, got {fake.edits}"

    # Finish the gesture — routes to fake.on_release.
    manip._finish(drag_points[-1], Qt.KeyboardModifier.NoModifier)
    assert fake.commits == 1, f"Expected 1 on_release call, got {fake.commits}"
    assert not manip.is_dragging()


# ---------------------------------------------------------------------------
# Test 2: item-provided manip_handles() sourced and hosted
# ---------------------------------------------------------------------------

def test_manip_handles_sourced_and_hosted(qapp, scene_and_view):
    """An item implementing manip_handles() makes _active_handles() return its
    handle and _sync_host_pool() builds a visible _HandleItem host for it.

    The stub item only implements manip_translate (to pass the rebake translate
    gate) and manip_handles.  It does NOT implement manip_scale, so the rigid
    resize handles stay hidden.
    """
    from firepro3d.selection_manipulator import SelectionManipulator, _HandleItem

    scene, view = scene_and_view

    stub_handle = _FakeLiveHandle()

    class _StubItem(QGraphicsRectItem):
        """Minimal item: translatable + exposes one custom handle."""

        def __init__(self):
            super().__init__(QRectF(50, 50, 80, 60))
            self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
            self._h = stub_handle

        def manip_translate(self, dx: float, dy: float) -> None:
            self.moveBy(dx, dy)

        def manip_handles(self):
            return [self._h]

    stub = _StubItem()
    scene.addItem(stub)
    stub.setSelected(True)
    qapp.processEvents()

    manip = next(i for i in scene.items() if isinstance(i, SelectionManipulator))
    manip.rebake()
    qapp.processEvents()

    # _active_handles() must return [stub._h] (item-provided), NOT the rigid list.
    active = manip._active_handles()
    assert active == [stub._h], (
        f"_active_handles() returned {active!r}, expected [stub._h]"
    )

    # The host pool must have at least one entry wired to stub._h.
    assert len(manip._host_pool) >= 1, "Host pool is empty after rebake with manip_handles()"
    hosted_handle = manip._host_pool[0].handle
    assert hosted_handle is stub._h, (
        f"_host_pool[0].handle is {hosted_handle!r}, expected stub._h"
    )

    # The pooled host must be visible (handle.visible() returns True, manip is shown).
    assert manip._host_pool[0].isVisible(), (
        "_host_pool[0] is not visible — handle should be shown for this stub"
    )


# ---------------------------------------------------------------------------
# Test 3: legacy grip seams untouched for box-native RectangleItem
# ---------------------------------------------------------------------------

def test_legacy_grip_seams_untouched(qapp, scene_and_view):
    """The legacy grip pipeline is correctly retired for a box-native item.

    When a single RectangleItem (which has manip_scale) is selected:
      - _is_box_native_single(r) is True (manipulator owns the handles)
      - _find_grip_hit at a corner grip returns None (grips suppressed so they
        cannot steal a manipulator-handle press)
    """
    from firepro3d.construction_geometry import RectangleItem
    from firepro3d.selection_manipulator import SelectionManipulator

    scene, view = scene_and_view

    r = RectangleItem(QPointF(100, 100), QPointF(200, 150))
    scene.addItem(r)
    r.setSelected(True)
    qapp.processEvents()

    manip = next(i for i in scene.items() if isinstance(i, SelectionManipulator))
    manip.rebake()
    qapp.processEvents()

    # The manipulator must claim ownership of r's handles.
    assert manip._is_box_native_single(r), (
        "_is_box_native_single(r) returned False — manipulator should own "
        "a single box-native (manip_scale) RectangleItem's handles"
    )

    # _find_grip_hit at the top-left corner (grip index 0 = (100, 100)) must
    # return None because the item is manipulator-owned.
    tl = QPointF(100.0, 100.0)   # TL corner == grip_points()[0] at angle=0
    hit = scene._tools._find_grip_hit(tl)
    assert hit is None, (
        f"_find_grip_hit returned {hit!r} at a corner of a manipulator-owned "
        "RectangleItem — grips should be suppressed to prevent handle theft"
    )
