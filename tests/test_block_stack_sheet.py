"""A schematic's stacking on a sheet, in a PDF and across save (D1, D3, D14)."""
import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_export import export_pdf
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from firepro3d.schematic_scene import SchematicSceneManager
from tests._block_stack_helpers import line_def, rect_def


class _PlanStub:
    _views: dict = {}

    def get(self, name):
        return None


class _Plan:
    level_name = "Level 1"
    view_height = 3000.0
    view_depth = -300.0


class _PlanViewStub:
    _views: dict = {}

    def get(self, name):
        return _Plan()


class _DetailStub:
    detail_names: list = []

    def get_marker(self, name):
        return None


def _rec(d, x, y, **kw):
    return {"type": "block_instance", "block_id": d.id, "pos": [x, y],
            "rotation": 0.0, **kw}


def _env(top_extra, loose=(), low=True):
    """*loose*: extra loose primitive records; *low*: the lower block's line."""
    proj = Model_Space()
    low_def, top = line_def(proj, "Low", 400.0), rect_def(proj, "Top", 200.0, 200.0)
    prims = [LineItem(QPointF(0, 140), QPointF(400, 140)).to_dict()]
    prims += list(loose)
    if low:
        prims.append(_rec(low_def, 0, 0))
    prims.append(_rec(top, 100, -100, **top_extra))
    sch = BlockDefinition.new(name="Riser", library="", series="", origin=(0.0, 0.0),
                              primitives=prims, kind="schematic")
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


def _dark_rows(path):
    """Per pixel row of page 1 at 200 dpi, the sorted dark-pixel columns."""
    px = fitz.open(str(path))[0].get_pixmap(dpi=200)
    s, n, w = px.samples, px.n, px.width
    return [[x for x in range(w) if s[(y * w + x) * n] < 128] for y in range(px.height)]


def _runs(xs):
    out = []
    for x in xs:
        if out and x == out[-1][1] + 1:
            out[-1][1] = x
        else:
            out.append([x, x])
    return out


def _assert_middle_hidden(default_pdf, through_pdf):
    """The 400 mm line runs under the 200 mm block (x 100..300): in the default
    export its middle half is hidden and both outer quarters stay (spatial, not
    total); with the block see-through the whole line shows."""
    dflt, thru = _dark_rows(default_pdf), _dark_rows(through_pdf)
    changed = [y for y in range(len(dflt)) if set(dflt[y]) != set(thru[y])]
    assert changed, "opaque and through-view PDFs are identical"
    y = max(changed, key=lambda r: len(set(dflt[r]) ^ set(thru[r])))   # the row the line is on
    line = max(_runs(thru[y]), key=lambda r: r[1] - r[0])        # the line's full run
    lo, hi = line
    span = hi - lo
    q1, q3 = lo + span * 0.25, lo + span * 0.75
    margin = span * 0.05                                        # stroke width and rounding
    shown = set(dflt[y])
    assert all(x in shown for x in range(lo, int(q1 - margin)))         # left outer quarter
    assert all(x in shown for x in range(int(q3 + margin), hi + 1))     # right outer quarter
    assert not any(x in shown for x in range(int(q1 + margin), int(q3 - margin)))
    assert all(x in set(thru[y]) for x in range(int(q1 + margin), int(q3 - margin)))


def test_an_existing_schematic_exports_opaque_with_no_save(qapp, tmp_path):
    _p, sheet, res = _env({})                                    # no opaque key at all
    export_pdf([sheet], res, str(tmp_path / "default.pdf"))
    _p, sheet, res = _env({"opaque": False})
    export_pdf([sheet], res, str(tmp_path / "through.pdf"))
    assert _pdf_ink(tmp_path / "default.pdf") < _pdf_ink(tmp_path / "through.pdf")
    _assert_middle_hidden(tmp_path / "default.pdf", tmp_path / "through.pdf")


def test_a_loose_line_under_an_opaque_block_is_hidden_through_a_viewport_and_in_a_pdf(qapp, tmp_path):
    """Smoke R2: the loose line along y 0 has no lower block under the Top
    block here, so any ink missing in the middle is the loose line hidden."""
    loose = [LineItem(QPointF(0, 0), QPointF(400, 0)).to_dict()]
    _p, sheet, res = _env({}, loose=loose, low=False)
    export_pdf([sheet], res, str(tmp_path / "default.pdf"))
    _p, sheet, res = _env({"opaque": False}, loose=loose, low=False)
    export_pdf([sheet], res, str(tmp_path / "through.pdf"))
    _assert_middle_hidden(tmp_path / "default.pdf", tmp_path / "through.pdf")


def _plan_pdf(path, opaque=True):
    """A Fixed-size (paper-scaled) block with a lower line and an upper square
    nested in it, placed in a plan and shown through a sheet plan viewport."""
    ms = Model_Space(scene_role="plan")
    lower = BlockDefinition.new(name="Low", library="L", series="S", origin=(0.0, 0.0),
                                primitives=[LineItem(QPointF(-30, 0), QPointF(30, 0)).to_dict()])
    upper = BlockDefinition.new(name="Top", library="L", series="S", origin=(0.0, 0.0),
                                primitives=[RectangleItem(QPointF(-10, -10),
                                                          QPointF(10, 10)).to_dict()])
    ms.register_block_definition(lower)
    ms.register_block_definition(upper)
    parent = BlockDefinition.new(
        name="P", library="L", series="S", origin=(0.0, 0.0),
        primitives=[_rec(lower, 0, 0), _rec(upper, 0, 0, opaque=opaque, layer_height=1)])
    parent.scale_mode = "annotative"
    parent.annotative_screen = "fixed"
    ms.register_block_definition(parent)
    ms.place_block_instance(parent.id, (0.0, 0.0), level=ms.active_level)
    res = ViewResolver(ms, _PlanViewStub(), _DetailStub(), None)
    sheet = Sheet.create_default()
    ms._sheets = [sheet]
    ps = PaperScene(sheet, res)
    # 1:10 -> 0.1 paper mm per model mm; crop 1000 model mm = the 100 mm box.
    view = SheetViewData("plan", "Plan: Level 1", "", 0.1, 100.0, 100.0, 100.0, 100.0)
    view.crop_rect = QRectF(-500.0, -500.0, 1000.0, 1000.0)
    ps.add_viewport(view)
    export_pdf([sheet], res, str(path))
    return ms


def test_a_fixed_size_block_in_a_plan_viewport_hides_only_the_lower_ink_under_it(qapp, tmp_path):
    """Hand geometry. The crop is centred on the model origin, so the block
    sits at the viewport centre: sheet (100+50, 100+50) mm = (150, 150) mm.
    Fixed size prints at its authored mm: lower line x 120..180 mm, upper
    square +-10 mm. At 200 dpi (200/25.4 = 7.874 px/mm): centre column 1181.1,
    line columns 944.9..1417.3, hidden half-width 78.7 -> hidden columns
    1102.4..1259.8; the line's row is 1181.1."""
    ms = _plan_pdf(tmp_path / "default.pdf")
    _plan_pdf(tmp_path / "through.pdf", opaque=False)
    rows = range(1179, 1184)

    def cols(name):
        r = _dark_rows(tmp_path / name)
        return {x for y in rows for x in r[y]}

    dflt, thru = cols("default.pdf"), cols("through.pdf")
    # positive control: the viewport really shows the lower line, end to end
    assert all(x in thru for x in range(950, 1411)), "the plan viewport shows no lower line"
    # outside the mask the lower ink survives; inside it is gone (margin 8 px
    # keeps the square's own edges, columns 1102 and 1259, out of the test)
    assert all(x in dflt for x in range(950, 1095))
    assert all(x in dflt for x in range(1267, 1411))
    assert not any(x in dflt for x in range(1110, 1252))
    ms.cleanup()


def test_a_saved_project_keeps_the_keys(qapp, tmp_path):
    proj, _s, _r = _env({"opaque": False, "layer_height": 3, "constraint_points_off": True})
    path = tmp_path / "p.fpd"
    proj.save_to_file(str(path), backup=False)
    other = Model_Space()
    other.load_from_file(str(path))
    sch = next(d for d in other._block_definitions.values() if d.kind == "schematic")
    rec = next(r for r in sch.primitives if r.get("layer_height") == 3)
    assert rec["opaque"] is False and rec["constraint_points_off"] is True
