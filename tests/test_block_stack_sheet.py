"""A schematic's stacking on a sheet, in a PDF and across save (D1, D3, D14)."""
import fitz
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_export import export_pdf
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from firepro3d.schematic_scene import SchematicSceneManager
from tests._block_stack_helpers import line_def, rect_def


class _PlanStub:
    _views: dict = {}

    def get(self, name):
        return None


class _DetailStub:
    detail_names: list = []

    def get_marker(self, name):
        return None


def _rec(d, x, y, **kw):
    return {"type": "block_instance", "block_id": d.id, "pos": [x, y],
            "rotation": 0.0, **kw}


def _env(top_extra):
    proj = Model_Space()
    low, top = line_def(proj, "Low", 400.0), rect_def(proj, "Top", 200.0, 200.0)
    sch = BlockDefinition.new(name="Riser", library="", series="", origin=(0.0, 0.0), primitives=[
        LineItem(QPointF(0, 140), QPointF(400, 140)).to_dict(),
        _rec(low, 0, 0), _rec(top, 100, -100, **top_extra)], kind="schematic")
    proj.register_block_definition(sch)
    mgr = SchematicSceneManager(proj)
    res = ViewResolver(proj, _PlanStub(), _DetailStub(), None, schematic_scenes=mgr)
    sheet = Sheet.create_default()
    proj._sheets = [sheet]
    ps = PaperScene(sheet, res)
    ps.add_viewport(SheetViewData("schematic", sch.id, "", 0.0, 100.0, 100.0, 104.0, 54.0))
    return proj, sheet, res


def _pdf_ink(path) -> int:
    px = fitz.open(str(path))[0].get_pixmap(dpi=200)
    s, n = px.samples, px.n
    return sum(1 for i in range(0, len(s), n) if s[i] < 128)


def test_an_existing_schematic_exports_opaque_with_no_save(qapp, tmp_path):
    _p, sheet, res = _env({})                                    # no opaque key at all
    export_pdf([sheet], res, str(tmp_path / "default.pdf"))
    _p, sheet, res = _env({"opaque": False})
    export_pdf([sheet], res, str(tmp_path / "through.pdf"))
    assert _pdf_ink(tmp_path / "default.pdf") < _pdf_ink(tmp_path / "through.pdf")


def test_a_saved_project_keeps_the_keys(qapp, tmp_path):
    proj, _s, _r = _env({"opaque": False, "layer_height": 3, "constraint_points_off": True})
    path = tmp_path / "p.fpd"
    proj.save_to_file(str(path), backup=False)
    other = Model_Space()
    other.load_from_file(str(path))
    sch = next(d for d in other._block_definitions.values() if d.kind == "schematic")
    rec = next(r for r in sch.primitives if r.get("layer_height") == 3)
    assert rec["opaque"] is False and rec["constraint_points_off"] is True
