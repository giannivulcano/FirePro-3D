"""WM2 G10 -- overrides are full references (Q8)."""
import json

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_library import used_weight_names
from firepro3d.block_registry import linetype_users_in, prim_refs
from tests.lt3_support import make_linetype
from tests.wm2_support import nested_record, scene_with, sprinkler_def


def test_record_linetype_override_is_a_dependency(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    rec = nested_record(s.id, {"linetype": lt.id, "weight": "Thick"})
    assert prim_refs([rec]) == {s.id, lt.id}
    assert used_weight_names([{"primitives": [rec]}]) == {"Thick"}


def test_fpdb_bundles_record_override_linetype(qapp, tmp_path):
    lt = make_linetype()
    s = sprinkler_def()
    h = BlockDefinition.new(name="H", library="L", series="S",
                            primitives=[nested_record(s.id, {"linetype": lt.id})],
                            origin=(0.0, 0.0))
    ms, _inst = scene_with([lt, s, h], h.id)
    path = block_library.save_to_library(
        h, root=str(tmp_path), bundled=ms.block_registry.bundle_for(h.id))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert set(data["bundled"]) == {s.id, lt.id}


def test_placement_override_blocks_linetype_delete(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    ms, inst = scene_with([lt, s], s.id, {"linetype": lt.id})
    assert inst in linetype_users_in(ms, lt.id)
    assert ms.block_users_message(lt.id) is not None


def test_weight_rename_follows_placement_and_record(qapp):
    from firepro3d.display_manager import DisplayManager
    s = sprinkler_def()
    h = BlockDefinition.new(name="H", library="L", series="S",
                            primitives=[nested_record(s.id, {"weight": "Thick"})],
                            origin=(0.0, 0.0))
    ms, inst = scene_with([s, h], h.id, {"weight": "Thick"})
    # A second, un-overridden placement shows the record's own override
    # (the first placement's override would hide it); compile it pre-rename.
    inst2 = ms.place_block_instance(h.id, (0.0, 0.0), level=ms.active_level)
    assert {op.weight for op in inst2.render_ops() if op.kind == "stroke"} == {"Thick"}
    dm = DisplayManager(ms)
    assert dm._line_weight_in_use("Thick")
    dm._propagate_lw_rename("Thick", "Bold")
    assert inst.overrides["weight"] == "Bold"
    rec = ms.get_block_definition(h.id).primitives[0]
    assert rec["overrides"]["weight"] == "Bold"
    # Observable: the host recompiled, so the placement now strokes "Bold".
    assert {op.weight for op in inst2.render_ops() if op.kind == "stroke"} == {"Bold"}


def test_weight_rename_cancel_restores_placement_and_record(qapp):
    """Cancel replays the rename backwards while the Thick->Bold alias is
    still live: the placement must store the old name raw, not canonicalise
    it straight back to the new one (seam review)."""
    from firepro3d import paper_display as pd
    from firepro3d.display_manager import DisplayManager
    s = sprinkler_def()
    h = BlockDefinition.new(name="H", library="L", series="S",
                            primitives=[nested_record(s.id, {"weight": "Thick"})],
                            origin=(0.0, 0.0))
    ms, inst = scene_with([s, h], h.id, {"weight": "Thick"})
    # An un-overridden placement paints the record's own override.
    inst2 = ms.place_block_instance(h.id, (0.0, 0.0), level=ms.active_level)
    try:
        d = DisplayManager(ms, active_context="paper")
        row = [x.name for x in d._lw_defs].index("Thick")
        d._lw_table.item(row, 0).setText("Bold")
        assert inst.overrides["weight"] == "Bold"
        d.reject()
        assert inst.overrides["weight"] == "Thick"
        assert {op.weight for op in inst.render_ops()
                if op.kind == "stroke"} == {"Thick"}
        rec = ms.get_block_definition(h.id).primitives[0]
        assert rec["overrides"]["weight"] == "Thick"
        assert {op.weight for op in inst2.render_ops()
                if op.kind == "stroke"} == {"Thick"}
    finally:
        pd.set_weight_aliases({})
        pd.reset_project_line_weights()


# -- H4 wording: override users read "by blocks ..." (seam review) ----------

def _override_host(ms, lt_id, inner_id, name="H"):
    h = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[nested_record(inner_id, {"linetype": lt_id})],
                            origin=(0.0, 0.0))
    ms.register_block_definition(h)
    return h


def test_record_override_user_reads_by_blocks_inside(qapp):
    from firepro3d.model_space import Model_Space
    lt = make_linetype("Hidden")
    s = sprinkler_def()
    ms = Model_Space()
    for d in (lt, s):
        ms.register_block_definition(d)
    _override_host(ms, lt.id, s.id)
    msg = ms.block_users_message(lt.id)
    assert msg == ("\u201cHidden\u201d is used by blocks inside: H \u2014 "
                   "change their linetype override first.")
    assert "explode or remove it there" not in msg


def test_record_and_plan_placement_overrides_both_named(qapp):
    lt = make_linetype("Hidden")
    s = sprinkler_def()
    ms, _inst = scene_with([lt, s], s.id, {"linetype": lt.id})
    _override_host(ms, lt.id, s.id)
    assert ms.block_users_message(lt.id) == (
        "\u201cHidden\u201d is used by blocks inside: H, and by blocks in "
        "the plan \u2014 change their linetype override first.")


def test_plan_placement_override_reads_by_blocks_in_the_plan(qapp):
    lt = make_linetype("Hidden")
    s = sprinkler_def()
    ms, _inst = scene_with([lt, s], s.id, {"linetype": lt.id})
    assert ms.block_users_message(lt.id) == (
        "\u201cHidden\u201d is used by blocks in the plan \u2014 change "
        "their linetype override first.")


# -- Q8: a missing placement Linetype override draws the canvas badge --------

def _warn_near(ms, cx, cy):
    """Render *ms* at 0.1 px/mm; (any warn-tinted pixel within 15 px of the
    insertion at scene (cx, cy) mm, any elsewhere)."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter
    from tests.test_lt3_missing import _is_warn
    img = QImage(400, 400, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 400, 400), QRectF(-2000, -2000, 4000, 4000))
    p.end()
    px, py = (cx + 2000) / 10.0, (cy + 2000) / 10.0
    near = far = False
    for x in range(400):
        for y in range(400):
            if _is_warn(QColor(img.pixel(x, y))):
                if abs(x - px) <= 15 and abs(y - py) <= 15:
                    near = True
                else:
                    far = True
    return near, far


def test_missing_placement_linetype_override_draws_the_badge(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    from firepro3d.stroke_style import AS_AUTHORED
    # One line well clear of the insertion point, so the badge pad (centred
    # on the insertion) is what grows the bounds (cf. test_lt3_missing B).
    ln = LineItem(QPointF(-1500.0, 600.0), QPointF(-500.0, 600.0))
    d = BlockDefinition.new(name="Off", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms, inst = scene_with([d], d.id, {"linetype": "deadbeef"})
    plain = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    assert plain.overrides["linetype"] == AS_AUTHORED
    assert inst._has_missing_linetype() and not plain._has_missing_linetype()
    # Same pose: the bounds grow by the badge pad only for the override.
    ext, base = inst.boundingRect(), plain.boundingRect()
    assert ext.contains(base) and ext.contains(QPointF(0.0, 0.0))
    assert not base.contains(QPointF(0.0, 0.0))
    plain.set_block_pos(1000.0, -1000.0)
    inst.set_block_pos(1000.0, 500.0)
    near, far = _warn_near(ms, 1000.0, 500.0)
    assert near and not far                    # once, at its insertion point


# -- Q9: new placements start As Authored x2 (no sticky current) -------------

def test_new_placement_and_ghost_start_as_authored(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d.stroke_style import AS_AUTHORED
    s = sprinkler_def()
    ms, prev = scene_with([s], s.id, {"weight": "Thick", "linetype": "continuous"})
    both = {"weight": AS_AUTHORED, "linetype": AS_AUTHORED}
    ms.set_mode("place_block", template=s.id)
    ms._move_place_block(None, QPointF(0.0, 0.0))
    assert ms._place_block_ghost.overrides == both              # placement ghost
    ms._press_place_block(None, QPointF(50.0, 0.0), QPointF(50.0, 0.0),
                          None, None, None)                     # place_block click
    clicked = ms._block_instances[-1]
    assert clicked is not prev and clicked.overrides == both
    ms.set_mode(None)
    # The Blocks-browser drop (Model_View._drop_block) places with this call.
    dropped = ms.place_block_instance(s.id, (90.0, 0.0), rotation=0.0)
    assert dropped.overrides == both
    assert prev.overrides["weight"] == "Thick"
