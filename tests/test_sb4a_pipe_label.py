"""SB4a -- pipe label drawn by an annotation block (design
docs/superpowers/specs/2026-10-31-sb4a-pipe-label-design.md)."""
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.bound_label import BoundLabelItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _pipe(ms, x0=0.0, y0=0.0, x1=3000.0, y1=0.0):
    return ms.add_pipe(ms.add_node(x0, y0), ms.add_node(x1, y1))


def _pipe_def(ms, texts=(("@[Diameter]", -4.0, False), ("@[Length]", 1.0, False))):
    """An eligible Pipe label: Annotative, Scale with zoom, host Pipe; one
    3 mm text per (text, y, hide_empty); mapped as the project default."""
    prims, keys = [], set()
    for text, y, hide in texts:
        rec = {"type": "text", "text": text, "x": -10.0, "y": y, "height_mm": 3.0,
               "wrap_width_mm": 20.0, "box_height_mm": 3.0, "align": "C", "valign": "M"}
        if hide:
            rec["hide_empty"] = True
        prims.append(rec)
        keys.add(text[2:-1])
    d = BlockDefinition.new(name="TestPipeLabel", library="", series="",
                            origin=(0.0, 0.0), primitives=prims)
    d.scale_mode = "annotative"
    d.host_category = "Pipe"
    d.attributes = [normalise_attr({"key": k, "source": "host", "host_key": k})
                    for k in sorted(keys)]
    ms.register_block_definition(d)
    ms.annotation_defaults["Pipe"] = d.id
    return d


def test_top_level_label_reads_its_explicit_host(qapp):
    ms = _scene()
    p = _pipe(ms)
    lab = BoundLabelItem(p, child=False)
    ms.addItem(lab)
    assert lab.parentItem() is None
    assert lab.host is p
    assert lab.category == "Pipe"
    hv = lab.host_values({"Diameter"})
    assert hv is not None and hv["Diameter"].raw == p._properties["Diameter"]["value"]
