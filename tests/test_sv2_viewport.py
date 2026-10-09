"""SV2 Tasks 4-5 -- resolver branch + schematic SheetViewport rules
(schematics.md D-S7 / D-S10 + SV2 delta)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import (PaperScene, Sheet, SheetViewData,
                                   ViewportProperties, ViewResolver)


class _PlanStub:
    _views: dict = {}

    def get(self, name):
        return None


class _DetailStub:
    detail_names: list = []

    def get_marker(self, name):
        return None


def _prims(sym_id, length=100.0):
    return [LineItem(QPointF(0, 0), QPointF(length, 0)).to_dict(),
            {"type": "block_instance", "block_id": sym_id,
             "pos": [50.0, 10.0], "rotation": 0.0}]


@pytest.fixture
def env(qapp):
    from firepro3d.schematic_scene import SchematicSceneManager
    proj = Model_Space()
    sym = BlockDefinition.new(
        name="Sym", library="L", series="S",
        primitives=[LineItem(QPointF(0, 0), QPointF(0, 40)).to_dict()],
        origin=(0.0, 0.0))
    proj.register_block_definition(sym)
    proj.push_undo_state()
    sch = BlockDefinition.new(name="Riser", library="", series="",
                              primitives=_prims(sym.id), origin=(0.0, 0.0),
                              kind="schematic")
    proj.register_block_definition(sch)
    proj.push_undo_state()
    mgr = SchematicSceneManager(proj)
    resolver = ViewResolver(proj, _PlanStub(), _DetailStub(), None,
                            schematic_scenes=mgr)
    sheet = Sheet.create_default()
    proj._sheets = [sheet]
    ps = PaperScene(sheet, resolver)
    # MainWindow's wiring (Task 8), reproduced for the headless scene.
    proj.blockDefinitionsChanged.connect(ps.refresh_schematic_viewports)
    return dict(proj=proj, sym=sym, sch=sch, mgr=mgr, resolver=resolver,
                sheet=sheet, ps=ps)


def _place(env, scale=0.0, title=""):
    data = SheetViewData("schematic", env["sch"].id, title, scale,
                         100.0, 100.0, 104.0, 54.0)
    return env["ps"].add_viewport(data)


def _grow(env, length=200.0):
    env["proj"].commit_block_definition(
        block_id=env["sch"].id, name=env["sch"].name, library="", series="",
        primitives=_prims(env["sym"].id, length), origin=(0.0, 0.0),
        place_instance=False)


# ── Task 4: resolver ─────────────────────────────────────────────────────────

def test_resolve_schematic_returns_render_scene_and_extent(env):
    scene, rect = env["resolver"].resolve("schematic", env["sch"].id)
    assert scene is env["mgr"].scene_for(env["sch"].id)
    assert rect == QRectF(-2, -2, 104, 54)


def test_resolve_schematic_none_for_unknown_or_plain(env):
    r = env["resolver"]
    assert r.resolve("schematic", "missing") is None
    assert r.resolve("schematic", env["sym"].id) is None
    assert r.resolve_level_context("schematic", env["sch"].id) is None


def test_display_name(env):
    r = env["resolver"]
    assert r.display_name("schematic", env["sch"].id) == "Riser"
    assert r.display_name("schematic", "missing") == "missing"
    assert r.display_name("plan", "Plan: Level 1") == "Plan: Level 1"


def test_resolver_without_manager_degrades(env):
    r = ViewResolver(env["proj"], _PlanStub(), _DetailStub(), None)
    assert r.resolve("schematic", env["sch"].id) is None


# -- Task 5: viewport rules ---------------------------------------------------

def test_crop_is_live_and_never_persisted(env):
    vp = _place(env)
    assert vp._effective_crop() == QRectF(-2, -2, 104, 54)
    assert vp.data.crop_rect.isEmpty()               # D-S10: no stale crop
    assert vp.data.to_dict()["crop_rect"]["w"] == 0


def test_title_is_live_name_unless_overridden(env):
    vp = _place(env)
    assert vp.display_title() == "Riser"
    env["proj"].set_block_metadata(env["sch"].id, "Riser B", "", "")
    assert vp.display_title() == "Riser B"            # rename, no migration
    typed = _place(env, title="Typ. Riser")
    assert typed.display_title() == "Typ. Riser"


def test_property_panel_view_label_shows_name_not_id(env):
    vp = _place(env)
    props = ViewportProperties(env["ps"], vp).get_properties()
    assert props["View"]["value"] == "Riser"


def test_resize_handles_only_at_nts(env):
    nts = _place(env, scale=0.0)
    scaled = _place(env, scale=0.5)
    assert nts.manip_capabilities() == {"translate", "scale"}
    assert scaled.manip_capabilities() == {"translate"}
    w0 = scaled.data.w
    scaled.manip_scale(2.0, 2.0, QPointF(scaled.data.x, scaled.data.y))
    assert scaled.data.w == w0                        # backstop: inert


def test_edit_refits_nts_content_and_resizes_scaled_box(env):
    nts = _place(env, scale=0.0)
    scaled = _place(env, scale=0.5)
    assert (scaled.data.w, scaled.data.h) == (52.0, 27.0)   # 104x54 x 0.5
    x0, y0 = scaled.data.x, scaled.data.y
    _grow(env)                                        # extent -> 208 x 58
    assert (nts.data.w, nts.data.h) == (104.0, 54.0)  # NTS box keeps its size
    assert nts._effective_crop() == QRectF(-4, -4, 208, 58)
    assert (scaled.data.w, scaled.data.h) == (104.0, 29.0)
    assert (scaled.data.x, scaled.data.y) == (x0, y0)  # top-left anchored


def test_cross_stack_undo_shows_placeholder_and_redo_restores(env):
    vp = _place(env)
    env["proj"].undo()                                # removes the schematic
    assert vp._placeholder
    env["proj"].redo()
    assert not vp._placeholder
    assert vp._effective_crop() == QRectF(-2, -2, 104, 54)


def test_drop_dialog_schematic_defaults(qapp):
    from firepro3d.paper_space import SheetViewPropertiesDialog
    dlg = SheetViewPropertiesDialog("", title_placeholder="Riser",
                                    default_scale="NTS")
    assert dlg.get_title() == ""
    assert dlg._title_edit.placeholderText() == "Riser"
    assert dlg.get_scale() == 0.0
    plain = SheetViewPropertiesDialog("Plan: Level 1")
    assert plain.get_title() == "Plan: Level 1"
    assert plain.get_scale() == pytest.approx(0.01)   # 1:100 unchanged
