"""D4: Copy/Cut pick a base point; payload carries base + scene role; Cut = 1 undo."""
import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests._modify_tools_helpers import PRIMITIVES, add_primitive
from tests._snap_polish_helpers import click, close_view, make_view


def _esc(view):
    """The real Escape path: a key event to the view -> scene keyPressEvent."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)


@pytest.mark.parametrize("name", list(PRIMITIVES))
def test_copy_writes_payload_with_base(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        scene._modify_ctl.start("copy")
        assert scene.mode == "copy_base"
        assert item.isSelected()                          # I-2: entry keeps selection
        # Well clear of every primitive's snap points (the base snaps normally, D4).
        click(view, QPointF(400, 300))
        payload = json.loads(QApplication.clipboard().text())
        assert payload["fp3d_clipboard"] == 1
        assert payload["scene_role"] == "block_editor"
        assert payload["base"] == pytest.approx([400.0, 300.0], abs=0.5)
        assert len(payload["items"]) == 1
        assert payload["items"][0] == item.to_dict()
        assert scene.mode in (None, "select")
        assert item.isSelected()                          # selection intact
    finally:
        close_view(view, scene)


def test_cut_removes_in_one_undo_step(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "rect")
        p0 = scene._undo_pos
        scene._modify_ctl.start("cut")
        click(view, QPointF(0, 0))
        assert getattr(scene, attr) == []
        assert item.scene() is None
        assert scene._undo_pos == p0 + 1                  # [RED]
        payload = json.loads(QApplication.clipboard().text())
        assert len(payload["items"]) == 1
        scene.undo()
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_copy_esc_copies_nothing(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        QApplication.clipboard().setText("sentinel")
        scene._modify_ctl.start("copy")
        _esc(view)                                        # real Esc path
        assert scene.mode in (None, "select")
        assert QApplication.clipboard().text() == "sentinel"
    finally:
        close_view(view, scene)


def test_add_from_dict_registers_each_type(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    view, scene = make_view(scale=1.0)
    try:
        cases = [(name, factory, attr) for name, (factory, attr) in PRIMITIVES.items()]
        cases.append(("text", lambda: TextItem(TextAnnotationData(text="T")), "_texts"))
        for name, factory, attr in cases:
            d = factory().to_dict()
            new = scene._add_from_dict(d)
            assert new is not None and new.scene() is scene, name
            assert new in getattr(scene, attr), name
            assert new.to_dict()["type"] == d["type"], name
    finally:
        close_view(view, scene)


def test_add_from_dict_unknown_type_is_none(qapp):
    view, scene = make_view(scale=1.0)
    try:
        assert scene._add_from_dict({"type": "no_such_thing"}) is None
    finally:
        close_view(view, scene)


def test_clipboard_payload_rejects_foreign(qapp):
    view, scene = make_view(scale=1.0)
    try:
        QApplication.clipboard().setText(json.dumps([{"type": "draw_line"}]))
        assert scene.clipboard_payload() is None
        QApplication.clipboard().setText("not json")
        assert scene.clipboard_payload() is None
        QApplication.clipboard().setText(json.dumps(
            {"fp3d_clipboard": 99, "base": [0, 0], "items": []}))
        assert scene.clipboard_payload() is None
    finally:
        close_view(view, scene)
