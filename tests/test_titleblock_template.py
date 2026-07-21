"""Tests for the parametric title block template system (data + solver + I/O)."""
import copy

from PyQt6.QtWidgets import QApplication

from firepro3d.titleblock_template import (
    BorderStyle, CellSpec, TemplateVariant, TitleBlockTemplate,
    solve_layout, validate,
)

_app = QApplication.instance() or QApplication([])


class TestSerialization:
    def _template(self):
        cell = CellSpec(kind="field", field_key="Title", label="Sheet Title",
                        min_height_mm=12.0, fill_color="#eef2f7")
        var = TemplateVariant(paper_size="ANSI D", cells=[cell])
        return TitleBlockTemplate(name="Test", uuid="u-1",
                                  modified="2026-07-21",
                                  variants={"ANSI D": var})

    def test_round_trip(self):
        t = self._template()
        t2 = TitleBlockTemplate.from_dict(t.to_dict())
        assert t2.to_dict() == t.to_dict()
        assert t2.variants["ANSI D"].cells[0].field_key == "Title"
        assert t2.variants["ANSI D"].cells[0].border.corner in ("sharp", "fillet")

    def test_unknown_keys_ignored(self):
        d = self._template().to_dict()
        d["future_field"] = 42
        d["variants"]["ANSI D"]["cells"][0]["mystery"] = "x"
        t2 = TitleBlockTemplate.from_dict(d)   # must not raise
        assert t2.name == "Test"

    def test_defaults(self):
        c = CellSpec(kind="stamp")
        assert c.pair_with_next is False
        assert c.border.visible is True
        b = BorderStyle()
        assert b.corner == "fillet" and b.fillet_radius_mm == 10.0
        v = TemplateVariant(paper_size="ANSI B")
        assert v.strip_edge == "right"

    def test_deep_copy_independent(self):
        t = self._template()
        t2 = t.copy()
        t2.variants["ANSI D"].cells[0].label = "changed"
        assert t.variants["ANSI D"].cells[0].label == "Sheet Title"
        assert t2.to_dict() != t.to_dict()


def _variant(cells, strip=90.0):
    return TemplateVariant(paper_size="ANSI D", strip_width_mm=strip,
                           cells=cells)


class TestSolver:
    PW, PH = 863.6, 558.8   # ANSI D landscape

    def test_area_and_strip_rects(self):
        v = _variant([CellSpec(kind="stamp", min_height_mm=20)])
        sl = solve_layout(v, self.PW, self.PH, {})
        # strip: right edge, inside 10mm margins
        assert sl.strip_rect.right() == self.PW - v.margin_edge_mm
        assert sl.strip_rect.width() == v.strip_width_mm
        # drawing area stops margin_strip before the strip
        assert sl.area_rect.right() == sl.strip_rect.left() - v.margin_strip_mm
        assert sl.area_rect.left() == v.margin_edge_mm

    def test_stack_positions_and_min_heights(self):
        cells = [CellSpec(kind="stamp", min_height_mm=30),
                 CellSpec(kind="stamp", min_height_mm=15)]
        sl = solve_layout(_variant(cells), self.PW, self.PH, {})
        r0, r1 = sl.cell_rects[0], sl.cell_rects[1]
        assert r0.top() == sl.strip_rect.top()
        assert r0.height() == 30
        assert r1.top() == r0.bottom()
        assert r1.height() == 15

    def test_pairing_half_width_row_height_max(self):
        cells = [CellSpec(kind="field", field_key="Scale", min_height_mm=10,
                          pair_with_next=True),
                 CellSpec(kind="field", field_key="Date", min_height_mm=14)]
        sl = solve_layout(_variant(cells), self.PW, self.PH,
                          {"Scale": "1:100", "Date": "2026-07-21"})
        r0, r1 = sl.cell_rects[0], sl.cell_rects[1]
        assert abs(r0.width() - sl.strip_rect.width() / 2) < 1e-6
        assert r0.top() == r1.top()
        assert r0.height() == r1.height() == 14   # max of pair

    def test_wrap_grows_and_pushes_down(self):
        long_val = "a very long project description " * 16
        cells = [CellSpec(kind="field", field_key="Project", min_height_mm=8),
                 CellSpec(kind="stamp", min_height_mm=20)]
        sl = solve_layout(_variant(cells), self.PW, self.PH,
                          {"Project": long_val})
        assert sl.cell_rects[0].height() > 8            # grew, text kept size
        assert sl.cell_rects[1].top() == sl.cell_rects[0].bottom()  # pushed

    def test_overflow_past_strip_bottom_warns(self):
        cells = [CellSpec(kind="stamp", min_height_mm=400),
                 CellSpec(kind="stamp", min_height_mm=400)]
        sl = solve_layout(_variant(cells), self.PW, self.PH, {})
        assert sl.warnings                                # clipped + warned

    def test_revision_table_rows(self):
        cells = [CellSpec(kind="revision_table", revision_rows=3,
                          min_height_mm=10)]
        revs = [{"no": str(i), "description": f"rev {i}", "date": "07-21"}
                for i in range(5)]
        sl = solve_layout(_variant(cells), self.PW, self.PH,
                          {"__revisions__": revs})
        assert sl.cell_revision_rows[0][0]["no"] == "4"   # newest first
        assert len(sl.cell_revision_rows[0]) == 3         # capped


class TestValidate:
    def test_valid_default(self):
        v = _variant([CellSpec(kind="field", field_key="Title")])
        assert validate(v, 863.6, 558.8) == []

    def test_floors(self):
        v = _variant([CellSpec(kind="field", field_key="Title")], strip=5.0)
        assert any("strip" in w.lower() for w in validate(v, 863.6, 558.8))
        v2 = _variant([CellSpec(kind="field", field_key="Title")])
        v2.margin_edge_mm = -1
        assert validate(v2, 863.6, 558.8)
        v3 = _variant([])
        assert any("cell" in w.lower() for w in validate(v3, 863.6, 558.8))
        v4 = _variant([CellSpec(kind="field", field_key="")])
        assert any("field key" in w.lower() for w in validate(v4, 863.6, 558.8))
        # drawing area floor: Letter portrait is 215.9 wide; 120mm strip leaves <100
        v5 = _variant([CellSpec(kind="field", field_key="Title")], strip=120.0)
        assert any("drawing area" in w.lower()
                   for w in validate(v5, 215.9, 279.4))

    def test_minimum_stack_must_fit(self):
        v = _variant([CellSpec(kind="stamp", min_height_mm=600)])
        assert any("fit" in w.lower() for w in validate(v, 863.6, 558.8))
