"""SB4a D6/D7 -- Hide when empty: a blank bound text drops and closes its slot."""
import pytest

from firepro3d.block_attributes import bound_text_ops, collapse_shifts
from firepro3d import element_params as ep
from tests.test_sb4a_pipe_label import _pipe, _pipe_def, _scene, _solve


def _ys(ops):
    return sorted(round(op.path.boundingRect().center().y(), 3)
                  for op in ops if op.text_frame is not None)


def test_collapse_shifts_drops_blank_and_closes_the_slot():
    boxes = [(-5.0, -1.0, False), (1.0, 5.0, False), (6.0, 10.0, True), (11.0, 15.0, False)]
    # (top, bottom, dropped) in definition-local y, origin 0
    assert collapse_shifts(boxes) == [0.0, 0.0, None, -5.0]


def test_collapse_shifts_ignores_a_box_centred_on_the_origin():
    assert collapse_shifts([(-2.0, 2.0, True), (3.0, 6.0, False)]) == [None, 0.0]


def test_g2_presolve_hydraulic_lines_collapse_and_bounds_shrink(qapp):
    ms = _scene()
    p = _pipe(ms)
    d = _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Length]", 1.0, False),
                             ("@[Flow]", 6.0, True), ("@[FrictionLoss]", 11.0, True)))
    hv = ep.host_values(p, None)
    ops, _ = bound_text_ops(d, {}, hv, False, 1.0, None, None)
    assert len(_ys(ops)) == 2                       # Flow + FrictionLoss dropped
    k = ms.scale_manager.drawing_scale                 # label bounds are authored mm x k
    h0 = p.label.boundingRect().height()
    _solve(ms, p, 52.5, 1.25)
    assert p.label.boundingRect().height() > h0 + 8.0 * k   # Flow (6) + FrictionLoss (11..14) return


def test_g2_zero_flow_collapses_like_no_solve(qapp):
    ms = _scene()
    p = _pipe(ms)
    _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Flow]", 6.0, True)))
    _solve(ms, p, 0.0, 0.0)
    assert ep.host_values(p, {"Flow"})["Flow"].raw is None


def test_hide_empty_off_shows_the_placeholder(qapp):
    ms = _scene()
    p = _pipe(ms)
    d = _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Flow]", 6.0, False)))
    ops, _ = bound_text_ops(d, {}, ep.host_values(p, None), False, 1.0, None, None)
    assert len(_ys(ops)) == 2


def test_explode_drops_the_blank_line_and_lands_where_it_was_drawn(qapp, make_model_space):
    """Explode parity (recipe: test_sb3_bound_label.py::test_exploded_bound_text_lands_in_the_hugged_box).
    An unhosted instance: every host field is blank, so the hide_empty Flow
    line drops and Length (beyond it) closes the slot -- drawn and exploded alike."""
    from firepro3d.block_explode import explode_instances
    from firepro3d.text_item import TextItem
    ms = make_model_space()
    d = _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Flow]", 6.0, True),
                             ("@[Length]", 11.0, False)))
    inst = ms.place_block_instance(d.id, (100.0, 50.0))
    drawn = sorted(o.text_frame[1] for o in inst.render_ops() if o.text_frame is not None)
    assert len(drawn) == 2                                   # Flow dropped when drawn
    made = [t for t in explode_instances(ms, [inst], flatten=True) if isinstance(t, TextItem)]
    assert len(made) == 2                                    # ...and when exploded
    ys = sorted(t.grip_points()[8].y() - 50.0 for t in made)
    assert ys == pytest.approx(drawn, abs=0.05)


def test_dropped_line_closes_its_slot_in_the_drawn_ops(qapp):
    """Length (beyond the dropped Flow) lands where Flow sat when it shows."""
    ms = _scene()
    p = _pipe(ms)
    hv = ep.host_values(p, None)
    shown = _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Flow]", 6.0, False),
                                 ("@[Length]", 11.0, False)))
    dropped = _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Flow]", 6.0, True),
                                   ("@[Length]", 11.0, False)))
    def centres(d):            # the box centres (glyph-independent)
        ops = bound_text_ops(d, {}, hv, False, 1.0, None, None)[0]
        return sorted(o.text_frame[1] for o in ops if o.text_frame is not None)
    ys_shown, ys_dropped = centres(shown), centres(dropped)
    assert ys_dropped == pytest.approx([ys_shown[0], ys_shown[1]], abs=0.01)
