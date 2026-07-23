"""Tests for the parametric title block template system (data + solver + I/O)."""
import copy
import os

import pytest
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import QApplication

import firepro3d.titleblock_template as tbt
from firepro3d.constants import (
    TB_CELL_PAD_MM, TB_LABEL_ROW_MM, TB_STRIP_MIN_MM, TB_AREA_MIN_MM,
)
from firepro3d.titleblock_template import (
    BorderStyle, FieldDef, Slot, TemplateLayout, TitleBlockTemplate,
    make_default_template, migrate_legacy_fields, native_orientation,
    new_field_id, resolve_text, solve_layout, validate,
    _cell_font,
    place_field, unplace_field, move_field, pair_field,
)

_app = QApplication.instance() or QApplication([])

PAPER_W, PAPER_H = 863.6, 558.8      # ANSI D landscape


def _lay3(fields, rows, **kw):
    return TemplateLayout(fields=fields, rows=rows, **kw)


# ─────────────────────────────────────────────────────────────────────────────
# TestSolveRev3 — rev-3 solver: rows walk, token resolution, sub-rects
# ─────────────────────────────────────────────────────────────────────────────

class TestSolveRev3:
    def test_flat_index_row_major(self):
        fs = [FieldDef(id=i, name=i, text="x") for i in ("a", "b", "c")]
        lay = _lay3(fs, [[Slot("a")], [Slot("b"), Slot("c")]])
        sol = solve_layout(lay, PAPER_W, PAPER_H, {})
        assert sol.cell_field_ids == ["a", "b", "c"]
        assert len(sol.cell_rects) == 3
        assert sol.row_spans == [(0, 1), (1, 2)]
        assert sol.cell_rects[1].top() == sol.cell_rects[2].top()
        assert abs(sol.cell_rects[1].width() * 2
                   - sol.strip_rect.width()) < 1e-6

    def test_tokens_resolve_and_unknown_warns(self):
        fs = [FieldDef(id="a", name="A", text="@[Company] @[Nope]")]
        sol = solve_layout(_lay3(fs, [[Slot("a")]]), PAPER_W, PAPER_H,
                           {"Company": "Acme"})
        assert sol.cell_lines[0][0].startswith("Acme")
        assert any("Nope" in w for w in sol.warnings)

    def test_image_remainder_band(self):
        fs = [FieldDef(id="a", name="A", label="Co", text="line",
                       image_data="AAAA")]
        sol = solve_layout(_lay3(fs, [[Slot("a", 40.0)]]), PAPER_W, PAPER_H, {})
        img = sol.cell_image_rects[0]
        txt = sol.cell_text_rects[0]
        lbl = sol.cell_label_rects[0]
        assert img is not None and lbl is not None and txt is not None
        assert lbl.bottom() <= img.top() + 1e-6
        assert img.bottom() <= txt.top() + 1e-6
        assert txt.bottom() <= sol.cell_rects[0].bottom() - TB_CELL_PAD_MM + 1e-6

    def test_image_no_room_warns_and_hides(self):
        fs = [FieldDef(id="a", name="A", text="x\n" * 30, image_data="AAAA")]
        sol = solve_layout(_lay3(fs, [[Slot("a", 5.0)]]), PAPER_W, PAPER_H, {})
        assert sol.cell_image_rects[0] is None
        assert any("no room" in w.lower() for w in sol.warnings)

    def test_no_image_text_top_aligned_as_rev2(self):
        fs = [FieldDef(id="a", name="A", label="L", text="hello")]
        sol = solve_layout(_lay3(fs, [[Slot("a", 30.0)]]), PAPER_W, PAPER_H, {})
        txt = sol.cell_text_rects[0]
        exp_top = sol.cell_rects[0].top() + TB_CELL_PAD_MM + TB_LABEL_ROW_MM
        assert abs(txt.top() - exp_top) < 1e-6

    def test_dynamic_row_fills_strip(self):
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = _lay3(fs, [[Slot("a", 10.0)], [Slot("b", 10.0, sizing="dynamic")]])
        sol = solve_layout(lay, PAPER_W, PAPER_H, {})
        assert abs(sol.cell_rects[-1].bottom() - sol.strip_rect.bottom()) < 1e-6

    def test_dangling_slot_dropped_with_warning(self):
        fs = [FieldDef(id="a", name="A")]
        lay = _lay3(fs, [[Slot("a")], [Slot("ghost")]])
        sol = solve_layout(lay, PAPER_W, PAPER_H, {})
        assert sol.cell_field_ids == ["a"]
        assert any("missing field" in w.lower() for w in sol.warnings)

    def test_revision_table_rows_newest_first(self):
        fs = [FieldDef(id="r", name="Revs", kind="revision_table",
                       label="Revisions", revision_rows=2)]
        revs = [{"no": "1", "description": "first", "date": "d1"},
                {"no": "2", "description": "second", "date": "d2"},
                {"no": "3", "description": "third", "date": "d3"}]
        sol = solve_layout(_lay3(fs, [[Slot("r", 25.0)]]), PAPER_W, PAPER_H,
                           {"__revisions__": revs})
        shown = sol.cell_revision_rows[0]
        assert [r["no"] for r in shown] == ["3", "2"]

    def test_default_template_solves_clean(self):
        t = make_default_template()
        # Seed all standard keys (known-but-empty = no Unknown warning per DD-13)
        values = {
            "Company": "Acme", "Title": "Plan", "Scale": "1:100",
            "Project": "", "Address": "", "Date": "",
            "Drawn By": "", "Checked By": "", "Drawing No": "", "Rev": "",
        }
        sol = solve_layout(t.layout, PAPER_W, PAPER_H, values)
        assert len(sol.cell_rects) == 13
        assert [n for _f, n in sol.row_spans] == [1, 1, 1, 1, 1, 2, 2, 2, 1, 1]
        assert abs(sol.cell_rects[-1].bottom()
                   - sol.strip_rect.bottom()) < 1e-6      # dynamic stamp
        # no warnings: all default tokens are known keys or empty-known
        assert not [w for w in sol.warnings if "Unknown" in w]

    def test_row_layout_indices_skips_dangling_rows(self):
        """SolvedLayout.row_layout_indices[k] == index in variant.rows (not solved index)."""
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = _lay3(fs, [[Slot("ghost")],      # fully dangling → not rendered
                         [Slot("a", 20.0)], [Slot("b", 20.0)]])
        sol = solve_layout(lay, PAPER_W, PAPER_H, {})
        # Two rendered rows (a and b); ghost row is dropped.
        # Solved row 0 → layout row 1; solved row 1 → layout row 2.
        assert sol.row_layout_indices == [1, 2]

    def test_dynamic_distribution_ignores_wrap_growth(self):
        # Row "a": dynamic, min 10, long text that wrap-grows well past 10.
        # Row "b": dynamic, min 30, no text.
        # DD-8b: leftover splits 10:30 by MIN heights, not solved heights.
        fs = [FieldDef(id="a", text="word " * 60),
              FieldDef(id="b")]
        lay = _lay3(fs, [[Slot("a", 10.0, sizing="dynamic")],
                         [Slot("b", 30.0, sizing="dynamic")]])
        sol = solve_layout(lay, PAPER_W, PAPER_H, {})
        grown_a = sol.cell_rects[0].height()
        grown_b = sol.cell_rects[1].height()
        # b's extra share must be 3x a's extra share
        # compare against static solve to isolate the dynamic bonus
        lay_static = _lay3(fs, [[Slot("a", 10.0)], [Slot("b", 30.0)]])
        sol_static = solve_layout(lay_static, PAPER_W, PAPER_H, {})
        extra_a = grown_a - sol_static.cell_rects[0].height()
        extra_b = grown_b - sol_static.cell_rects[1].height()
        assert extra_a > 0 and extra_b > 0
        assert abs(extra_b - 3 * extra_a) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# TestSolveRev3Ported — behaviors from the 8 deleted rev-2 classes
# ─────────────────────────────────────────────────────────────────────────────

class TestSolveRev3Ported:
    """Rev-2 solver behaviors ported to the rev-3 model via FieldDef/Slot/rows."""

    PW, PH = 863.6, 558.8

    # ── Area/strip geometry (was TestSolver.test_area_and_strip_rects) ───────

    def test_area_and_strip_rects(self):
        f = FieldDef(id="s", name="Stamp")
        lay = _lay3([f], [[Slot("s", 20.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert sol.strip_rect.right() == pytest.approx(self.PW - lay.margin_edge_mm)
        assert sol.strip_rect.width() == pytest.approx(lay.strip_width_mm)
        assert sol.area_rect.right() == pytest.approx(
            sol.strip_rect.left() - lay.margin_strip_mm)
        assert sol.area_rect.left() == pytest.approx(lay.margin_edge_mm)

    # ── Stack positions & min heights (was TestSolver) ────────────────────────

    def test_stack_positions_and_min_heights(self):
        f0 = FieldDef(id="s0", name="S0")
        f1 = FieldDef(id="s1", name="S1")
        lay = _lay3([f0, f1], [[Slot("s0", 30.0)], [Slot("s1", 15.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        r0, r1 = sol.cell_rects[0], sol.cell_rects[1]
        assert r0.top() == pytest.approx(sol.strip_rect.top())
        assert r0.height() == pytest.approx(30.0)
        assert r1.top() == pytest.approx(r0.bottom())
        assert r1.height() == pytest.approx(15.0)

    # ── Two-slot row: half-width + row height = max (was TestSolver) ─────────

    def test_pairing_half_width_row_height_max(self):
        fs = [FieldDef(id="sc", name="Scale", text="@[Scale]"),
              FieldDef(id="dt", name="Date", text="@[Date]")]
        lay = _lay3(fs, [[Slot("sc", 10.0), Slot("dt", 14.0)]])
        sol = solve_layout(lay, self.PW, self.PH,
                           {"Scale": "1:100", "Date": "2026-07-21"})
        r0, r1 = sol.cell_rects[0], sol.cell_rects[1]
        assert abs(r0.width() - sol.strip_rect.width() / 2) < 1e-6
        assert r0.top() == pytest.approx(r1.top())
        assert r0.height() == pytest.approx(r1.height())
        assert r0.height() >= 14.0

    # ── Wrap grows and pushes down (was TestSolver) ──────────────────────────

    def test_wrap_grows_and_pushes_down(self):
        long_val = "a very long project description " * 16
        f0 = FieldDef(id="p", name="Project", text="@[Project]")
        f1 = FieldDef(id="s", name="Stamp")
        lay = _lay3([f0, f1], [[Slot("p", 8.0)], [Slot("s", 20.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {"Project": long_val})
        assert sol.cell_rects[0].height() > 8.0
        assert sol.cell_rects[1].top() == pytest.approx(sol.cell_rects[0].bottom())

    # ── Overflow warning (was TestSolver) ─────────────────────────────────────

    def test_overflow_past_strip_bottom_warns(self):
        f0 = FieldDef(id="s0", name="S0")
        f1 = FieldDef(id="s1", name="S1")
        lay = _lay3([f0, f1], [[Slot("s0", 400.0)], [Slot("s1", 400.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert sol.warnings

    # ── Revision table (was TestSolver) ──────────────────────────────────────

    def test_revision_table_rows(self):
        f = FieldDef(id="rt", kind="revision_table", name="Revs", revision_rows=3)
        lay = _lay3([f], [[Slot("rt", 10.0)]])
        revs = [{"no": str(i), "description": f"rev {i}", "date": "07-21"}
                for i in range(5)]
        sol = solve_layout(lay, self.PW, self.PH, {"__revisions__": revs})
        assert sol.cell_revision_rows[0][0]["no"] == "4"
        assert len(sol.cell_revision_rows[0]) == 3

    # ── Cap height zero guard (was TestCapHeightCrashFix) ────────────────────

    def test_solve_does_not_raise_with_zero_cap_height(self):
        f = FieldDef(id="t", name="Title", text="@[Title]", cap_height_mm=0.0)
        lay = _lay3([f], [[Slot("t")]])
        sol = solve_layout(lay, self.PW, self.PH, {"Title": "Fire Protection Plan"})
        assert len(sol.cell_rects) == 1

    def test_validate_flags_zero_cap_height(self):
        f = FieldDef(id="t", name="Title", text="@[Title]", cap_height_mm=0.0)
        lay = _lay3([f], [[Slot("t")]])
        errs = validate(lay, self.PW, self.PH)
        assert any("cap height" in e.lower() for e in errs)

    def test_validate_flags_negative_cap_height(self):
        f = FieldDef(id="s", name="Stamp", cap_height_mm=-1.0)
        lay = _lay3([f], [[Slot("s")]])
        errs = validate(lay, self.PW, self.PH)
        assert any("cap height" in e.lower() for e in errs)

    # ── Min height floor (was TestMinHeightFloor) ─────────────────────────────

    def test_validate_flags_negative_min_height(self):
        f = FieldDef(id="s", name="Stamp")
        lay = _lay3([f], [[Slot("s", -5.0)]])
        errs = validate(lay, self.PW, self.PH)
        assert any("minimum height" in e.lower() for e in errs)

    def test_solve_clamps_negative_min_height_to_zero(self):
        f = FieldDef(id="s", name="Stamp")
        lay = _lay3([f], [[Slot("s", -5.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert sol.cell_rects[0].height() >= 0.0

    def test_validate_passes_zero_min_height(self):
        f = FieldDef(id="t", name="Title", text="@[Title]")
        lay = _lay3([f], [[Slot("t", 0.0)]])
        errs = validate(lay, self.PW, self.PH)
        assert not any("minimum height" in e.lower() for e in errs)

    # ── Fillet check (was TestFilletCheck) ───────────────────────────────────

    def test_large_strip_fillet_fails(self):
        f = FieldDef(id="t", name="Title", text="@[Title]")
        lay = _lay3([f], [[Slot("t")]])
        lay.strip_border = BorderStyle(corner="fillet", fillet_radius_mm=80.0)
        errs = validate(lay, self.PW, self.PH)
        assert any("fillet radius" in e.lower() for e in errs)

    def test_default_fillet_passes(self):
        f = FieldDef(id="t", name="Title", text="@[Title]")
        lay = _lay3([f], [[Slot("t")]])
        assert validate(lay, self.PW, self.PH) == []

    def test_sharp_corner_ignores_radius(self):
        f = FieldDef(id="t", name="Title", text="@[Title]")
        lay = _lay3([f], [[Slot("t")]])
        lay.strip_border = BorderStyle(corner="sharp", fillet_radius_mm=999.0)
        errs = validate(lay, self.PW, self.PH)
        assert not any("fillet radius" in e.lower() for e in errs)

    # ── Cell lines contract (was TestCellLinesContract) ───────────────────────

    def test_lines_join_equals_normalized_text(self):
        text = "  The quick brown fox jumps over  the lazy dog  "
        f = FieldDef(id="k", name="K", text="@[K]", cap_height_mm=3.0)
        lay = _lay3([f], [[Slot("k")]])
        sol = solve_layout(lay, self.PW, self.PH, {"K": text})
        lines = sol.cell_lines[0]
        assert " ".join(lines) == " ".join(text.split())

    def test_lines_fit_available_width(self):
        text = "word " * 40
        f = FieldDef(id="k", name="K", text="@[K]", cap_height_mm=3.0)
        lay = _lay3([f], [[Slot("k")]])
        sol = solve_layout(lay, self.PW, self.PH, {"K": text})
        lines = sol.cell_lines[0]
        font = _cell_font(f)
        fm = QFontMetricsF(font)
        cap_px = fm.capHeight() or 1.0
        px_per_mm = cap_px / max(f.cap_height_mm, 0.1)
        cw = sol.strip_rect.width()
        avail_px = max(1.0, (cw - 2 * TB_CELL_PAD_MM) * px_per_mm)
        for line in lines:
            if " " in line:
                assert fm.horizontalAdvance(line) <= avail_px + 1e-3

    def test_single_unbreakable_word_one_line(self):
        text = "A" * 200
        f = FieldDef(id="k", name="K", text="@[K]", cap_height_mm=3.0)
        lay = _lay3([f], [[Slot("k")]])
        sol = solve_layout(lay, self.PW, self.PH, {"K": text})
        assert len(sol.cell_lines[0]) == 1

    # ── Hard newlines (was TestHardNewlines) ──────────────────────────────────

    def test_hard_newline_yields_two_lines(self):
        f = FieldDef(id="t", name="Text", text="Line one\nLine two")
        lay = _lay3([f], [[Slot("t", 5.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        lines = sol.cell_lines[0]
        assert len(lines) >= 2
        assert lines[0].startswith("Line one")
        assert lines[1].startswith("Line two")

    def test_empty_paragraph_produces_empty_line(self):
        f = FieldDef(id="t", name="Text", text="a\n\nb")
        lay = _lay3([f], [[Slot("t", 5.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        lines = sol.cell_lines[0]
        assert len(lines) == 3
        assert lines[1] == ""

    # ── Dynamic pass DD-8b (was TestDynamicSolverPass) ───────────────────────

    def test_single_dynamic_stamp_fills_strip(self):
        f0 = FieldDef(id="ti", name="Title", text="@[Title]")
        f1 = FieldDef(id="st", name="Stamp")
        lay = _lay3([f0, f1],
                    [[Slot("ti", 20.0)], [Slot("st", 30.0, sizing="dynamic")]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert abs(sol.cell_rects[-1].bottom() - sol.strip_rect.bottom()) < 1e-6

    def test_two_dynamic_rows_proportional_distribution(self):
        f0 = FieldDef(id="s0", name="S0")
        f1 = FieldDef(id="s1", name="S1")
        lay = _lay3([f0, f1],
                    [[Slot("s0", 10.0, sizing="dynamic")],
                     [Slot("s1", 30.0, sizing="dynamic")]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert abs(sol.cell_rects[-1].bottom() - sol.strip_rect.bottom()) < 1e-6
        h0 = sol.cell_rects[0].height()
        h1 = sol.cell_rects[1].height()
        assert abs(h0 / h1 - 10.0 / 30.0) < 1e-3

    def test_zero_leftover_no_change(self):
        f0 = FieldDef(id="s0", name="S0")
        f1 = FieldDef(id="s1", name="S1")
        lay = _lay3([f0, f1],
                    [[Slot("s0", 400.0)], [Slot("s1", 400.0, sizing="dynamic")]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert sol.cell_rects[1].height() == pytest.approx(400.0)

    def test_no_dynamic_cells_unchanged(self):
        f0 = FieldDef(id="s0", name="S0")
        f1 = FieldDef(id="s1", name="S1")
        lay = _lay3([f0, f1], [[Slot("s0", 30.0)], [Slot("s1", 15.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert sol.cell_rects[0].height() == pytest.approx(30.0)
        assert sol.cell_rects[1].height() == pytest.approx(15.0)
        assert sol.cell_rects[-1].bottom() < sol.strip_rect.bottom() - 1.0

    def test_dynamic_paired_row_grows_as_one(self):
        f0 = FieldDef(id="sc", name="Scale", text="@[Scale]")
        f1 = FieldDef(id="dt", name="Date", text="@[Date]", )
        f2 = FieldDef(id="st", name="Stamp")
        lay = _lay3([f0, f1, f2],
                    [[Slot("sc", 10.0), Slot("dt", 10.0, sizing="dynamic")],
                     [Slot("st", 20.0)]])
        sol = solve_layout(lay, self.PW, self.PH, {})
        assert sol.cell_rects[0].height() == pytest.approx(sol.cell_rects[1].height())
        assert sol.cell_rects[2].height() == pytest.approx(20.0)
        assert abs(sol.cell_rects[-1].bottom() - sol.strip_rect.bottom()) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# TestValidateRev3 — rev-3 validate floors
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateRev3:
    def test_needs_one_placed_row(self):
        lay = _lay3([FieldDef(id="a", name="A")], [])
        assert any("placed" in e.lower()
                   for e in validate(lay, PAPER_W, PAPER_H))

    def test_empty_field_is_legal(self):
        lay = _lay3([FieldDef(id="a", name="Stamp")], [[Slot("a")]])
        assert validate(lay, PAPER_W, PAPER_H) == []

    def test_row_width_ceiling(self):
        fs = [FieldDef(id=i) for i in ("a", "b", "c")]
        lay = _lay3(fs, [[Slot("a"), Slot("b"), Slot("c")]])
        assert any("two" in e.lower() for e in validate(lay, PAPER_W, PAPER_H))

    def test_dangling_field_id_blocks(self):
        lay = _lay3([FieldDef(id="a")], [[Slot("a")], [Slot("ghost")]])
        assert any("missing field" in e.lower()
                   for e in validate(lay, PAPER_W, PAPER_H))

    def test_min_stack_must_fit(self):
        lay = _lay3([FieldDef(id="a")], [[Slot("a", 10_000.0)]])
        assert any("stack" in e.lower() for e in validate(lay, PAPER_W, PAPER_H))

    def test_revision_table_worst_case_in_stack(self):
        # 200 rev rows × row height blows the strip even with tiny min_height
        fs = [FieldDef(id="r", kind="revision_table", revision_rows=200)]
        lay = _lay3(fs, [[Slot("r", 1.0)]])
        assert any("stack" in e.lower() for e in validate(lay, PAPER_W, PAPER_H))

    def test_geometric_floors(self):
        base_fields = [FieldDef(id="a")]
        # negative margin
        lay = _lay3(base_fields, [[Slot("a")]], margin_edge_mm=-1.0)
        assert any("margin" in e.lower() for e in validate(lay, PAPER_W, PAPER_H))
        # strip width under floor
        lay = _lay3(base_fields, [[Slot("a")]], strip_width_mm=TB_STRIP_MIN_MM - 1)
        assert any("strip width" in e.lower()
                   for e in validate(lay, PAPER_W, PAPER_H))
        # drawing area squeezed under floor (huge strip)
        lay = _lay3(base_fields, [[Slot("a")]],
                    strip_width_mm=PAPER_W - 2 * 10.0 - TB_AREA_MIN_MM + 1)
        assert any("drawing area" in e.lower()
                   for e in validate(lay, PAPER_W, PAPER_H))

    def test_unplaced_field_bad_cap_blocks_save(self):
        # Deliberate decision (Task-5 review): cap>0 floor covers ALL fields,
        # including unplaced pool fields — a bad pool definition blocks Save.
        fs = [FieldDef(id="a"), FieldDef(id="pool", cap_height_mm=0.0)]
        lay = _lay3(fs, [[Slot("a")]])
        assert any("cap height" in e.lower()
                   for e in validate(lay, PAPER_W, PAPER_H))


class TestDisplayName:
    """TitleBlockTemplate.display_name property."""

    def test_landscape_native_no_suffix(self):
        t = TitleBlockTemplate(name="FirePro Default", uuid="u", modified="",
                               paper_size="ANSI D", orientation="landscape",
                               layout=TemplateLayout())
        assert t.display_name == "FirePro Default (ANSI D)"

    def test_portrait_native_no_suffix(self):
        t = TitleBlockTemplate(name="My A4", uuid="u", modified="",
                               paper_size="A4", orientation="portrait",
                               layout=TemplateLayout())
        assert t.display_name == "My A4 (A4)"

    def test_portrait_nonnative_appends_label(self):
        t = TitleBlockTemplate(name="FirePro Default", uuid="u", modified="",
                               paper_size="ANSI D", orientation="portrait",
                               layout=TemplateLayout())
        name = t.display_name
        assert "ANSI D" in name
        assert "Portrait" in name

    def test_landscape_nonnative_appends_label(self):
        t = TitleBlockTemplate(name="My A4", uuid="u", modified="",
                               paper_size="A4", orientation="landscape",
                               layout=TemplateLayout())
        name = t.display_name
        assert "A4" in name
        assert "Landscape" in name


class TestNativeOrientation:
    """native_orientation() helper covers all PAPER_SIZES entries."""

    def test_ansi_landscape(self):
        assert native_orientation("ANSI B") == "landscape"
        assert native_orientation("ANSI D") == "landscape"

    def test_iso_portrait(self):
        for size in ("A4", "A3", "A2", "A1", "A0"):
            assert native_orientation(size) == "portrait", size

    def test_letter_portrait(self):
        assert native_orientation("Letter") == "portrait"

    def test_d_size_portrait(self):
        assert native_orientation("D-size") == "portrait"

    def test_unknown_defaults_landscape(self):
        assert native_orientation("Unknown-X9") == "landscape"


class TestLibrary:
    def _tpl(self, uuid="u-lib", modified="2026-07-21"):
        f = FieldDef(id=new_field_id(), name="Title", text="@[Title]")
        layout = TemplateLayout(fields=[f], rows=[[Slot(f.id, 12.0)]])
        return TitleBlockTemplate(
            name="Lib", uuid=uuid, modified=modified,
            paper_size="ANSI D", orientation="landscape",
            layout=layout)

    def test_save_load_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = self._tpl()
        tbt.save_to_library(t)
        loaded = tbt.load_library()
        assert len(loaded) == 1 and loaded[0].uuid == "u-lib"

    def test_dir_created_on_first_use(self, tmp_path, monkeypatch):
        target = tmp_path / "sub" / "titleblocks"
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(target))
        tbt.save_to_library(self._tpl())
        assert target.exists()

    def test_corrupt_file_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        tbt.save_to_library(self._tpl())
        loaded = tbt.load_library()          # must not raise
        assert len(loaded) == 1

    def test_delete(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        tbt.save_to_library(self._tpl())
        tbt.delete_from_library("u-lib")
        assert tbt.load_library() == []

    def test_divergence(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        tbt.save_to_library(self._tpl(modified="2026-07-01"))
        embedded = self._tpl(modified="2026-07-21")
        assert tbt.library_diverges(embedded) is True
        tbt.save_to_library(embedded)
        assert tbt.library_diverges(embedded) is False
        assert tbt.library_diverges(self._tpl(uuid="unknown")) is False

    def test_corrupt_file_skipped_wrong_shape(self, tmp_path, monkeypatch):
        """Wrong-shape JSON (list not dict) must be skipped, not raise."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        (tmp_path / "wrongshape.json").write_text("[1, 2, 3]", encoding="utf-8")
        tbt.save_to_library(self._tpl())
        loaded = tbt.load_library()          # must not raise
        assert len(loaded) == 1

    def test_save_returns_path_and_file_exists(self, tmp_path, monkeypatch):
        """save_to_library returns the written path and the file must exist."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        returned = tbt.save_to_library(self._tpl())
        assert os.path.isfile(returned)

    def test_delete_absent_uuid_is_noop(self, tmp_path, monkeypatch):
        """Deleting a uuid that was never saved must not raise."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        tbt.delete_from_library("does-not-exist")  # must not raise

    def test_non_json_files_ignored(self, tmp_path, monkeypatch):
        """Non-.json files in the library dir are ignored by load_library."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        (tmp_path / "readme.txt").write_text("ignore me", encoding="utf-8")
        (tmp_path / "template.json.bak").write_text("{}", encoding="utf-8")
        tbt.save_to_library(self._tpl())
        loaded = tbt.load_library()
        assert len(loaded) == 1

    def test_save_evil_uuid_raises_value_error(self, tmp_path, monkeypatch):
        """A uuid with path separators must raise ValueError and write nothing."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        evil = self._tpl()
        evil.uuid = "..\\evil"
        with pytest.raises(ValueError):
            tbt.save_to_library(evil)
        assert list(tmp_path.iterdir()) == []

    def test_save_empty_uuid_raises_value_error(self, tmp_path, monkeypatch):
        """An empty uuid must raise ValueError."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        empty = self._tpl()
        empty.uuid = ""
        with pytest.raises(ValueError):
            tbt.save_to_library(empty)


class TestLegacyFieldsMigration:
    """migrate_legacy_fields — one-way project-field seeding (not cell migration)."""

    LEGACY = {"Company": "ACME Fire", "Project": "Plant 9",
              "Title": "L1 Plan", "Scale": "1:100", "Drawing No": "FP-1",
              "Rev": "A", "Date": "01 Jul 2026", "Drawn By": "GV",
              "Checked By": "JB"}

    def test_seeds_project_info_only_if_empty(self):
        info = {"name": ""}
        sheet_fields = dict(self.LEGACY)
        migrate_legacy_fields([sheet_fields], info)
        assert info["name"] == "Plant 9"
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "ACME Fire"
        assert custom["Drawn By"] == "GV"
        assert custom["Checked By"] == "JB"
        # sheet-scoped keys stay; Scale dropped (auto)
        assert sheet_fields["Title"] == "L1 Plan"
        assert "Scale" not in sheet_fields

    def test_idempotent_and_no_overwrite(self):
        info = {"name": "Existing", "custom": [
            {"key": "Company", "value": "Keep Me"}]}
        sheet_fields = dict(self.LEGACY)
        migrate_legacy_fields([sheet_fields], info)
        before = (copy.deepcopy(info), copy.deepcopy(sheet_fields))
        migrate_legacy_fields([sheet_fields], info)
        assert (dict(info), dict(sheet_fields)) == before
        assert info["name"] == "Existing"
        custom = {c["key"]: c["value"] for c in info["custom"]}
        assert custom["Company"] == "Keep Me"

    def test_empty_sheets_no_crash(self):
        info = {}
        migrate_legacy_fields([], info)
        migrate_legacy_fields([{}], info)
        assert "custom" not in info or info["custom"] == []

    # ── Multi-sheet / odd-input hardening (findings 1–2) ─────────────────────

    def test_two_sheets_different_company_first_wins(self):
        """First non-empty Company across sheets seeds; both sheets lose the key."""
        info = {}
        sheet1 = {"Company": "Alpha Fire", "Title": "S1"}
        sheet2 = {"Company": "Beta Fire", "Title": "S2"}
        migrate_legacy_fields([sheet1, sheet2], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "Alpha Fire"     # first non-empty wins
        assert "Company" not in sheet1
        assert "Company" not in sheet2

    def test_first_sheet_empty_company_second_sheet_seeds(self):
        """Empty first-sheet Company is skipped; second sheet's value seeds."""
        info = {}
        sheet1 = {"Company": "", "Title": "S1"}
        sheet2 = {"Company": "Gamma Fire", "Title": "S2"}
        migrate_legacy_fields([sheet1, sheet2], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "Gamma Fire"

    def test_none_company_skipped_no_crash(self):
        """Company=None must be skipped without error and must not seed."""
        info = {}
        sheet = {"Company": None, "Title": "S1"}
        migrate_legacy_fields([sheet], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert "Company" not in custom
        assert "Company" not in sheet          # still popped

    def test_int_company_seeds_as_str(self):
        """Company=123 (int) must be coerced to "123" and seed Project Info."""
        info = {}
        sheet = {"Company": 123, "Title": "S1"}
        migrate_legacy_fields([sheet], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "123"
        assert isinstance(custom["Company"], str)

    def test_skip_values_suppresses_shipped_default(self):
        """A Company matching skip_values is not treated as a donor; key still popped."""
        shipped_default = "Celerity Engineering Limited"
        info = {}
        sheet = {"Company": shipped_default, "Title": "S1"}
        migrate_legacy_fields(
            [sheet], info,
            skip_values={"Company": shipped_default},
        )
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert "Company" not in custom          # not seeded
        assert "Company" not in sheet           # but key was still popped


class TestResolveText:
    VALUES = {"Company": "Acme Fire", "Rev": "", "Scale": "1:100"}

    def test_substitutes_known_key(self):
        out, unknown = resolve_text("By @[Company]", self.VALUES)
        assert out == "By Acme Fire"
        assert unknown == []

    def test_known_empty_renders_empty(self):
        out, unknown = resolve_text("Rev @[Rev].", self.VALUES)
        assert out == "Rev ."
        assert unknown == []

    def test_unknown_key_stays_literal_and_reported(self):
        out, unknown = resolve_text("@[Drawnig No]", self.VALUES)
        assert out == "@[Drawnig No]"
        assert unknown == ["Drawnig No"]

    def test_multiple_tokens_and_multiline(self):
        out, unknown = resolve_text("@[Company]\n@[Scale] @[Nope]", self.VALUES)
        assert out == "Acme Fire\n1:100 @[Nope]"
        assert unknown == ["Nope"]

    def test_malformed_tokens_pass_through(self):
        for text in ("@[Unclosed", "@[]", "@[a@[b]]"):
            out, unknown = resolve_text(text, self.VALUES)
            assert "@[" in out
        assert resolve_text("@[]", self.VALUES) == ("@[]", [])

    def test_no_tokens_no_change(self):
        assert resolve_text("plain text", self.VALUES) == ("plain text", [])


# ─────────────────────────────────────────────────────────────────────────────
# TestRev3Model — rev-3 data model: FieldDef + Slot + rows (Task 2)
# ─────────────────────────────────────────────────────────────────────────────


class TestRev3Model:
    def _layout(self):
        f1 = FieldDef(id="f1", name="Company", text="@[Company]")
        f2 = FieldDef(id="f2", name="Stamp")            # empty field = stamp
        f3 = FieldDef(id="f3", name="Spare", text="unplaced")
        return TemplateLayout(
            fields=[f1, f2, f3],
            rows=[[Slot("f1", 12.0)], [Slot("f2", 60.0, sizing="dynamic")]],
        )

    def test_round_trip(self):
        lay = self._layout()
        again = TemplateLayout.from_dict(lay.to_dict())
        assert again.to_dict() == lay.to_dict()

    def test_pool_and_placed(self):
        lay = self._layout()
        assert lay.placed_ids() == {"f1", "f2"}
        assert [f.id for f in lay.pool_fields()] == ["f3"]

    def test_field_map(self):
        lay = self._layout()
        assert lay.field_map()["f1"].name == "Company"

    def test_unknown_keys_ignored_on_load(self):
        d = self._layout().to_dict()
        d["future_thing"] = 1
        d["fields"][0]["future_prop"] = "x"
        d["rows"][0][0]["future_slot_prop"] = 2
        TemplateLayout.from_dict(d)      # must not raise

    def test_new_field_id_unique(self):
        assert new_field_id() != new_field_id()

    def test_image_position_reserved_default(self):
        assert FieldDef(id="x").image_position == "top"


# ─────────────────────────────────────────────────────────────────────────────
# TestMigration — rev-2 cells[] → rev-3 fields/rows migration (Task 3)
# ─────────────────────────────────────────────────────────────────────────────


class TestMigration:
    def _old(self, **kw):
        base = {"kind": "field", "field_key": "", "label": "", "static_text": "",
                "min_height_mm": 10.0, "sizing": "static",
                "pair_with_next": False, "font_family": "Arial",
                "cap_height_mm": 3.0, "bold": True, "italic": False,
                "alignment": "left", "fill_color": "",
                "border": {}, "logo_data": "", "logo_fit": "contain",
                "revision_rows": 3}
        base.update(kw)
        return base

    def test_field_key_becomes_token(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(field_key="Company", label="Company")]})
        f = lay.fields[0]
        assert f.text == "@[Company]"
        assert f.name == "Company"
        assert len(lay.rows) == 1 and lay.rows[0][0].field_id == f.id

    def test_static_text_becomes_text(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="static_text", static_text="Hello\nWorld")]})
        assert lay.fields[0].text == "Hello\nWorld"

    def test_logo_becomes_image_field(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="logo", logo_data="AAAA", min_height_mm=25.0)]})
        f = lay.fields[0]
        assert f.kind == "field" and f.image_data == "AAAA" and f.text == ""
        assert f.name == "Logo"
        assert lay.rows[0][0].min_height_mm == 25.0

    def test_stamp_becomes_empty_field(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="stamp", sizing="dynamic", min_height_mm=60.0)]})
        f = lay.fields[0]
        assert (f.kind, f.text, f.image_data) == ("field", "", "")
        assert f.name == "Stamp"
        assert lay.rows[0][0].sizing == "dynamic"

    def test_pair_chain_becomes_two_slot_row(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(field_key="Scale", pair_with_next=True),
            self._old(field_key="Date"),
            self._old(field_key="Title")]})
        assert [len(r) for r in lay.rows] == [2, 1]

    def test_names_deduped(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="logo"), self._old(kind="logo")]})
        assert [f.name for f in lay.fields] == ["Logo", "Logo 2"]

    def test_idempotent_and_one_way(self):
        old = {"cells": [self._old(field_key="Company", label="Company",
                                   pair_with_next=True),
                         self._old(field_key="Project")]}
        lay = TemplateLayout.from_dict(old)
        d = lay.to_dict()
        assert "cells" not in d
        assert TemplateLayout.from_dict(d).to_dict() == d

    def test_default_template_is_rev3_native(self):
        t = make_default_template()
        assert t.layout.fields and t.layout.rows
        assert "cells" not in t.layout.to_dict()
        stamp_slot = t.layout.rows[-1][0]
        assert stamp_slot.sizing == "dynamic"
        assert any(f.kind == "revision_table" for f in t.layout.fields)
        from firepro3d.titleblock_template import DEFAULT_SEED_MODIFIED
        assert DEFAULT_SEED_MODIFIED > "2026-07-22"

    def test_variants_era_chains_through(self):
        old_rev1 = {"name": "Old", "uuid": "u1", "modified": "2026-07-21",
                    "variants": {"ANSI D": {
                        "strip_width_mm": 90.0,
                        "cells": [self._old(field_key="Title")]}}}
        t = TitleBlockTemplate.from_dict(old_rev1)
        assert t.layout.fields[0].text == "@[Title]"

    # Coercion coverage carried over from Task-2 review:
    def test_kind_fallback_on_load(self):
        f = FieldDef.from_dict({"id": "x", "kind": "banana"})
        assert f.kind == "field"

    def test_sizing_fallback_on_load(self):
        s = Slot.from_dict({"field_id": "x", "sizing": "banana"})
        assert s.sizing == "static"

    def test_missing_id_regenerated(self):
        f = FieldDef.from_dict({"name": "n"})
        assert f.id

    def test_trailing_pair_flag_single_row(self):
        """pair_with_next=True on the LAST cell migrates to a single row, no crash."""
        lay = TemplateLayout.from_dict({"cells": [
            self._old(field_key="Title", pair_with_next=True)]})
        assert len(lay.rows) == 1
        assert len(lay.rows[0]) == 1
        assert lay.fields[0].text == "@[Title]"


# ─────────────────────────────────────────────────────────────────────────────
# TestRev2RenderParity — frozen rev-2 seeded default (regression fixture)
# ─────────────────────────────────────────────────────────────────────────────

#: Verbatim serialization of the rev-2 seeded default template, as produced by
#: ``make_default_template().to_dict()`` at commit 23fa804 (the last rev-2
#: HEAD), with the random uuid pinned to ``"rev2-fixture-uuid"``.  DO NOT
#: regenerate from current code — this literal is the frozen rev-2 on-disk
#: shape that .fpd embeds and library JSONs from that era contain.
#: Also imported by the .fpd embed regression in tests/test_titleblock_render.py.
REV2_DEFAULT_TEMPLATE_DICT = {
    'name': 'FirePro Default',
    'uuid': 'rev2-fixture-uuid',
    'modified': '2026-07-22',
    'paper_size': 'ANSI D',
    'orientation': 'landscape',
    'layout': {
        'margin_edge_mm': 10.0,
        'margin_strip_mm': 5.0,
        'strip_width_mm': 90.0,
        'strip_edge': 'right',
        'area_border': {'visible': True, 'width_mm': 0.5, 'color': '#000000',
                        'corner': 'fillet', 'fillet_radius_mm': 10.0},
        'strip_border': {'visible': True, 'width_mm': 0.5, 'color': '#000000',
                         'corner': 'fillet', 'fillet_radius_mm': 10.0},
        'cells': [
            {'kind': 'logo', 'field_key': '', 'label': '', 'static_text': '',
             'min_height_mm': 25.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 3.0, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Company', 'label': 'Company',
             'static_text': '', 'min_height_mm': 12.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 2.6, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '#eef2f7',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Project', 'label': 'Project',
             'static_text': '', 'min_height_mm': 12.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 2.6, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Address', 'label': 'Address',
             'static_text': '', 'min_height_mm': 10.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 2.6, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Title', 'label': 'Sheet Title',
             'static_text': '', 'min_height_mm': 14.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 3.2, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Scale', 'label': 'Scale',
             'static_text': '', 'min_height_mm': 10.0, 'sizing': 'static',
             'pair_with_next': True, 'font_family': 'Arial',
             'cap_height_mm': 2.6, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Date', 'label': 'Date',
             'static_text': '', 'min_height_mm': 10.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 2.6, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Drawn By', 'label': 'Drawn',
             'static_text': '', 'min_height_mm': 10.0, 'sizing': 'static',
             'pair_with_next': True, 'font_family': 'Arial',
             'cap_height_mm': 2.6, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Checked By', 'label': 'Checked',
             'static_text': '', 'min_height_mm': 10.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 2.6, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Drawing No', 'label': 'Drawing No',
             'static_text': '', 'min_height_mm': 14.0, 'sizing': 'static',
             'pair_with_next': True, 'font_family': 'Arial',
             'cap_height_mm': 4.0, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '#eef2f7',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'field', 'field_key': 'Rev', 'label': 'Rev',
             'static_text': '', 'min_height_mm': 14.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 4.0, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'revision_table', 'field_key': '', 'label': 'Revisions',
             'static_text': '', 'min_height_mm': 25.0, 'sizing': 'static',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 3.0, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
            {'kind': 'stamp', 'field_key': '', 'label': '', 'static_text': '',
             'min_height_mm': 60.0, 'sizing': 'dynamic',
             'pair_with_next': False, 'font_family': 'Arial',
             'cap_height_mm': 3.0, 'bold': True, 'italic': False,
             'alignment': 'left', 'fill_color': '',
             'border': {'visible': True, 'width_mm': 0.3, 'color': '#000000',
                        'corner': 'sharp', 'fillet_radius_mm': 0.0},
             'logo_data': '', 'logo_fit': 'contain', 'revision_rows': 3},
        ],
    },
}


class TestRev2RenderParity:
    """The frozen rev-2 seeded default must migrate and solve with rev-2 geometry."""

    def _migrated(self) -> TitleBlockTemplate:
        return TitleBlockTemplate.from_dict(
            copy.deepcopy(REV2_DEFAULT_TEMPLATE_DICT))

    def _solve(self, t):
        return solve_layout(t.layout, 863.6, 558.8,
                            {"Company": "Acme", "Title": "Plan"})

    def test_migrates_to_13_fields_10_rows(self):
        t = self._migrated()
        assert t.paper_size == "ANSI D"
        assert t.orientation == "landscape"
        assert len(t.layout.fields) == 13
        assert [len(r) for r in t.layout.rows] == [1, 1, 1, 1, 1, 2, 2, 2, 1, 1]

    def test_solves_with_rev2_geometry(self):
        sol = self._solve(self._migrated())
        assert len(sol.cell_rects) == 13
        assert [n for _f, n in sol.row_spans] == [1, 1, 1, 1, 1, 2, 2, 2, 1, 1]
        # Dynamic stamp: last cell fills to the strip bottom, as in rev 2.
        assert abs(sol.cell_rects[-1].bottom() - sol.strip_rect.bottom()) < 1e-6

    def test_company_cell_token_parity(self):
        """field_key="Company" migrates to "@[Company]" and resolves to the
        same rendered line the rev-2 field_key lookup produced."""
        t = self._migrated()
        sol = self._solve(t)
        company = next(f for f in t.layout.fields if f.name == "Company")
        assert company.text == "@[Company]"
        idx = sol.cell_field_ids.index(company.id)
        assert sol.cell_lines[idx] == ["Acme"]


class TestArrangementOps:
    def _lay(self):
        fs = [FieldDef(id=i, name=i) for i in ("a", "b", "c", "d")]
        return TemplateLayout(fields=fs,
                              rows=[[Slot("a")], [Slot("b"), Slot("c")]])

    def test_place_from_pool(self):
        lay = self._lay()
        place_field(lay, "d", 1)
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["a"], ["d"], ["b", "c"]]

    def test_place_already_placed_moves_it(self):
        lay = self._lay()
        place_field(lay, "a", 2)          # indexes AFTER removal
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["b", "c"], ["a"]]

    def test_place_unknown_field_noop(self):
        lay = self._lay()
        place_field(lay, "ghost", 0)
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["a"], ["b", "c"]]

    def test_place_index_clamped(self):
        lay = self._lay()
        place_field(lay, "d", 99)
        assert [s.field_id for s in lay.rows[-1]] == ["d"]
        lay2 = self._lay()
        place_field(lay2, "d", -5)
        assert [s.field_id for s in lay2.rows[0]] == ["d"]

    def test_unplace_keeps_definition(self):
        lay = self._lay()
        unplace_field(lay, "b")
        assert [[s.field_id for s in r] for r in lay.rows] == [["a"], ["c"]]
        assert "b" in {f.id for f in lay.fields}

    def test_unplace_last_of_row_drops_row(self):
        lay = self._lay()
        unplace_field(lay, "a")
        assert [[s.field_id for s in r] for r in lay.rows] == [["b", "c"]]

    def test_unplace_unplaced_noop(self):
        lay = self._lay()
        unplace_field(lay, "d")
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["a"], ["b", "c"]]

    def test_move_reorders(self):
        lay = self._lay()
        move_field(lay, "a", 2)           # insertion index after removal
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["b", "c"], ["a"]]

    def test_move_out_of_pair_unpairs(self):
        lay = self._lay()
        move_field(lay, "c", 0)
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["c"], ["a"], ["b"]]

    def test_pair_onto_single_row(self):
        lay = self._lay()
        pair_field(lay, "d", 0, "right")
        assert [s.field_id for s in lay.rows[0]] == ["a", "d"]
        pair2 = self._lay()
        pair_field(pair2, "d", 0, "left")
        assert [s.field_id for s in pair2.rows[0]] == ["d", "a"]

    def test_pair_swap_sides_with_partner(self):
        lay = self._lay()
        pair_field(lay, "b", 1, "right")   # b drops on its own row -> swap
        assert [s.field_id for s in lay.rows[1]] == ["c", "b"]

    def test_pair_onto_full_row_is_noop(self):
        lay = self._lay()
        pair_field(lay, "d", 1, "left")    # row 1 already has 2 others
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["a"], ["b", "c"]]

    def test_pair_from_row_above_target(self):
        fs = [FieldDef(id=i, name=i) for i in ("a", "b", "c")]
        lay = TemplateLayout(fields=fs,
                             rows=[[Slot("a")], [Slot("b")], [Slot("c")]])
        # pair "a" (its own row 0 disappears) into what WAS row 1 ("b")
        pair_field(lay, "a", 1, "right")
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["b", "a"], ["c"]]

    def test_pair_unknown_field_noop(self):
        lay = self._lay()
        pair_field(lay, "ghost", 0, "left")
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["a"], ["b", "c"]]

    def test_pair_bad_row_index_noop(self):
        lay = self._lay()
        pair_field(lay, "d", 99, "left")
        assert [[s.field_id for s in r] for r in lay.rows] == [
            ["a"], ["b", "c"]]

    def test_ops_preserve_slot_props(self):
        lay = TemplateLayout(fields=[FieldDef(id="a")],
                             rows=[[Slot("a", 33.0, sizing="dynamic")]])
        move_field(lay, "a", 0)
        assert (lay.rows[0][0].min_height_mm,
                lay.rows[0][0].sizing) == (33.0, "dynamic")

    def test_pair_own_half_is_noop(self):
        lay = self._lay()                  # rows [["a"], ["b","c"]]
        pair_field(lay, "b", 1, "left")    # b already on the left
        assert [s.field_id for s in lay.rows[1]] == ["b", "c"]

    def test_pair_own_single_row_is_noop(self):
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 33.0)], [Slot("b")]])
        pair_field(lay, "a", 0, "right")
        assert [[s.field_id for s in r] for r in lay.rows] == [["a"], ["b"]]
        assert lay.rows[0][0].min_height_mm == 33.0
