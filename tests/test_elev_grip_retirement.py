"""U5 Leg B — Task 6: regression lockdown for the elevation grip retirement.

Locks the invariants Leg B must preserve:

* The legacy ``ElevationScene._find_grip_hit`` grip-hit method is RETIRED (the
  shared ``SelectionManipulator`` is the sole grip owner).
* ``ElevationView`` carries no ``paintEvent`` grip-loop override (resolves to
  ``QGraphicsView``'s).
* A gridline endpoint grip driven through the MANIPULATOR lifecycle commits the
  SAME ``_gridline_z_overrides`` entry as the legacy ``apply_grip`` + commit path
  (byte-parity), and the ``commit_hook`` fires.

Drives the manipulator's handle ``on_press``/``on_drag``/``on_release``
lifecycle directly (mirrors ``_drive_grip`` in
``tests/test_manip_griphandle_gridline_parity.py``) — robust offscreen where a
posted grip-drag is fiddly. Asserts OBSERVABLE ground truth (the override dict),
not internals. Uses the ``elevation_scene_for`` fixture (real Model_Space) from
conftest.py.

Note: the datum §3.1 no-lateral-move twin already lives in
``tests/test_elev_manip_handles_parity.py::test_datum_interior_move_keeps_V_pinned``
and is not duplicated here.
"""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d.elevation_scene import ElevGridlineItem


def _add_gridline(scene, label="A", h=100.0, v_top=-50.0, v_bot=50.0):
    g = ElevGridlineItem(h, v_top, v_bot, label, 20.0,
                         QColor("#888"), QColor("#fff"), 1.0)
    scene.addItem(g)
    return g


def _drive_grip(scene, g, index, start, path,
                mods=Qt.KeyboardModifier.NoModifier):
    """Select *g*, install its handle *index* on the scene's live manipulator,
    and drive press -> moves through the manipulator (the lifecycle the view
    posts). Returns the manipulator so callers can finish or cancel.

    Mirrors ``_drive_grip`` in test_manip_griphandle_gridline_parity.py.
    """
    g.setSelected(True)
    QApplication.processEvents()
    m = scene._live_manip()
    h = g.manip_handles()[index]
    m._begin_handle(h, QPointF(*start), QPointF(*start))
    for pt in path:
        m._update(QPointF(*pt), mods, QPointF(*pt))
    return m


# ── Retirement guards ────────────────────────────────────────────────────────

def test_find_grip_hit_retired(qapp):
    from firepro3d import elevation_scene as es
    assert not hasattr(es.ElevationScene, "_find_grip_hit")


def test_elevation_view_has_no_paintevent_grip_loop(qapp):
    from firepro3d.elevation_view import ElevationView
    # paintEvent override removed -> resolves to QGraphicsView's.
    assert "paintEvent" not in ElevationView.__dict__


# ── Grip byte-parity (manipulator-driven) ────────────────────────────────────

def test_gridline_grip_byte_parity_via_manipulator(qapp, elevation_scene_for):
    """Dragging the bottom endpoint (index 1) via the manipulator grip lifecycle
    to y=80 commits the SAME override entry as the legacy apply_grip + commit
    path, and the commit_hook fires ("grip")."""
    _ms, elev = elevation_scene_for("north")
    g = _add_gridline(elev, label="A", h=100.0, v_top=-50.0, v_bot=50.0)

    # Record commit_hook firings (parity: one "grip" commit per gesture).
    fired = []
    m = elev._live_manip()
    real_hook = m._commit_hook

    def _spy(mode):
        fired.append(mode)
        if real_hook is not None:
            real_hook(mode)

    m._commit_hook = _spy

    # Bottom endpoint starts at scene (100, 50); drag it to (100, 80).
    m = _drive_grip(elev, g, index=1, start=(100.0, 50.0),
                    path=[(100.0, 65.0), (100.0, 80.0)])
    m._finish(QPointF(100.0, 80.0), Qt.KeyboardModifier.NoModifier)

    # OBSERVABLE ground truth: the persisted override dict.
    ov = elev._gridline_z_overrides["A"]
    assert ov == {"v_top": -50.0, "v_bot": 80.0}
    # commit_hook fired exactly once, in grip mode.
    assert fired == ["grip"]
