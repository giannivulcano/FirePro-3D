"""SB1c -- annotative helper, definition key, canvas guards."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt

from firepro3d import annotative as an
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

HALF = 3.0          # authored half-length (printed mm)


def _annot_def(screen="scale", mode="annotative", name="A"):
    ln = LineItem(QPointF(-HALF, 0.0), QPointF(HALF, 0.0))
    ln.style["colour"] = "#ffffff"      # light ink on the dark render backdrop (HF1 record colour)
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    d.scale_mode = mode
    d.annotative_screen = screen
    return d


def _placed(screen="scale", mode="annotative", role="plan"):
    ms = Model_Space(scene_role=role)
    d = _annot_def(screen, mode)
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    return ms, d, inst


def test_definition_round_trips_annotative_screen(qapp):
    d = _annot_def("fixed")
    rec = d.to_dict()
    assert rec["annotative_screen"] == "fixed"
    assert BlockDefinition.from_dict(rec).annotative_screen == "fixed"
    d.annotative_screen = "scale"
    rec = d.to_dict()
    assert "annotative_screen" not in rec            # default omitted (byte-identical)
    assert BlockDefinition.from_dict(rec).annotative_screen == "scale"


def test_paper_scene_size():
    assert an.paper_scene_size(3.0, 0.02) == pytest.approx(150.0)


def test_factor_real_size_is_one(qapp):
    ms, d, inst = _placed(mode="real_size")
    assert an.annotative_factor(inst) == 1.0
    assert not an.frame_scaled(inst)


def test_factor_scale_with_zoom_is_drawing_scale(qapp):
    ms, d, inst = _placed("scale")
    ms.scale_manager.drawing_scale = 50.0
    assert an.annotative_factor(inst) == pytest.approx(50.0)
    assert not an.frame_scaled(inst)


def test_factor_paper_pass_is_inverse_scale(qapp):
    ms, d, inst = _placed("fixed")
    inst._paper_scale = 0.005
    try:
        assert an.annotative_factor(inst) == pytest.approx(200.0)
        assert not an.frame_scaled(inst)
    finally:
        inst._paper_scale = None


def test_editor_role_factor_is_one(qapp):
    ms, d, inst = _placed("scale", role="block_editor")
    ms.scale_manager.drawing_scale = 100.0
    assert an.annotative_factor(inst) == 1.0       # D5: editor nested at k = 1
