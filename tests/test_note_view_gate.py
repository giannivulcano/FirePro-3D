"""Fix round item 1: a Note is gated by its view key alone (D9), not by its level."""
from PyQt6.QtCore import QPointF, QRectF

from tests.test_note_view_scope import PLAN, place_note, view_fixture

L2 = "plan:Plan: Level 2"


def _sweep(fx, key, level, **rng):
    ms = fx["ms"]
    ms.active_view_key, ms.active_level = key, level
    fx["lm"].apply_to_scene(ms, level, **rng)


def test_a_note_copied_on_plan_l1_and_pasted_on_plan_l2_shows_there(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    src = place_note(ms, PLAN)
    ms.active_view_key, ms.active_level = L2, "Level 2"
    (cp,) = ms.paste_items(QPointF(50, 0), data=ms._clipboard_item_dicts([src]))
    assert cp.note["view"] == L2 and cp.level == "Level 2"       # view and level agree in the data
    _sweep(fx, L2, "Level 2")
    assert cp.isVisible() and not src.isVisible()
    _sweep(fx, PLAN, "Level 1")
    assert src.isVisible() and not cp.isVisible()


def test_a_note_pasted_into_a_detail_on_another_level_shows_there(qapp):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    det.create_detail("D2", QRectF(0, 0, 500, 500), "Level 3")
    src = place_note(ms, PLAN)
    ms.active_view_key, ms.active_level = "detail:D2", "Level 3"
    (cp,) = ms.paste_items(QPointF(0, 0), data=ms._clipboard_item_dicts([src]))
    assert cp.level == "Level 3"
    _sweep(fx, "detail:D2", "Level 3")
    assert cp.isVisible()


def test_a_mirror_copy_joins_the_active_level_too(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    src = place_note(ms, PLAN)
    ms.active_view_key, ms.active_level = L2, "Level 2"
    cp = ms._add_from_dict(src.to_dict())
    assert cp.note["view"] == L2 and cp.level == "Level 2"


def test_a_note_ignores_the_z_range_filter(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    n = place_note(ms, PLAN)
    n.level = "Level 3"                                       # far above this view's range
    _sweep(fx, PLAN, "Level 1", view_height=1000.0, view_depth=0.0)
    assert n.isVisible() and n.opacity() == 1.0


def test_editing_a_notes_level_row_keeps_it_in_its_view(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    n = place_note(ms, PLAN)
    n.set_property("Level", "Level 2")                        # the panel's own path
    assert n.level == "Level 2"
    _sweep(fx, PLAN, "Level 1")
    assert n.isVisible()


def test_a_detail_whose_level_changed_still_shows_its_notes(qapp):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    n = place_note(ms, "detail:D1")
    det.get_marker("D1").set_property("Level", "Level 2")
    _sweep(fx, "detail:D1", "Level 2")
    assert n.isVisible()


def test_a_note_in_another_view_stays_hidden_and_no_key_hides_all(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    other = place_note(ms, "detail:D1")
    _sweep(fx, PLAN, "Level 1")
    assert not other.isVisible()
    mine = place_note(ms, PLAN)
    _sweep(fx, "", "Level 1")                                  # no view key: today's behaviour
    assert not mine.isVisible() and not other.isVisible()
