"""SB4d P4 probe (c) / guard 2 first half: the SectionScene depth walk
(-50 + 0.01 per item, farthest first) is bounded below the annotation band
(design D5 / D8c, Phase 2 Q17)."""
import pytest
from PyQt6.QtWidgets import QGraphicsRectItem

N_ITEMS = 12_000      # design Q17: a big project's projected item count


def _walk(sec, n):
    """Register *n* real scene items at distinct depths (item 0 farthest)
    through the production registration path and run the walk."""
    sec.rebuild()                           # an empty model: creates the depth list
    items = [QGraphicsRectItem(0.0, 0.0, 1.0, 1.0) for _ in range(n)]
    for i, it in enumerate(items):
        sec.addItem(it)
        sec._register_depth_item(float(i), it)      # ascending sort = farthest first
    sec._assign_depth_z_values()
    return items


def test_p4_walk_starts_at_minus_50_and_steps_one_hundredth(qapp, section_scene_for):
    """Pins today's arithmetic (P4): 12,000 items end at -50 + 0.01 * 11,999
    = 69.99 -- above the literal 50 the section gridlines / datums used."""
    _ms, sec = section_scene_for("north")
    items = _walk(sec, N_ITEMS)
    assert items[0].zValue() == pytest.approx(-50.0)
    assert items[-1].zValue() == pytest.approx(-50.0 + 0.01 * (N_ITEMS - 1))   # 69.99
    assert items[-1].zValue() > 50.0          # today's literal section gridline z is reachable


def test_guard2_walk_is_clamped_below_the_text_band(qapp, section_scene_for, monkeypatch):
    """A walk that would run past the band stops at Z_DEPTH_CEIL
    (= Z_ANNOT_TEXT - 1.0 = 9,999.0, constants.py). The step is raised to
    1.0 so 12,000 items would reach -50 + 11,999 = 11,949 unclamped."""
    from firepro3d import section_scene
    from firepro3d.constants import Z_ANNOT_TEXT, Z_DEPTH_CEIL
    monkeypatch.setattr(section_scene, "_DEPTH_Z_STEP", 1.0)
    _ms, sec = section_scene_for("north")
    items = _walk(sec, N_ITEMS)
    top = max(it.zValue() for it in items)
    assert Z_DEPTH_CEIL == Z_ANNOT_TEXT - 1.0 == 9_999.0
    assert top == Z_DEPTH_CEIL
    assert top < Z_ANNOT_TEXT
    assert items[100].zValue() == pytest.approx(-50.0 + 100.0)   # below the ceiling the walk is unchanged
