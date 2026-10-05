"""LT3-8 -- the cascade table (canvas half; paper half guarded in Task 9)."""
import pytest

from firepro3d import stroke_style as ss, paper_display as pd
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden, make_linetype


@pytest.fixture(autouse=True)
def _qt(qapp):
    """Model_Space needs a QApplication."""


def _style(lt, w):
    st = ss.default_style()
    st["linetype"], st["weight"] = lt, w
    return st


def test_continuous_and_by_block_draw_solid():
    ms = Model_Space()
    for lt in (ss.CONTINUOUS, ss.BY_BLOCK):
        r = ss.resolve_stroke(_style(lt, ss.BY_BLOCK), ms.block_registry)
        assert r.lt is None and r.missing_id is None


def test_linetype_id_resolves_and_missing_reports():
    ms = Model_Space()
    lid = hidden(ms)
    assert ss.resolve_stroke(_style(lid, ss.BY_BLOCK), ms.block_registry).lt.block_id == lid
    r = ss.resolve_stroke(_style("deadbeef", ss.BY_BLOCK), ms.block_registry)
    assert r.lt is None and r.missing_id == "deadbeef"


def test_malformed_linetype_is_solid_without_badge():
    ms = Model_Space()
    d = make_linetype(length=0)
    ms.register_block_definition(d)
    r = ss.resolve_stroke(_style(d.id, ss.BY_BLOCK), ms.block_registry)
    assert r.lt is None and r.missing_id is None


def test_by_linetype_takes_dash_weight_else_blocks():
    ms = Model_Space()
    heavy = hidden(ms, weight="Heavy")
    plain = hidden(ms, name="Plain")
    assert ss.resolve_stroke(_style(heavy, ss.BY_LINETYPE), ms.block_registry).weight == "Heavy"
    assert ss.resolve_stroke(_style(plain, ss.BY_LINETYPE), ms.block_registry).weight == ss.BY_LINETYPE
    assert ss.canvas_weight_name(ss.BY_LINETYPE) == pd.model_blocks_weight()


def test_named_weight_overrides_dash_weight():
    ms = Model_Space()
    heavy = hidden(ms, weight="Heavy")
    assert ss.resolve_stroke(_style(heavy, "Light"), ms.block_registry).weight == "Light"
