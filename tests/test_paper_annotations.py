from PyQt6.QtGui import QFontMetricsF

from firepro3d.paper_space import TextAnnotationData, Sheet, TextAnnotationItem


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
