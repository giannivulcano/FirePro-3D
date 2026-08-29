"""Item 2 of the PDF Import Polish cluster: PDF vector line-width hierarchy is
preserved (colour still deferred). Source widths are the default; a Display-
Manager per-file Line-Weight override wins (flattens). Generated fitz fixtures."""
import fitz  # PyMuPDF
from PyQt6.QtCore import Qt

from firepro3d.pdf_import_worker import extract_pdf_vectors_sync
from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay


def _make_pdf(path, widths):
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    shape = page.new_shape()
    for i, w in enumerate(widths):
        y = 20 + i * 20
        shape.draw_line((10, y), (180, y))
        shape.finish(width=w, color=(0, 0, 0))
    shape.commit()
    doc.save(str(path))
    doc.close()


def _pdf_stroke_widths(scene, geom_list, record):
    """Build the batched group; return the set of stroke pen widths."""
    group, _layers = scene._build_batched_underlay_group(geom_list, record)
    widths = set()
    for child in group.childItems():
        pen = child.pen()
        if pen.style() != Qt.PenStyle.NoPen:
            widths.add(round(pen.widthF(), 3))
    return widths


def test_extract_captures_path_width(tmp_path):
    p = tmp_path / "widths.pdf"
    _make_pdf(p, widths=[0.5, 3.0])
    geoms, _layers = extract_pdf_vectors_sync(str(p), page=0)
    widths = {round(g["width"], 2) for g in geoms
              if g.get("kind") == "path_points" and "width" in g}
    assert 0.5 in widths and 3.0 in widths


def test_widths_produce_distinct_pens(qapp):
    scene = Model_Space()
    rec = Underlay(type="pdf", path="x.pdf")
    geoms = [
        {"kind": "path_points", "layer": "PDF Vectors",
         "points": [(0, 0), (10, 0)], "closed": False, "width": 0.5},
        {"kind": "path_points", "layer": "PDF Vectors",
         "points": [(0, 5), (10, 5)], "closed": False, "width": 3.0},
    ]
    widths = _pdf_stroke_widths(scene, geoms, rec)
    assert len(widths) == 2   # two distinct pen widths -> hierarchy preserved


def test_per_file_weight_override_flattens(qapp):
    scene = Model_Space()
    rec = Underlay(type="pdf", path="x.pdf")
    rec.line_weight_name = "Medium"   # DM per-file Line-Weight override
    geoms = [
        {"kind": "path_points", "layer": "PDF Vectors",
         "points": [(0, 0), (10, 0)], "closed": False, "width": 0.5},
        {"kind": "path_points", "layer": "PDF Vectors",
         "points": [(0, 5), (10, 5)], "closed": False, "width": 3.0},
    ]
    widths = _pdf_stroke_widths(scene, geoms, rec)
    assert len(widths) == 1   # override wins -> all flattened to one width


def _two_width_geoms():
    return [
        {"kind": "path_points", "layer": "PDF Vectors",
         "points": [(0, 0), (10, 0)], "closed": False, "width": 0.5},
        {"kind": "path_points", "layer": "PDF Vectors",
         "points": [(0, 5), (10, 5)], "closed": False, "width": 3.0},
    ]


def _child_widths(group):
    return {round(c.pen().widthF(), 3) for c in group.childItems()
            if c.pen().style() != Qt.PenStyle.NoPen}


def test_repen_preserves_width_hierarchy(qapp):
    scene = Model_Space()
    rec = Underlay(type="pdf", path="x.pdf")
    group, _ = scene._build_batched_underlay_group(_two_width_geoms(), rec)
    scene.underlays.append((rec, group))
    scene.repen_underlay(rec)                 # e.g. a DM colour/opacity change
    assert len(_child_widths(group)) == 2     # hierarchy survives the re-pen


def test_repen_flattens_when_override_set(qapp):
    scene = Model_Space()
    rec = Underlay(type="pdf", path="x.pdf")
    group, _ = scene._build_batched_underlay_group(_two_width_geoms(), rec)
    scene.underlays.append((rec, group))
    rec.line_weight_name = "Medium"           # user sets a per-file override
    scene.repen_underlay(rec)
    assert len(_child_widths(group)) == 1     # override wins live
