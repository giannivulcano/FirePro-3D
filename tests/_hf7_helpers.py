"""HF7 fixtures: DXFs written with ezdxf, extraction, and underlay rendering."""
from __future__ import annotations

import ezdxf
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter

from firepro3d.dxf_import_worker import DxfImportWorker
from firepro3d.model_space import Model_Space
from firepro3d.underlay import Underlay

BAIT = "#ff0022"


def new_doc():
    doc = ezdxf.new(setup=True)
    return doc, doc.modelspace()


def extract(doc, tmp_path, name="f.dxf", **kw):
    path = str(tmp_path / name)
    doc.saveas(path)
    return DxfImportWorker.extract_file_sync(path, skip_sanitize=True, **kw)


def square(x, y, side):
    return [(x, y), (x + side, y), (x + side, y + side), (x, y + side)]


def ring_hatch(msp, *, layer="0", x=0.0, y=0.0, color=None):
    h = msp.add_hatch(dxfattribs={"layer": layer})
    if color is not None:
        h.dxf.color = color
    h.paths.add_polyline_path(square(x, y, 100), is_closed=True, flags=1)
    h.paths.add_polyline_path(square(x + 40, y + 40, 20), is_closed=True, flags=16)
    return h


def fills(geoms):
    return [g for g in geoms if g.get("kind") == "fill"]


def built_scene(geoms, colour=BAIT):
    scene = Model_Space()
    rec = Underlay(type="dxf", path="fixture.dxf", colour=colour)
    group, _ = scene._build_batched_underlay_group(geoms, rec)
    scene._apply_underlay_display(group, rec)
    scene._attach_snap_index(group, geoms, rec)
    scene.underlays.append((rec, group))
    return scene, rec, group


def render(scene, rect: QRectF, size=200) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0xffffffff)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), rect)
    p.end()
    return img


def sample(img, rect: QRectF, x, y):
    """Colour at DXF point (x, y); scene Y is the negated DXF Y."""
    sx = (x - rect.x()) / rect.width() * img.width()
    sy = (-y - rect.y()) / rect.height() * img.height()
    return img.pixelColor(int(sx), int(sy))


def is_bait(c) -> bool:
    return c.red() > 200 and c.green() < 90 and c.blue() < 120
