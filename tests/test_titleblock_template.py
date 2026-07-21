"""Tests for the parametric title block template system (data + solver + I/O)."""
import copy

from firepro3d.titleblock_template import (
    BorderStyle, CellSpec, TemplateVariant, TitleBlockTemplate,
)


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
