"""C2 — underlay is reachable ONLY as the terminal HALO candidate.

An underlay group must:
  * appear in ``halo_candidates_at`` LAST (after all real geometry), never
    ahead of a real click target;
  * be excluded entirely when locked (ItemIsSelectable cleared);
  * be classified as an underlay even when ``scene.items()`` hands back a
    child path item of the group (parent-walk), not just the tracked group.

Real underlay registration: we build the same batched path-item group the
production ``_build_batched_underlay_group`` builds, set the selectable/movable
flags that real placement sets, run the real ``_apply_underlay_display`` (which
clears those flags when ``record.locked``), then append ``(record, group)`` to
the controller's tracking list exactly as ``import_dxf``/``place_import`` do at
the end of placement. No monkeypatch — this is the genuine registration path.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsItem

from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay

# Reuse the production-mirroring group builder from the integration suite.
from tests.test_underlay_integration import _build_underlay_group


def _place_underlay(sc, at=(0.0, 0.0), locked=False):
    """Build + register a real underlay group at ``at``.

    Mirrors the tail of import_dxf/place_import: build the batched group,
    set the placement flags, apply display (clears the flags if locked),
    then track ``(record, group)`` on the controller.
    """
    x, y = at
    group = _build_underlay_group(sc, layers=["0"], x=x, y=y)
    # Real placement sets these before _apply_underlay_display.
    group.setFlags(
        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    )
    record = Underlay(type="dxf", path="floor.dxf", x=x, y=y, locked=locked)
    # _apply_underlay_display clears ItemIsSelectable/Movable when locked.
    sc._apply_underlay_display(group, record)
    sc._underlay_ctl.items.append((record, group))
    return group


def test_underlay_is_last_candidate(qapp):
    sc = Model_Space()
    n = sc.add_node(0.0, 0.0)
    u = _place_underlay(sc, at=(0.0, 0.0))
    cands = sc.halo_candidates_at(QPointF(0.0, 0.0), 8.0, QTransform())
    assert u in cands
    assert cands[-1] is u          # terminal
    assert cands[0] is n           # real geometry ranks first


def test_locked_underlay_excluded(qapp):
    sc = Model_Space()
    u = _place_underlay(sc, at=(0.0, 0.0), locked=True)
    cands = sc.halo_candidates_at(QPointF(0.0, 0.0), 8.0, QTransform())
    assert u not in cands


def test_underlay_child_classified_as_underlay(qapp):
    """A child path item of the group must be classified as an underlay
    (parent-walk), so it is never misrouted into the ranked geometry bucket.
    """
    sc = Model_Space()
    u = _place_underlay(sc, at=(0.0, 0.0))
    children = [c for c in u.childItems()]
    assert children, "expected the group to have child path items"
    for child in children:
        assert sc._halo_is_underlay(child) is True


def test_selecting_underlay_emits_readonly_properties(qapp):
    """Selecting the underlay group emits its record for the property panel;
    every property is a read-only ``label`` (no editable fields).
    """
    sc = Model_Space()
    u = _place_underlay(sc, at=(0.0, 0.0))
    captured = []
    sc.requestPropertyUpdate.connect(captured.append)
    u.setSelected(True)
    assert captured, "selecting an underlay should emit a property update"
    record = captured[-1]
    props = record.get_properties()
    assert props, "underlay record should expose properties"
    assert all(meta.get("type") == "label" for meta in props.values())


def test_underlay_group_has_no_grips(qapp):
    """An underlay group provides no manipulator handles → no grips shown."""
    sc = Model_Space()
    u = _place_underlay(sc, at=(0.0, 0.0))
    assert not hasattr(u, "manip_handles")
    assert not hasattr(u, "grip_points")
