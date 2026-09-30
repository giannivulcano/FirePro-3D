"""Drag a block from the Blocks browser onto a canvas (AC2, AC4, AC5, AC13)."""
import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _line_def(name, extra=()):
    prims = [LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(), *extra]
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


def _leaf(browser, name):
    t = browser._tree
    for i in range(t.topLevelItemCount()):
        lib = t.topLevelItem(i)
        for j in range(lib.childCount()):
            ser = lib.child(j)
            for k in range(ser.childCount()):
                if ser.child(k).text(0) == name:
                    return ser.child(k)
    raise AssertionError(name)


def test_block_leaf_mime_carries_id(qapp, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    from firepro3d.mime_types import MIME_BLOCK
    sc = Model_Space()
    b = _line_def("B")
    sc.register_block_definition(b)
    br = BlocksBrowser(sc, root=str(tmp_path))
    mime = br._tree.mimeData([_leaf(br, "B")])
    assert mime.hasFormat(MIME_BLOCK)
    assert json.loads(bytes(mime.data(MIME_BLOCK)).decode()) == {"id": b.id, "path": None}
    folder = br._tree.topLevelItem(0)
    assert not br._tree.mimeData([folder]).hasFormat(MIME_BLOCK)
