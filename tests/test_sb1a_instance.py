"""SB1a: per-instance bound layer (design S2/S3; AC1, AC3, AC4, G1, G6-half)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.test_block_rotate import _ink


def _text(text, x=0.0, y=0.0, angle=0.0, **kw):
    d = {"type": "text", "text": text, "x": x, "y": y, "height_mm": 5.0, "angle": angle}
    d.update(kw)
    return d


def _attr(key, **kw):
    return normalise_attr({"key": key, **kw})


def _tag_def(ms, attrs, prims):
    d = BlockDefinition.new(name="Tag", library="", series="", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(20, 0)).to_dict()] + prims)
    d.attributes = attrs
    ms.register_block_definition(d)
    return d


def _texts(inst):
    return [op for op in inst.render_ops() if op.kind == "text"]


def _glyph_key(op):
    """Digest of a glyph path: element count + rounded bbox (one string differs
    from another by both)."""
    p = op.path
    r = p.boundingRect()
    return (p.elementCount(), round(r.x(), 2), round(r.y(), 2), round(r.width(), 2))


class _Stub(BlockInstance):
    """The A2 provider seam, stubbed (G1)."""
    hv = None

    def host_values(self):
        return self.hv


def test_bound_text_resolves_from_each_source(qapp):
    ms = Model_Space()
    d = _tag_def(ms, [_attr("Mark", default="A1"),
                      _attr("Area", type="number", precision=1, source="host",
                            host_key="Room.Area", placeholder="--")],
                 [_text("@[Mark]"), _text("@[Area]", y=-10.0)])
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    assert len(d.render_ops()) == 1                            # the line only (static)
    ops = _texts(inst)
    assert len(ops) == 2 and all(op.kind == "text" for op in ops)
    k_default = _glyph_key(ops[0])
    inst.set_attributes({"Mark": "B2"})
    assert _glyph_key(_texts(inst)[0]) != k_default          # instance value
    assert _glyph_key(_texts(inst)[1]) == _glyph_key(ops[1])  # "--" unchanged
    inst.set_attributes({"Mark": "B2", "Area": "7"})          # host override (D4)
    assert _glyph_key(_texts(inst)[1]) != _glyph_key(ops[1])


def test_static_ops_shared_bound_distinct(qapp):
    ms = Model_Space()
    d = _tag_def(ms, [_attr("Mark", default="A1")], [_text("@[Mark]")])
    a = ms.place_block_instance(d.id, (0.0, 0.0))
    b = ms.place_block_instance(d.id, (50.0, 0.0))
    b.set_attributes({"Mark": "ZZ"})
    oa, ob = a.render_ops(), b.render_ops()
    static = d.render_ops()
    assert len(static) == 1 and oa[0] is static[0] and ob[0] is static[0]   # F1
    assert oa[1] is not ob[1] and _glyph_key(oa[1]) != _glyph_key(ob[1])
    assert a.render_ops() is oa                                              # stable identity


def test_host_value_change_rebuilds_once(qapp):
    ms = Model_Space()
    d = _tag_def(ms, [_attr("Area", source="host", host_key="Room.Area", placeholder="--")],
                 [_text("@[Area]")])
    inst = _Stub(block_id=d.id, resolver=ms.get_block_definition)
    ms.addItem(inst)
    inst.hv = {"Room.Area": "12"}
    k1 = _glyph_key(_texts(inst)[0])
    n = inst._bound_builds
    _ink(inst); _ink(inst)                      # two real paints, same values
    assert inst._bound_builds == n              # no rebuild
    inst.hv = {"Room.Area": "99"}
    _ink(inst)
    assert inst._bound_builds == n + 1          # one rebuild
    assert _glyph_key(_texts(inst)[0]) != k1


def test_nested_bound_prim_uses_outer_values(qapp):
    ms = Model_Space()
    child = _tag_def(ms, [_attr("Mark", default="child")], [_text("@[Mark]")])
    host = BlockDefinition.new(
        name="H", library="", series="", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": child.id, "x": 0.0, "y": 0.0}])
    host.attributes = [_attr("Mark", default="host")]
    ms.register_block_definition(host)
    outer = ms.place_block_instance(host.id, (0.0, 0.0))
    inner = ms.place_block_instance(child.id, (0.0, 0.0))
    inner.set_attributes({"Mark": "host"})
    assert _glyph_key(_texts(outer)[0]) == _glyph_key(_texts(inner)[0])   # "host" both
    outer.set_attributes({"Mark": "X"})
    assert _glyph_key(_texts(outer)[0]) != _glyph_key(_texts(inner)[0])


def _turned(path, cx, cy):
    from PyQt6.QtGui import QTransform
    t = QTransform()
    t.translate(cx, cy); t.rotate(180.0); t.translate(-cx, -cy)
    return t.map(path)


def _same_path(a, b, tol=0.05):
    if a.elementCount() != b.elementCount():
        return False
    return all(abs(a.elementAt(i).x - b.elementAt(i).x) < tol
               and abs(a.elementAt(i).y - b.elementAt(i).y) < tol
               for i in range(a.elementCount()))


def test_keep_upright_flip_threshold(qapp):
    ms = Model_Space()
    d = _tag_def(ms, [], [_text("Fg", keep_upright=True)])
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    op = _texts(inst)[0]
    assert op.readable is True
    base = inst._text_path(op)
    inst.set_block_rotation(89.0)
    assert _same_path(inst._text_path(op), op.path)              # not turned
    inst.set_block_rotation(91.0)
    fr = op.text_frame
    assert _same_path(inst._text_path(op), _turned(op.path, fr[0], fr[1]))
    inst.set_block_rotation(270.0)
    assert _same_path(inst._text_path(op), _turned(op.path, fr[0], fr[1]))   # (90, 270] turns
    inst.set_block_rotation(271.0)
    assert _same_path(inst._text_path(op), op.path)
    # a plain (non keep_upright) text op is never turned
    d2 = _tag_def(ms, [], [_text("Fg")])
    plain = ms.place_block_instance(d2.id, (0.0, 0.0))
    plain.set_block_rotation(180.0)
    pop = plain.render_ops()[1]
    assert pop.readable is False and _same_path(plain._text_path(pop), pop.path)


def test_keep_upright_mirrored_reads_unmirrored(qapp):
    from PyQt6.QtGui import QTransform
    ms = Model_Space()
    d = _tag_def(ms, [_attr("Mark", default="Fg")], [_text("@[Mark]", keep_upright=True)])
    a = ms.place_block_instance(d.id, (0.0, 0.0))
    b = ms.place_block_instance(d.id, (0.0, 0.0))
    b.set_block_mirrored(True)
    pa, pb = _texts(a)[0], _texts(b)[0]
    # the mirrored op's glyphs equal the un-mirrored glyphs reflected about
    # the box vertical, then placed on the mirrored box: i.e. glyph shape is
    # NOT a mirror image -- its bbox width matches and element order matches.
    ra, rb = pa.path.boundingRect(), pb.path.boundingRect()
    assert abs(ra.width() - rb.width()) < 0.05 and abs(ra.height() - rb.height()) < 0.05
    # reflecting b's path back across its own box centre vertical must NOT
    # equal a's path (it would if the glyphs had been mirrored)
    cx = pb.text_frame[0]
    refl = QTransform(); refl.translate(cx, 0); refl.scale(-1, 1); refl.translate(-cx, 0)
    assert not _same_path(refl.map(pb.path), QTransform.fromTranslate(
        pb.text_frame[0] - pa.text_frame[0], 0).map(pa.path))
