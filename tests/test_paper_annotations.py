from PyQt6.QtGui import QFontMetricsF

from firepro3d.paper_space import TextAnnotationData, Sheet, TextAnnotationItem


# ─────────────────────────────────────────────────────────────────────────────
# Task-6: _parse_text_height_mm + TextAnnotationPropertiesDialog
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_text_height_bare_fraction():
    from firepro3d.paper_space import _parse_text_height_mm
    assert abs(_parse_text_height_mm('1/8"') - 3.175) < 0.01
    assert abs(_parse_text_height_mm('3mm') - 3.0) < 1e-6
    assert _parse_text_height_mm('garbage') is None


def test_dialog_accessors_round_trip(qapp):
    from firepro3d.paper_space import TextAnnotationPropertiesDialog
    from firepro3d.scale_manager import ScaleManager
    sm = ScaleManager()
    data = TextAnnotationData(text="Hi", height_mm=3.175, color="#112233",
                              bold=True, align="C", opaque_bg=True)
    dlg = TextAnnotationPropertiesDialog(data, sm)
    assert dlg.get_text() == "Hi"
    assert dlg.get_bold() is True
    assert dlg.get_alignment() == "C"
    assert dlg.get_color() == "#112233"
    assert dlg.get_opaque_bg() is True
    assert abs(dlg.get_height_mm() - 3.175) < 0.01


def test_text_annotation_data_round_trip():
    d = TextAnnotationData(
        text="GENERAL NOTES\n1. Comply with NFPA 13.",
        x=12.5, y=30.0, height_mm=3.175, wrap_width_mm=120.0,
        font_family="Arial", bold=True, italic=False,
        color="#ff0000", align="C", opaque_bg=True,
    )
    out = TextAnnotationData.from_dict(d.to_dict())
    assert out == d
    assert d.to_dict()["type"] == "text"


def test_text_annotation_data_partial_dict_defaults():
    out = TextAnnotationData.from_dict({"text": "X"})
    assert out.text == "X"
    assert out.height_mm == 3.175
    assert out.color == "#000000"
    assert out.align == "L"
    assert out.wrap_width_mm == 0.0


def test_sheet_without_annotations_key_loads_empty():
    base = Sheet.create_default().to_dict()
    base.pop("annotations", None)
    s = Sheet.from_dict(base)
    assert s.annotations == []


def test_sheet_round_trips_annotations():
    s = Sheet.create_default()
    s.annotations.append(TextAnnotationData(text="Note", x=5, y=5))
    s2 = Sheet.from_dict(s.to_dict())
    assert len(s2.annotations) == 1
    assert s2.annotations[0].text == "Note"


# ─────────────────────────────────────────────────────────────────────────────
# TextAnnotationItem — §9.3 / §9.4 sizing invariants
# ─────────────────────────────────────────────────────────────────────────────

def test_item_cap_height_scale(qapp):
    data = TextAnnotationData(text="A", height_mm=3.175)
    item = TextAnnotationItem(data)
    cap = QFontMetricsF(item.font()).capHeight()
    assert cap > 0
    assert abs(item.scale() * cap - 3.175) < 1e-3


def test_item_uses_pixel_size_not_point_size(qapp):
    item = TextAnnotationItem(TextAnnotationData(text="A"))
    assert item.font().pixelSize() > 0
    assert item.font().pointSize() == -1


def test_item_wrap_width_converts_to_local_units(qapp):
    data = TextAnnotationData(text="word " * 30, height_mm=3.0, wrap_width_mm=50.0)
    item = TextAnnotationItem(data)
    assert abs(item.textWidth() - 50.0 / item.scale()) < 1e-2


def test_item_auto_width_when_wrap_zero(qapp):
    item = TextAnnotationItem(TextAnnotationData(text="hello world", wrap_width_mm=0.0))
    assert item.textWidth() > 0


def test_item_default_color_black_and_z(qapp):
    item = TextAnnotationItem(TextAnnotationData(text="x"))
    assert item.defaultTextColor().name() == "#000000"
    assert item.zValue() == 15
    assert item.data is item._data


# ─────────────────────────────────────────────────────────────────────────────
# Task-3: edit lifecycle, anchor clamp, wrap-resize grip (§9.3, §9.5)
# ─────────────────────────────────────────────────────────────────────────────

def _stub_resolver():
    """Return a ViewResolver with all-None managers (safe for sheets with no views)."""
    from firepro3d.paper_space import ViewResolver
    return ViewResolver(None, None, None, None)


def test_item_is_empty_helper(qapp):
    """is_effectively_empty() detects whitespace-only text."""
    assert TextAnnotationItem(TextAnnotationData(text="   \n  ")).is_effectively_empty()
    assert not TextAnnotationItem(TextAnnotationData(text="x")).is_effectively_empty()


def test_item_clamp_to_paper_rect(qapp):
    """itemChange clamps negative positions to (0, 0)."""
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = TextAnnotationItem(TextAnnotationData(text="x", x=0, y=0))
    scene.addItem(item)
    item.setPos(-50, -50)
    assert item.pos().x() >= 0 and item.pos().y() >= 0


def test_item_clamp_does_not_exceed_paper(qapp):
    """itemChange clamps positions beyond paper width/height to the paper edge."""
    from firepro3d.paper_space import PaperScene, PAPER_SIZES
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = TextAnnotationItem(TextAnnotationData(text="x", x=0, y=0))
    scene.addItem(item)
    pw, ph = PAPER_SIZES[Sheet.create_default().paper_size]
    item.setPos(pw + 200, ph + 200)
    assert item.pos().x() <= pw and item.pos().y() <= ph


def test_sync_data_from_item(qapp):
    """sync_data_from_item writes current scene position into _data."""
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = TextAnnotationItem(TextAnnotationData(text="x", x=0, y=0))
    scene.addItem(item)
    item.setPos(10.0, 20.0)
    # itemChange(ItemPositionHasChanged) already calls sync_data_from_item
    assert abs(item.data.x - 10.0) < 0.01
    assert abs(item.data.y - 20.0) < 0.01


def test_begin_and_cancel_edit_reverts_text(qapp):
    """cancel_edit() restores the pre-edit text and clears _editing flag."""
    item = TextAnnotationItem(TextAnnotationData(text="original"))
    item.begin_edit()
    assert item._editing
    item.setPlainText("changed")
    item.cancel_edit()
    assert not item._editing
    assert item.toPlainText() == "original"
    assert item.data.text == "original"


def test_commit_edit_updates_data(qapp):
    """commit_edit() writes the new text to _data and clears _editing flag."""
    item = TextAnnotationItem(TextAnnotationData(text="old"))
    item.begin_edit()
    item.setPlainText("new text")
    result = item.commit_edit()
    assert result == "new text"
    assert not item._editing
    assert item.data.text == "new text"


def test_grip_mm_class_constant(qapp):
    """_GRIP_MM is accessible as a class attribute and is positive."""
    from firepro3d.paper_space import TextAnnotationItem as TAI
    assert TAI._GRIP_MM > 0


def test_wrap_resize_updates_wrap_width(qapp):
    """mouseMoveEvent while _resizing updates wrap_width_mm above MIN_TEXT_WRAP_WIDTH_MM."""
    from PyQt6.QtCore import QPointF
    from firepro3d.paper_space import PaperScene
    from firepro3d.constants import MIN_TEXT_WRAP_WIDTH_MM
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 20, x=10.0, y=10.0, wrap_width_mm=50.0)
    item = TextAnnotationItem(data)
    scene.addItem(item)
    item.setPos(10.0, 10.0)

    # Simulate entering resize mode directly
    item._resizing = True
    item._wrap_at_press = 50.0

    # Synthesise a fake mouse-move event at scene x=100, item origin x=10 → new_w=90
    class _FakeEvent:
        def scenePos(self):
            return QPointF(100.0, 15.0)
        def accept(self):
            pass

    item.mouseMoveEvent(_FakeEvent())
    assert abs(item.data.wrap_width_mm - 90.0) < 0.01
    assert item.data.wrap_width_mm >= MIN_TEXT_WRAP_WIDTH_MM


def test_wrap_resize_clamps_to_min(qapp):
    """mouseMoveEvent clamps wrap_width_mm to MIN_TEXT_WRAP_WIDTH_MM when dragged left."""
    from PyQt6.QtCore import QPointF
    from firepro3d.paper_space import PaperScene
    from firepro3d.constants import MIN_TEXT_WRAP_WIDTH_MM
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 10, x=10.0, y=10.0, wrap_width_mm=50.0)
    item = TextAnnotationItem(data)
    scene.addItem(item)
    item.setPos(10.0, 10.0)

    item._resizing = True
    item._wrap_at_press = 50.0

    class _FakeEvent:
        def scenePos(self):
            # Scene x=10, item origin x=10 → raw new_w=0, below minimum
            return QPointF(10.0, 15.0)
        def accept(self):
            pass

    item.mouseMoveEvent(_FakeEvent())
    assert item.data.wrap_width_mm == MIN_TEXT_WRAP_WIDTH_MM


def test_grip_press_starts_resizing(qapp):
    """mousePressEvent on the grip rect sets _resizing=True; far points do not contain the grip."""
    from PyQt6.QtCore import QPointF
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 10, x=10.0, y=10.0, wrap_width_mm=50.0)
    item = TextAnnotationItem(data)
    scene.addItem(item)
    item.setPos(10.0, 10.0)
    item.setSelected(True)

    grip_center = item._grip_scene_rect().center()

    class _FakeEvent:
        def __init__(self, pos):
            self._pos = pos
        def scenePos(self):
            return self._pos
        def accept(self):
            pass

    # Positive: press inside the grip → _resizing becomes True
    item.mousePressEvent(_FakeEvent(grip_center))
    assert item._resizing is True

    # Negative: a far-away point is not contained within the grip rect
    far_point = QPointF(0.0, 0.0)
    assert not item._grip_scene_rect().contains(far_point)


def test_delete_key_vs_edit_mode(qapp):
    """Delete key emits delete_requested when not editing; suppressed when editing."""
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt as _Qt
    from firepro3d.paper_space import PaperScene

    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = TextAnnotationItem(TextAnnotationData(text="hello"))
    scene.addItem(item)

    fired = []
    item.delete_requested.connect(lambda obj: fired.append(obj))

    # Not editing: Delete should fire delete_requested
    key_delete = QKeyEvent(
        QEvent.Type.KeyPress, _Qt.Key.Key_Delete, _Qt.KeyboardModifier.NoModifier
    )
    item.keyPressEvent(key_delete)
    assert len(fired) == 1

    # Editing: Delete should NOT fire delete_requested (it deletes a character instead)
    fired.clear()
    item.begin_edit()
    assert item._editing is True
    key_delete2 = QKeyEvent(
        QEvent.Type.KeyPress, _Qt.Key.Key_Delete, _Qt.KeyboardModifier.NoModifier
    )
    item.keyPressEvent(key_delete2)
    assert len(fired) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Task-4: PaperScene annotation lifecycle + data-driven rebuild
# ─────────────────────────────────────────────────────────────────────────────

def test_scene_add_remove_annotation(qapp):
    """add_annotation tracks item in scene and data in sheet; remove_annotation cleans both."""
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = scene.add_annotation(TextAnnotationData(text="Note", x=10, y=10))
    assert item in scene.get_annotations()
    assert item.data in scene.sheet.annotations
    scene.remove_annotation(item)
    assert item not in scene.get_annotations()
    assert item.data not in scene.sheet.annotations


def test_setup_rebuilds_annotations_from_data(qapp):
    """PaperScene._setup() rebuilds TextAnnotationItems from sheet.annotations."""
    from firepro3d.paper_space import PaperScene
    sheet = Sheet.create_default()
    sheet.annotations.append(TextAnnotationData(text="Persisted", x=5, y=5))
    scene = PaperScene(sheet, _stub_resolver())
    texts = [i.toPlainText() for i in scene.get_annotations()]
    assert "Persisted" in texts


def test_export_scene_contains_annotation(qapp, tmp_path):
    """export_pdf renders annotations for free via the data-driven _setup rebuild."""
    from firepro3d.paper_export import export_pdf
    from firepro3d.paper_space import PaperScene
    sheet = Sheet.create_default()
    sheet.annotations.append(TextAnnotationData(text="PLOTME", x=20, y=20))
    out = tmp_path / "s.pdf"
    export_pdf([sheet], _stub_resolver(), str(out), dpi=150)
    assert out.exists() and out.stat().st_size > 0
    probe = PaperScene(sheet, _stub_resolver())
    assert any(i.toPlainText() == "PLOTME" for i in probe.get_annotations())


# ─────────────────────────────────────────────────────────────────────────────
# Task-5: begin_place_text / commit_place_text + empty auto-delete (§9.5)
# ─────────────────────────────────────────────────────────────────────────────

def test_commit_place_empty_discards(qapp):
    """commit_place_text with empty text removes transient item and tracks nothing."""
    from firepro3d.paper_space import PaperScene
    from PyQt6.QtCore import QPointF
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = scene.begin_place_text(QPointF(30, 30))
    assert item in scene.items()                # transient, on scene
    assert item not in scene.get_annotations()  # NOT tracked yet
    item.setPlainText("")
    scene.commit_place_text(item)
    assert item not in scene.items()            # discarded
    assert scene.get_annotations() == []


def test_commit_place_nonempty_tracks(qapp):
    """commit_place_text with non-empty text creates a tracked annotation."""
    from firepro3d.paper_space import PaperScene
    from PyQt6.QtCore import QPointF
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = scene.begin_place_text(QPointF(30, 30))
    item.setPlainText("Hello")
    scene.commit_place_text(item)
    texts = [i.toPlainText() for i in scene.get_annotations()]
    assert "Hello" in texts


# ─────────────────────────────────────────────────────────────────────────────
# Task-8: Integration tests — real save/load round-trip + end-to-end undo/redo
# ─────────────────────────────────────────────────────────────────────────────

def test_project_round_trip_preserves_annotations(qapp, tmp_path):
    """Sheet annotations survive a real .fpd save→load via scene_io.

    This test goes through the ACTUAL Model_Space.save_to_file /
    load_from_file path (not just Sheet.to_dict/from_dict), so it will
    fail if scene_io ever stops delegating the 'sheets' key to
    Sheet.to_dict / from_dict or drops any annotation field.
    """
    from firepro3d.model_space import Model_Space

    # --- Build a scene with one sheet carrying a rich annotation ---
    scene1 = Model_Space()
    sheet = Sheet.create_default()
    sheet.annotations.append(
        TextAnnotationData(
            text="RT NOTE",
            x=9.0, y=9.0,
            color="#ff0000",
            height_mm=4.0,
            wrap_width_mm=80.0,
        )
    )
    scene1._sheets = [sheet]

    # --- Save through the real serialisation path ---
    save_path = tmp_path / "p.fpd"
    result = scene1.save_to_file(str(save_path))
    assert result is True, "save_to_file should return True on success"
    assert save_path.exists(), ".fpd file was not created"

    # --- Load into a fresh scene ---
    scene2 = Model_Space()
    scene2.load_from_file(str(save_path))

    # --- Verify the sheet and annotation survived intact ---
    assert len(scene2._sheets) == 1, "Expected exactly one sheet after load"
    loaded_annotations = scene2._sheets[0].annotations
    assert len(loaded_annotations) == 1, "Expected exactly one annotation after load"

    a = loaded_annotations[0]
    assert a.text == "RT NOTE"
    assert a.color == "#ff0000"
    assert abs(a.height_mm - 4.0) < 1e-6
    assert abs(a.wrap_width_mm - 80.0) < 1e-6
    assert abs(a.x - 9.0) < 1e-6
    assert abs(a.y - 9.0) < 1e-6


def test_undo_redo_add_text_end_to_end(qapp):
    """AddTextAnnotationCommand wired to _undo_stack does a full undo/redo cycle.

    Distinct from the command-unit test: asserts the live scene tracking list
    (get_annotations()) rather than the data list, covering the full
    PaperScene integration path.
    """
    from firepro3d.paper_space import PaperScene
    from firepro3d.paper_commands import AddTextAnnotationCommand

    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="U", x=1, y=1)

    # Push via the stack (not _do_add_annotation directly) — exercises the
    # same path as a real user action routed through _undo_stack.
    scene._undo_stack.push(AddTextAnnotationCommand(scene, data))
    assert len(scene.get_annotations()) == 1

    scene._undo_stack.undo()
    assert scene.get_annotations() == []

    scene._undo_stack.redo()
    assert len(scene.get_annotations()) == 1


def test_undo_redo_move_text_end_to_end(qapp):
    """MoveTextAnnotationCommand undo/redo restores and re-applies scene position.

    Tests the full round-trip: scene item position, data fields, and stack state.
    """
    from firepro3d.paper_space import PaperScene
    from firepro3d.paper_commands import MoveTextAnnotationCommand, _find_text_item

    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="M", x=5.0, y=5.0)
    scene.add_annotation(data)  # adds via the scene tracking layer

    old_pos = (5.0, 5.0)
    new_pos = (42.0, 77.0)
    scene._undo_stack.push(MoveTextAnnotationCommand(scene, data, old_pos, new_pos))

    # After redo (applied automatically on push): item and data at new_pos
    item = _find_text_item(scene, data)
    assert item is not None
    assert abs(data.x - 42.0) < 1e-6
    assert abs(data.y - 77.0) < 1e-6
    assert abs(item.pos().x() - 42.0) < 1e-6
    assert abs(item.pos().y() - 77.0) < 1e-6

    # Undo: back to old_pos
    scene._undo_stack.undo()
    assert abs(data.x - 5.0) < 1e-6
    assert abs(data.y - 5.0) < 1e-6
    assert abs(item.pos().x() - 5.0) < 1e-6
    assert abs(item.pos().y() - 5.0) < 1e-6

    # Redo: forward to new_pos again
    scene._undo_stack.redo()
    assert abs(data.x - 42.0) < 1e-6
    assert abs(data.y - 77.0) < 1e-6
    assert abs(item.pos().x() - 42.0) < 1e-6
    assert abs(item.pos().y() - 77.0) < 1e-6
