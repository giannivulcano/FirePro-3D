"""ET1 G3 (persistence half): a line's per-end ``scale`` survives every
round trip -- .fpd save / load, a block definition through .fpdb, copy /
paste and Explode. Each reads the record back off the real output."""
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt5_support import arrow

START = {"end": "none", "visible": True, "scale": 0.5}
FINISH = {"end": None, "visible": True, "mirrored": True, "scale": 3.0}


def _scaled_line(a, x0=0.0, x1=2000.0):
    ln = LineItem(QPointF(x0, 0.0), QPointF(x1, 0.0))
    ln.style["start"] = dict(START)
    ln.style["finish"] = {**FINISH, "end": a.id}
    return ln


def _assert_scaled(style, a):
    assert style["start"] == START, style["start"]
    assert style["finish"] == {**FINISH, "end": a.id}, style["finish"]


def test_g3_fpd_save_load_keeps_scale(qapp, tmp_path):
    """A model scene holds geometry only inside blocks (containment C1: a
    loose model line is clean-dropped on load), so the scaled line rides in
    an embedded definition with a placement."""
    ms = Model_Space()
    a = arrow()
    d = BlockDefinition.new(name="Scaled", library="L", series="S",
                            primitives=[_scaled_line(a).to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(a)
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    path = tmp_path / "p.fpd"
    ms.save_to_file(str(path))
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    d2 = ms2.get_block_definition(d.id)
    assert d2 is not None and d2 is not d
    assert [i.block_id for i in ms2._block_instances] == [d.id]
    (prim,) = d2.primitives
    _assert_scaled(prim["style"], a)


def test_g3_fpdb_block_keeps_scale(tmp_path):
    a = arrow()
    d = BlockDefinition.new(name="Scaled", library="L", series="S",
                            primitives=[_scaled_line(a).to_dict()], origin=(0.0, 0.0))
    path = block_library.save_to_library(d, root=str(tmp_path))
    loaded = block_library.load_block_file(path)
    assert loaded is not None and loaded is not d
    (prim,) = loaded.primitives
    _assert_scaled(prim["style"], a)


def test_g3_paste_keeps_scale(qapp):
    """The in-process paste path (``paste_items(data=)``) -- no host
    clipboard (the LT5 E9 driver)."""
    a = arrow()
    data = [_scaled_line(a).to_dict()]
    ms = Model_Space()
    ms.register_block_definition(a)
    (it,) = ms.paste_items(QPointF(0.0, 0.0), data=data)
    _assert_scaled(it.style, a)


def test_g3_explode_keeps_scale(qapp):
    """The real ``block_explode`` path in the Block Editor scene it runs in
    (the LT5 E9 / WM2 G8 setup)."""
    from firepro3d.block_explode import explode_instances
    from tests.test_wm2_nested_explode import _editor_scene
    a = arrow()
    d = BlockDefinition.new(name="X", library="L", series="S",
                            primitives=[_scaled_line(a, -300.0, 300.0).to_dict()],
                            origin=(0.0, 0.0))
    _w, ms = _editor_scene([a, d])
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    (item,) = explode_instances(ms, [inst], flatten=False)
    assert isinstance(item, LineItem)
    _assert_scaled(item.style, a)
