"""FilledRegionItem guards (HF3 design section 5). Later tasks append classes."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QTransform
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.constants import Z_FILLED_REGION
from firepro3d.fill_layers import BackgroundLayer, FillLayers
from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.selection_manipulator import item_capabilities


def _render(scene, area=QRectF(0, 0, 120, 120), size=120) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), area)
    p.end()
    return img


def _px(img, x, y) -> QColor:
    return QColor(img.pixel(x, y))


def _is_white(c: QColor) -> bool:
    return c.red() > 250 and c.green() > 250 and c.blue() > 250


def _statuses(scene):
    """Capture ``_show_status`` messages (idiom: tests/test_modify_tools_offset.py:30-35)."""
    log = []
    orig = scene._show_status
    scene._show_status = lambda msg, timeout=5000: (log.append(msg), orig(msg, timeout))
    return log


def square_pieces(size=100.0):
    a, b, c, d = QPointF(10, 10), QPointF(10 + size, 10), QPointF(10 + size, 10 + size), QPointF(10, 10 + size)
    return [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]


def ring_region() -> FilledRegionItem:
    """100x100 square at (10,10) with a r=15 circular island at (60,60)."""
    return FilledRegionItem.from_pieces([square_pieces(), [CircleItem(QPointF(60, 60), 15)]])


class TestModel:
    def test_defaults_match_r9_r11(self, qapp):
        r = ring_region()
        assert r.fill_layers == FillLayers(background=BackgroundLayer("token:auto", 1.0))
        assert r.outline is False and r.is_closed() and r.is_fillable()
        assert r.zValue() == Z_FILLED_REGION
        assert r._REFERENCE_CAPABLE is False
        assert len(r._loops) == 2 and r.path().fillRule() == Qt.FillRule.OddEvenFill

    def test_pieces_are_static_copies(self, qapp):
        src = square_pieces()
        r = FilledRegionItem.from_pieces([src])
        assert all(p is not s for p in r._loops[0] for s in src)
        src[0].translate(500, 500)
        assert r.path().boundingRect() == QRectF(10, 10, 100, 100)

    def test_record_round_trip(self, qapp):
        r = ring_region()
        r.outline = True
        r.fill_layers = FillLayers(background=BackgroundLayer("#ff0000", 0.5))
        d = r.to_dict()
        assert d["type"] == "draw_filled_region" and d["outline"] is True
        assert [[p["type"] for p in lp] for lp in d["loops"]] == [["draw_line"] * 4, ["draw_circle"]]
        assert "fill" in d
        r2 = FilledRegionItem.from_dict(d)
        d2 = r2.to_dict()
        assert d2["loops"] == d["loops"] and d2["fill"] == d["fill"] and d2["outline"] is True

    def test_empty_fill_writes_no_key(self, qapp):
        r = ring_region()
        r.fill_layers = FillLayers()
        assert "fill" not in r.to_dict()

    def test_unknown_piece_type_is_skipped_and_empty_loop_dropped(self, qapp):
        d = ring_region().to_dict()
        d["loops"][1][0]["type"] = "no_such_type"
        r = FilledRegionItem.from_dict(d)
        assert len(r._loops) == 1

    def test_capabilities_match_the_shapes(self, qapp):
        r = ring_region()
        assert item_capabilities(r) == {"translate", "rotate"}
        assert not hasattr(r, "manip_scale") and r.manip_handles() == []

    def test_transforms_move_every_piece(self, qapp):
        r = ring_region()
        r.translate(5, 0)
        assert r.path().boundingRect().left() == pytest.approx(15)
        r.manip_rotate(90.0, QPointF(15, 10))
        assert r.path().boundingRect().width() == pytest.approx(100, abs=1e-6)
        r.manip_scale_about(QPointF(0, 0), 2.0)
        assert r.path().boundingRect().width() == pytest.approx(200, abs=1e-6)
        before = r.path().boundingRect()
        r.manip_reflect(QPointF(0, 0), QPointF(0, 1))          # mirror across the y axis
        after = r.path().boundingRect()
        assert after.left() == pytest.approx(-before.right(), abs=1e-6)
        assert after.right() == pytest.approx(-before.left(), abs=1e-6)


class TestPaint:
    def _scene(self, region):
        s = QGraphicsScene()
        s.addItem(region)
        return s

    def test_solid_fill_between_outer_and_island_only(self, qapp):
        r = ring_region()
        r.fill_layers = FillLayers(background=BackgroundLayer("#0000ff", 1.0))
        img = _render(self._scene(r))
        assert not _is_white(_px(img, 20, 20))          # between square edge and circle
        assert _is_white(_px(img, 60, 60))              # island centre (OddEven)
        assert _is_white(_px(img, 5, 5))                # outside

    def test_outline_off_paints_no_stroke_on_the_edge(self, qapp):
        r = ring_region()
        r.fill_layers = FillLayers()
        img = _render(self._scene(r))
        assert _is_white(_px(img, 10, 60))              # left edge, no stroke, no fill

    def test_outline_on_paints_the_edge(self, qapp):
        # an explicit stroke colour: TOKEN_AUTO resolves to the theme ink, which
        # a white render could not distinguish under a dark theme
        r = FilledRegionItem(ring_region().to_dict()["loops"], color="#ff0000")
        r.fill_layers = FillLayers()
        r.outline = True
        r.update()
        img = _render(self._scene(r))
        assert not _is_white(_px(img, 10, 60))

    def test_interior_click_hits_the_region(self, qapp):
        r = ring_region()
        s = self._scene(r)
        assert s.itemAt(QPointF(20, 20), QTransform()) is r
        assert r.get_closed_path().contains(QPointF(20, 20))
        assert not r.get_closed_path().contains(QPointF(60, 60))


class TestPanel:
    def test_rows_and_outline_toggle(self, qapp):
        r = ring_region()
        props = r.get_properties()
        assert props["Type"]["value"] == "Filled Region"
        assert props["Outline"] == {"type": "toggle", "value": False}
        assert "Reference" not in props and props["Fill"]["type"] == "fill"
        r.set_property("Outline", True)
        assert r.outline is True and r.to_dict()["outline"] is True


class TestStrokePieces:
    def test_one_curve_per_loop_so_dashed_linetypes_have_pieces(self, qapp):
        sp = ring_region().stroke_pieces()
        assert len(sp) == 2 and all(len(c.pts) >= 3 for c in sp)


# ── Task 3: registry seams (G9a placed-instance pixels, G9b round-trips) ──
from firepro3d.block_definition import BlockDefinition, _PRIMITIVE_FACTORY
from firepro3d.model_space import Model_Space


def editor_scene():
    """A Block Editor scene (containment C1) — the only scene that holds regions."""
    return Model_Space(scene_role="block_editor")


def add_region(scene, region=None):
    region = region or ring_region()
    scene.addItem(region)
    scene._filled_regions.append(region)
    return region


class TestRegistry:
    def test_factory_and_style_table(self, qapp):
        from firepro3d.stroke_style import STYLED_TYPES
        assert _PRIMITIVE_FACTORY["draw_filled_region"] is FilledRegionItem
        assert "draw_filled_region" in STYLED_TYPES
        assert Model_Space._GEOM_TYPE_REGISTRY["draw_filled_region"] == (FilledRegionItem, "_filled_regions")

    def test_undo_round_trip(self, qapp):
        es = editor_scene()
        r = add_region(es)
        r.outline = True
        state = es._capture_network()
        d = r.to_dict()
        es._restore_network(state)
        assert len(es._filled_regions) == 1
        assert es._filled_regions[0].to_dict()["loops"] == d["loops"]
        assert es._filled_regions[0].outline is True

    def test_clipboard_round_trip(self, qapp):
        es = editor_scene()
        r = add_region(es)
        r.setSelected(True)
        es.copy_selected_items()
        es.paste_items(QPointF(5.0, 0.0))
        assert len(es._filled_regions) == 2
        pasted = es._filled_regions[1]
        assert pasted.path().boundingRect().left() == pytest.approx(15)
        assert [[p.to_dict()["type"] for p in lp] for lp in pasted._loops] == \
               [[p.to_dict()["type"] for p in lp] for lp in r._loops]

    def test_plan_scene_refuses_paste_and_loader_drops_the_key(self, qapp, tmp_path):
        # paste refusal lives in ModifyToolsController.begin_paste (306-320): any
        # _GEOM_TYPE_REGISTRY type is refused outside the Block Editor
        plan = Model_Space()
        es = editor_scene()
        r = add_region(es)
        r.setSelected(True)
        es.copy_selected_items()
        log = _statuses(plan)
        assert plan._modify_ctl.begin_paste() is False      # read 306-320 for the exact arity
        assert "2D geometry can only be pasted in the Block Editor" in log
        assert plan._filled_regions == []
        # loader: a project file holding the key loads no region (containment C1/C8)
        path = tmp_path / "e.fpd"
        es.save_to_file(str(path))
        plan2 = Model_Space()
        plan2.load_from_file(str(path))
        assert plan2._filled_regions == []
        assert not any(isinstance(i, FilledRegionItem) for i in plan2.items())

    def test_remove_from_lists_and_materialize(self, qapp):
        from firepro3d import schematic_scene
        es = editor_scene()
        r = add_region(es)
        assert r in schematic_scene.materialized_items(es)
        es._remove_item_from_lists(r)
        assert es._filled_regions == []

    def test_display_manager_collects_it_under_2d_geometry(self, qapp):
        from firepro3d.display_manager import _items_for_category_static, _is_geo2d_item
        es = editor_scene()
        r = add_region(es)
        assert r in _items_for_category_static(es, "2D Geometry")
        assert _is_geo2d_item(r)

    def test_paper_category(self, qapp):
        from firepro3d.paper_display import _category_for_item
        assert _category_for_item(ring_region()) == "Construction"

    def test_scene_tools_sees_it(self, qapp):
        es = editor_scene()
        r = add_region(es)
        assert r in es._tools._all_geometry_items()


class TestPlacedInstance:
    """G9a: a block whose definition holds a region renders the fill in a plan scene."""

    def test_placed_instance_pixels(self, qapp):
        es = editor_scene()
        lines = square_pieces()                        # (10,10)-(110,110)
        circ = CircleItem(QPointF(60, 60), 15)
        for ln in lines:
            es.addItem(ln); es._draw_lines.append(ln)
        es.addItem(circ); es._draw_circles.append(circ)
        region = FilledRegionItem.from_pieces([lines, [circ]])
        region.fill_layers = FillLayers(background=BackgroundLayer("#0000ff", 1.0))
        add_region(es, region)
        # editor scene: the region sits under the lines (z -1 < 0): the edge picks the line
        assert es.itemAt(QPointF(60, 10), QTransform()) is lines[0]
        assert es.itemAt(QPointF(20, 20), QTransform()) is region
        from firepro3d import schematic_scene
        prims = [it.to_dict() for it in schematic_scene.materialized_items(es)]
        assert any(p["type"] == "draw_filled_region" for p in prims)
        defn = BlockDefinition.new(name="R", library="L", series="S", origin=(0.0, 0.0),
                                   primitives=prims)
        plan = Model_Space()
        plan.register_block_definition(defn)
        plan.place_block_instance(defn.id, (0.0, 0.0))
        img = _render(plan, QRectF(0, 0, 120, 120))
        assert not _is_white(_px(img, 20, 20))        # between square and circle: fill
        assert _is_white(_px(img, 60, 60))            # island centre: background
        assert not _is_white(_px(img, 10, 60))        # square edge: the source line's stroke
        assert _is_white(_px(img, 5, 5))              # outside

    def test_compiled_region_strokes_only_with_outline_on(self, qapp):
        """The compile STROKE op follows ``outline`` (design section 3, Block compile row)."""
        region = FilledRegionItem(ring_region().to_dict()["loops"], color="#ff0000")
        region.fill_layers = FillLayers()
        for outline, expect_ink in ((False, False), (True, True)):
            region.outline = outline
            defn = BlockDefinition.new(name=f"O{outline}", library="L", series="S",
                                       origin=(0.0, 0.0), primitives=[region.to_dict()])
            plan = Model_Space()
            plan.register_block_definition(defn)
            plan.place_block_instance(defn.id, (0.0, 0.0))
            img = _render(plan, QRectF(0, 0, 120, 120))
            assert (not _is_white(_px(img, 10, 60))) is expect_ink, outline


class TestReviewGuards:
    def test_halo_is_area_with_empty_fill(self, qapp):
        from firepro3d.halo import halo_is_area
        r = ring_region()
        r.fill_layers = FillLayers()
        r.outline = False
        assert halo_is_area(r) is True

    def test_outline_on_default_colour_resolves_to_theme_ink(self, qapp):
        from firepro3d.colour_tokens import resolve_colour
        from firepro3d.constants import TOKEN_AUTO
        r = ring_region()
        r.fill_layers = FillLayers()
        r.outline = True
        assert getattr(r, "_display_color", None) is None
        s = QGraphicsScene()
        s.addItem(r)
        img = _render(s)
        # theme ink may be white under a dark theme: assert the pen colour
        assert r.pen().color() == resolve_colour(TOKEN_AUTO, item=r)
        ink = resolve_colour(TOKEN_AUTO, item=r)
        if not _is_white(ink):
            assert not _is_white(_px(img, 10, 60))

    def test_empty_fill_round_trips_with_no_key(self, qapp):
        r = ring_region()
        r.fill_layers = FillLayers()
        d = r.to_dict()
        assert "fill" not in d
        assert FilledRegionItem.from_dict(d).fill_layers == FillLayers()

    def test_unknown_piece_type_logs_a_warning(self, qapp, caplog):
        import logging
        d = ring_region().to_dict()
        d["loops"][1][0]["type"] = "no_such_type"
        with caplog.at_level(logging.WARNING, logger="firepro3d.filled_region"):
            FilledRegionItem.from_dict(d)
        assert any("unknown" in m and "no_such_type" in m for m in caplog.messages)


# ── Task 4: creation UX (R5, R8, R12, R15) ──
from firepro3d.text_item import TextAnnotationData, TextItem


def _square_in(es):
    a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    lines = [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]
    for ln in lines:
        es.addItem(ln); es._draw_lines.append(ln)
    return lines


class TestFillSelected:
    def test_fill_creates_one_region_selected_alone_sources_kept(self, qapp):
        es = editor_scene()
        lines = _square_in(es)
        circ = CircleItem(QPointF(50, 50), 15)
        es.addItem(circ); es._draw_circles.append(circ)
        txt = TextItem(TextAnnotationData(text="x", x=10.0, y=10.0, height_mm=100.0))
        es.addItem(txt); es._texts.append(txt)
        for it in lines + [circ, txt]:
            it.setSelected(True)
        pos0 = es._undo_pos
        log = _statuses(es)
        region = es.fill_selected_items()
        assert isinstance(region, FilledRegionItem) and es._filled_regions == [region]
        assert es.selectedItems() == [region]
        assert len(region._loops) == 2 and len(es._draw_lines) == 4 and len(es._draw_circles) == 1
        assert region.fill_layers == FillLayers(background=BackgroundLayer("token:auto", 1.0))
        assert es._undo_pos == pos0 + 1
        assert log[-1] == "Filled Region created (2 loops)"

    def test_failed_fill_changes_nothing(self, qapp):
        es = editor_scene()
        lines = _square_in(es)
        es.removeItem(lines[3]); es._draw_lines.remove(lines[3])
        for ln in lines[:3]:
            ln.setSelected(True)
        n0, pos0 = len(es.items()), es._undo_pos
        log = _statuses(es)
        assert es.fill_selected_items() is None
        assert es._filled_regions == [] and len(es.items()) == n0 and es._undo_pos == pos0
        assert len(es.selectedItems()) == 3
        assert log[-1].startswith("Not enclosed")

    def test_region_and_reference_pieces_are_ignored(self, qapp):
        es = editor_scene()
        lines = _square_in(es)
        lines[0].reference = True
        r = add_region(es)
        for it in lines + [r]:
            it.setSelected(True)
        log = _statuses(es)
        assert es.fill_selected_items() is None
        assert len(es._filled_regions) == 1
        assert log[-1] == "Not enclosed -- 3 curve(s) have an open end"

    def test_nothing_eligible(self, qapp):
        es = editor_scene()
        log = _statuses(es)
        assert es.fill_selected_items() is None
        assert log[-1] == "Select closed shapes or curves that form a closed outline"

    def test_plan_scene_is_a_no_op(self, qapp):
        plan = Model_Space()
        lines = _square_in(plan)
        for ln in lines:
            ln.setSelected(True)
        assert plan.fill_selected_items() is None and plan._filled_regions == []

    def test_fill_candidates_helper(self, qapp):
        es = editor_scene()
        lines = _square_in(es)
        r = add_region(es)
        assert Model_Space.fill_candidates(lines + [r]) == lines


# ── Task 5: Explode (R6) ──
class TestExplode:
    def test_region_explodes_to_its_pieces_in_one_undo_step(self, qapp):
        es = editor_scene()
        r = add_region(es)                        # 4 lines + 1 circle
        old_uids = {rec.get("uid") for loop in r.to_dict()["loops"] for rec in loop}
        r.setSelected(True)
        es.push_undo_state()
        pos0 = es._undo_pos
        new = es.explode_selected_blocks()
        assert r.scene() is None and es._filled_regions == []
        assert len(new) == 5 and len(es._draw_lines) == 4 and len(es._draw_circles) == 1
        assert all(i.isSelected() for i in new)
        assert all(it.fill_layers.is_empty for it in new)
        new_uids = [it._uid for it in new]
        assert len(set(new_uids)) == 5 and not (set(new_uids) & old_uids)
        assert es._undo_pos == pos0 + 1
        es.undo()
        assert len(es._filled_regions) == 1 and es._draw_lines == [] and es._draw_circles == []

    def test_exploded_pieces_carry_the_region_stroke_record(self, qapp):
        es = editor_scene()
        r = add_region(es, FilledRegionItem(ring_region().to_dict()["loops"], color="#123456"))
        assert r.style["colour"] == "#123456"           # the ctor colour lands in the record
        assert r.outline is False                        # Invisible outline (design section 4)
        r.setSelected(True)
        new = es.explode_selected_blocks()
        assert len(new) == 5 and all(it.style == r.style for it in new)
        assert all(it.isVisible() for it in new)         # pieces are ordinary stroked curves

    def test_block_and_region_explode_together(self, qapp):
        es = editor_scene()
        d = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                                primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()])
        es.register_block_definition(d)
        inst = es.place_block_instance(d.id, (200.0, 200.0))
        r = add_region(es)
        inst.setSelected(True); r.setSelected(True)
        pos0 = es._undo_pos
        new = es.explode_selected_blocks()
        assert len(new) == 6 and es._block_instances == [] and es._filled_regions == []
        assert es._undo_pos == pos0 + 1

    def test_region_beside_an_unexplodable_block_still_explodes(self, qapp):
        """Design section 4 'handles both': a missing-definition block beside a
        region does not refuse the whole Explode; the block stays, the region goes."""
        es = editor_scene()
        orphan = es.place_block_instance("no-such-block", (0.0, 0.0))
        r = add_region(es)
        orphan.setSelected(True); r.setSelected(True)
        log = _statuses(es)
        new = es.explode_selected_blocks()
        assert len(new) == 5 and es._filled_regions == [] and orphan.scene() is es
        assert not any("can't be exploded" in m for m in log)

    def test_no_block_no_region_status(self, qapp):
        es = editor_scene()
        log = _statuses(es)
        assert es.explode_selected_blocks() == []
        assert log[-1] == "Select a block or Filled Region to explode"


# -- Task 6: snap / HALO / pick (D-A26) --
import math
from firepro3d.halo import halo_is_area


class TestSnapHaloPick:
    def test_collect_yields_piece_endpoints_with_outline_off(self, qapp):
        es = editor_scene()
        r = add_region(es)
        pts = [p for k, p, _n in es._snap_engine._collect(r) if k == "endpoint"]
        for exp in (QPointF(10, 10), QPointF(110, 10), QPointF(110, 110), QPointF(10, 110)):
            assert any(math.hypot(p.x() - exp.x(), p.y() - exp.y()) < 0.01 for p in pts), exp
        centers = [p for k, p, _n in es._snap_engine._collect(r) if k == "center"]
        assert any(math.hypot(p.x() - 60, p.y() - 60) < 0.01 for p in centers)

    def test_collect_recurses_into_a_circle_piece(self, qapp):
        es = editor_scene()
        r = add_region(es, ring_region())      # island: circle r=15 at (60, 60)
        snaps = list(es._snap_engine._collect(r))
        quads = [p for k, p, _n in snaps if k == "quadrant"]
        assert any(math.hypot(p.x() - 75, p.y() - 60) < 0.01 for p in quads), quads
        centers = [p for k, p, _n in snaps if k == "center"]
        assert sum(math.hypot(p.x() - 60, p.y() - 60) < 0.01 for p in centers) >= 1

    def test_halo_is_area_with_and_without_fill(self, qapp):
        r = ring_region()
        es = editor_scene(); add_region(es, r)
        assert halo_is_area(r)                      # halo.py:108-111 via _draws_fill()
        r.fill_layers = FillLayers()
        assert halo_is_area(r)                      # HALO_AREA = True (D-A26): still an area with no fill

    def test_crossing_line_wins_the_pick(self, qapp):
        es = editor_scene()
        r = add_region(es)
        ln = LineItem(QPointF(0, 30), QPointF(200, 30))
        es.addItem(ln); es._draw_lines.append(ln)
        assert es.itemAt(QPointF(30, 30), QTransform()) is ln
        assert es.itemAt(QPointF(30, 50), QTransform()) is r


# -- Task 7: D-A13 tool matrix (G9c) --
from firepro3d.selection_manipulator import bake_translate


def _fill_pixel_moves(es, region, before_pt, after_pt):
    region.fill_layers = FillLayers(background=BackgroundLayer("#0000ff", 1.0))
    img = _render(es, QRectF(0, 0, 240, 240), 240)
    return (not _is_white(_px(img, int(after_pt.x()), int(after_pt.y())))
            and _is_white(_px(img, int(before_pt.x()), int(before_pt.y()))))


def _rect_close(r: QRectF, x, y, w, h) -> bool:
    return all(abs(a - b) < 1e-6 for a, b in
               ((r.left(), x), (r.top(), y), (r.width(), w), (r.height(), h)))


class TestToolMatrix:
    def test_move_through_bake_translate(self, qapp):
        es = editor_scene()
        r = add_region(es)
        assert bake_translate(r, 100, 0)                 # selection_manipulator._bake_move's call
        assert _rect_close(r.path().boundingRect(), 110, 10, 100, 100)
        assert _fill_pixel_moves(es, r, QPointF(20, 20), QPointF(120, 20))

    def test_rotate_mirror_scale_hooks_are_the_tools_hooks(self, qapp):
        es = editor_scene()
        r = add_region(es)
        assert hasattr(r, "manip_reflect") and hasattr(r, "manip_scale_about") and hasattr(r, "manip_rotate")
        r.manip_rotate(180.0, QPointF(60, 60))
        assert _rect_close(r.path().boundingRect(), 10, 10, 100, 100)
        r.manip_reflect(QPointF(60, 0), QPointF(60, 1))
        assert _rect_close(r.path().boundingRect(), 10, 10, 100, 100)
        r.manip_scale_about(QPointF(10, 10), 0.5)
        assert _rect_close(r.path().boundingRect(), 10, 10, 50, 50)

    @pytest.mark.parametrize("tool, verb", [("offset", "offset"), ("trim", "trimmed"),
                                            ("extend", "extended"), ("break", "broken"),
                                            ("break_at_point", "broken"),
                                            ("fillet", "filleted")])
    def test_refused_tools_leave_it_unchanged_with_a_status(self, qapp, make_model_space, tool, verb):
        from tests._snap_polish_helpers import click         # click(view, scene_pt)
        scene = make_model_space()
        view = scene.views()[0]
        scene.scene_role = "block_editor"
        r = add_region(scene)
        r.setSelected(True)
        d0 = r.to_dict(); pos0 = scene._undo_pos
        log = _statuses(scene)
        if tool == "offset":
            scene._modify_ctl.begin_offset([r])
        else:
            scene.set_mode(tool)
            click(view, QPointF(20, 20))     # inside the region (its shape() is the area), on no curve
        assert r.to_dict() == d0 and scene._undo_pos == pos0
        assert f"Filled Regions can't be {verb}" in log
