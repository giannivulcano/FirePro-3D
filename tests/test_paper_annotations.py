from PyQt6.QtGui import QFontMetricsF

from firepro3d.paper_space import TextAnnotationData, Sheet, TextAnnotationItem
from firepro3d.paper_commands import ResizeTextBoxCommand


# ─────────────────────────────────────────────────────────────────────────────
# Task-6: _parse_text_height_mm  (TextAnnotationPropertiesDialog removed Task-7)
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_text_height_bare_fraction():
    from firepro3d.paper_space import _parse_text_height_mm
    assert abs(_parse_text_height_mm('1/8"') - 3.175) < 0.01
    assert abs(_parse_text_height_mm('3mm') - 3.0) < 1e-6
    assert _parse_text_height_mm('garbage') is None


def test_properties_dialog_is_gone():
    import firepro3d.paper_space as ps
    assert not hasattr(ps, "TextAnnotationPropertiesDialog")


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
    from firepro3d.constants import DEFAULT_TEXT_HEIGHT_MM
    out = TextAnnotationData.from_dict({"text": "X"})
    assert out.text == "X"
    assert out.height_mm == DEFAULT_TEXT_HEIGHT_MM
    assert out.color == "#000000"
    assert out.align == "L"
    assert out.wrap_width_mm == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Smoke-test defect fixes: undo keyboard dispatch (#7) + Esc while editing (#2)
# ─────────────────────────────────────────────────────────────────────────────

def test_view_keypress_ctrl_z_undoes(qapp):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt
    from firepro3d.paper_space import PaperScene, PaperGraphicsView
    from firepro3d.paper_commands import AddTextAnnotationCommand
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    view = PaperGraphicsView(scene)
    scene._undo_stack.push(
        AddTextAnnotationCommand(scene, TextAnnotationData(text="U", x=1, y=1)))
    assert len(scene.get_annotations()) == 1
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z,
                                 Qt.KeyboardModifier.ControlModifier))
    assert scene.get_annotations() == []
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Y,
                                 Qt.KeyboardModifier.ControlModifier))
    assert len(scene.get_annotations()) == 1


def test_view_keypress_ctrl_z_ignored_while_editing(qapp):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt
    from firepro3d.paper_space import PaperScene, PaperGraphicsView
    from firepro3d.paper_commands import AddTextAnnotationCommand
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    view = PaperGraphicsView(scene)
    scene._undo_stack.push(
        AddTextAnnotationCommand(scene, TextAnnotationData(text="U", x=1, y=1)))
    item = scene.get_annotations()[0]
    item.begin_edit()
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z,
                                 Qt.KeyboardModifier.ControlModifier))
    assert len(scene.get_annotations()) == 1   # editor undo, not stack undo


def test_view_accepts_escape_override_only_while_editing(qapp):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt
    from firepro3d.paper_space import PaperScene, PaperGraphicsView
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    view = PaperGraphicsView(scene)
    item = scene.add_annotation(TextAnnotationData(text="Hi", x=2, y=2))
    item.begin_edit()
    assert scene._editing_item is item
    ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Escape,
                   Qt.KeyboardModifier.NoModifier)
    assert view.event(ev) is True
    assert ev.isAccepted()


def test_click_anywhere_in_box_hits_item(qapp):
    # Grab-anywhere: empty box area below the text must hit-test to the item,
    # not just the glyph strip (2026-07-20 smoke: "grab and pull" anywhere).
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QTransform
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = scene.add_annotation(TextAnnotationData(
        text="X", x=10, y=10, wrap_width_mm=80.0, box_height_mm=60.0))
    p = QPointF(10 + 40, 10 + 50)          # well below the single text line
    assert scene.itemAt(p, QTransform()) is item


def test_box_interior_grab_and_manipulator_coexist(qapp):
    # Grab-anywhere for the INITIAL pick: on an unselected block the empty box
    # interior hit-tests to the item (so a bare click selects it).  Once
    # selected, the SelectionManipulator frame (z=1e6) sits above the box and
    # owns the interior drag — a press there falls through to picking via the
    # manipulator's _click_through (the retired grip-halo hit area is gone).
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QTransform
    from firepro3d.paper_space import PaperScene
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = scene.add_annotation(TextAnnotationData(
        text="X", x=10, y=10, wrap_width_mm=80.0, box_height_mm=60.0))
    box = item.mapRectToScene(item._box_rect_local())
    p = QPointF(box.center().x(), box.bottom() - 5.0)   # empty area, in-box
    # Unselected: the empty box interior hits the item (grab-anywhere pick).
    assert scene.itemAt(p, QTransform()) is item
    # Selected: the manipulator frame is the topmost item over the interior.
    item.setSelected(True)
    scene._manipulator.rebake()
    assert isinstance(scene.itemAt(p, QTransform()), SelectionManipulator)


def test_item_escape_confirms_pending_placement(qapp):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt, QPointF
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    idx = scene.undo_stack.index()
    item = scene.begin_place_text(QPointF(10, 10))
    item.setPlainText("NOTE 1")
    item.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                 Qt.KeyboardModifier.NoModifier))
    assert scene._pending_text is None
    anns = scene.get_annotations()
    assert len(anns) == 1
    assert anns[0].data.text == "NOTE 1"
    assert scene.undo_stack.index() == idx + 1   # creation recorded for undo


def test_item_escape_discards_empty_pending_placement(qapp):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt, QPointF
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    idx = scene.undo_stack.index()
    item = scene.begin_place_text(QPointF(10, 10))
    item.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                 Qt.KeyboardModifier.NoModifier))
    assert scene._pending_text is None
    assert scene.get_annotations() == []
    assert scene.undo_stack.index() == idx       # nothing recorded


def test_item_escape_commits_existing_edit(qapp):
    """Esc on an existing block commits (not reverts); undo restores the original."""
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = scene.add_annotation(TextAnnotationData(text="Original", x=1, y=1))
    idx_before = scene.undo_stack.index()
    item.begin_edit()
    item.setPlainText("Changed")
    item.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                 Qt.KeyboardModifier.NoModifier))
    # Esc commits — "Changed" is now the live text
    assert item._data.text == "Changed"
    assert item._editing is False
    # Undo stack gained exactly one entry (the EditTextCommand)
    assert scene.undo_stack.index() == idx_before + 1
    # Undo restores "Original"
    scene.undo_stack.undo()
    assert item._data.text == "Original"


# ─────────────────────────────────────────────────────────────────────────────
# Smoke-test defect: ZeroDivisionError when height_mm == 0 (+ imperial precision)
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_format_survives_zero_height(qapp):
    # height 0 + a wrap width previously divided by a zero scale -> crash
    item = TextAnnotationItem(
        TextAnnotationData(text="x", height_mm=0.0, wrap_width_mm=50.0))
    assert item.scale() > 0            # clamped to a sane default, no ZeroDivisionError



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


# ─────────────────────────────────────────────────────────────────────────────
# Box resize via the SelectionManipulator — box/wrap/pinned-edge parity
#
# The 8-handle per-item grips are RETIRED (the scene's SelectionManipulator now
# draws the frame + handles and drives resize/move through manip_scale /
# manip_translate).  These tests drive manip_scale directly with the anchor the
# manipulator supplies (the corner/edge opposite the dragged handle) and assert
# the SAME box/wrap/pinned-edge outcomes the retired grip drag produced.
# Numeric old-vs-new parity lives in tests/test_selection_manipulator_paper.py.
# ─────────────────────────────────────────────────────────────────────────────

def _resize_setup(qapp, wrap=50.0, box_h=0.0, **kw):
    from firepro3d.paper_space import PaperScene
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 10, x=10.0, y=10.0,
                              wrap_width_mm=wrap, box_height_mm=box_h, **kw)
    item = TextAnnotationItem(data)
    scene.addItem(item)
    item.setPos(10.0, 10.0)
    item.setSelected(True)
    return scene, item, data


def test_br_corner_drag_grows_wrap_and_box_height(qapp):
    """BR resize (+x,+y via TL anchor): wrap AND box_height grow; x/y unchanged."""
    from PyQt6.QtCore import QPointF
    scene, item, data = _resize_setup(qapp)
    b = item.manip_bounds()
    item.manip_scale((b.width() + 20.0) / b.width(),
                     (b.height() + 15.0) / b.height(),
                     QPointF(b.x(), b.y()))            # anchor = TL
    assert abs(data.wrap_width_mm - 70.0) < 1.0
    assert data.box_height_mm > 0
    assert abs(data.x - 10.0) < 0.01
    assert abs(data.y - 10.0) < 0.01


def test_tl_corner_drag_moves_anchor_shrinks_box(qapp):
    """TL resize: x/y move; wrap and box height shrink; BR corner stays pinned."""
    from PyQt6.QtCore import QPointF
    scene, item, data = _resize_setup(qapp, wrap=60.0, box_h=60.0)
    b = item.manip_bounds()
    br_x, br_y = b.x() + b.width(), b.y() + b.height()
    item.manip_scale((b.width() - 10.0) / b.width(),
                     (b.height() - 5.0) / b.height(),
                     QPointF(br_x, br_y))              # anchor = BR
    assert data.x > 10.0
    assert data.y > 10.0
    assert data.wrap_width_mm < 60.0
    # BR corner pinned on paper (x + wrap, y + box_height unchanged)
    assert abs((data.x + data.wrap_width_mm) - br_x) < 0.5
    assert abs((data.y + data.box_height_mm) - br_y) < 0.5


def test_mr_drag_changes_only_wrap(qapp):
    """MR resize (fy==1): only wrap changes; y and box_height untouched."""
    from PyQt6.QtCore import QPointF
    scene, item, data = _resize_setup(qapp)
    orig_bh = data.box_height_mm
    b = item.manip_bounds()
    item.manip_scale((b.width() + 20.0) / b.width(), 1.0,
                     QPointF(b.x(), b.y() + b.height() / 2))   # anchor = ML
    assert abs(data.wrap_width_mm - 70.0) < 1.0
    assert abs(data.y - 10.0) < 0.01
    assert data.box_height_mm == orig_bh   # untouched (axis isolation)


def test_bm_drag_changes_only_box_height(qapp):
    """BM resize (fx==1): only box_height changes; wrap and x untouched."""
    from PyQt6.QtCore import QPointF
    scene, item, data = _resize_setup(qapp)
    orig_wrap = data.wrap_width_mm
    b = item.manip_bounds()
    item.manip_scale(1.0, (b.height() + 20.0) / b.height(),
                     QPointF(b.x() + b.width() / 2, b.y()))    # anchor = TM
    assert data.box_height_mm > 0
    assert abs(data.wrap_width_mm - orig_wrap) < 0.01
    assert abs(data.x - 10.0) < 0.01


def test_tm_drag_moves_y_shrinks_height_pins_bottom(qapp):
    """TM resize (+y): y moves down, box height shrinks, bottom edge pinned."""
    from PyQt6.QtCore import QPointF
    scene, item, data = _resize_setup(qapp, box_h=60.0)
    b = item.manip_bounds()
    bottom = b.y() + b.height()
    item.manip_scale(1.0, (b.height() - 5.0) / b.height(),
                     QPointF(b.x() + b.width() / 2, bottom))   # anchor = BM
    assert data.y > 10.0
    assert data.box_height_mm < 60.0
    assert abs((data.y + data.box_height_mm) - bottom) < 0.5   # bottom pinned


def test_box_height_clamps_at_content_height(qapp):
    """Shrinking box height below content clamps at the content height."""
    from PyQt6.QtCore import QPointF
    scene, item, data = _resize_setup(qapp, box_h=30.0)
    content_h_mm = item._content_height_mm()
    b = item.manip_bounds()
    item.manip_scale(1.0, 1.0 / b.height(),            # target 1 mm << content
                     QPointF(b.x() + b.width() / 2, b.y()))
    assert data.box_height_mm >= content_h_mm - 0.1


def test_width_clamps_at_min_wrap(qapp):
    """Shrinking wrap below the min clamps at MIN_TEXT_WRAP_WIDTH_MM."""
    from PyQt6.QtCore import QPointF
    from firepro3d.constants import MIN_TEXT_WRAP_WIDTH_MM
    scene, item, data = _resize_setup(qapp)
    b = item.manip_bounds()
    item.manip_scale(1.0 / b.width(), 1.0,             # target 1 mm << 5 mm min
                     QPointF(b.x(), b.y() + b.height() / 2))
    assert data.wrap_width_mm == MIN_TEXT_WRAP_WIDTH_MM


def test_box_resize_single_undo_restores_all_four(qapp):
    """A full manipulator TL resize gesture pushes one entry; undo restores
    x, y, wrap, box_height."""
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtWidgets import QGraphicsView
    from firepro3d.manip_math import HandleRole
    scene, item, data = _resize_setup(qapp, wrap=60.0, box_h=30.0)
    _view = QGraphicsView(scene)
    orig = (data.x, data.y, data.wrap_width_mm, data.box_height_mm)

    manip = scene._manipulator
    manip.rebake()
    r0 = QRectF(manip._rect)
    start = r0.topLeft()                               # TL drag anchors BR
    manip._begin("resize", start, QPointF(0, 0), HandleRole.TOP_LEFT)
    manip._moved = True
    manip._last_factors = ((r0.width() - 10.0) / r0.width(),
                           (r0.height() - 5.0) / r0.height())
    manip._finish(QPointF(start.x() + 10, start.y() + 5),
                  Qt.KeyboardModifier.NoModifier)

    assert scene._undo_stack.count() == 1
    scene._undo_stack.undo()
    assert abs(data.x - orig[0]) < 0.5
    assert abs(data.y - orig[1]) < 0.5
    assert abs(data.wrap_width_mm - orig[2]) < 0.5
    assert abs(data.box_height_mm - orig[3]) < 0.5


def test_font_height_untouched_by_resize(qapp):
    """No manip_scale touches height_mm (font size)."""
    from PyQt6.QtCore import QPointF
    scene, item, data = _resize_setup(qapp, height_mm=4.7625)
    orig_h = data.height_mm
    b = item.manip_bounds()
    item.manip_scale((b.width() + 10.0) / b.width(),
                     (b.height() + 10.0) / b.height(),
                     QPointF(b.x(), b.y()))
    assert abs(data.height_mm - orig_h) < 1e-9, "resize must never touch height_mm"


def test_box_height_mm_serialization_round_trip():
    """box_height_mm survives to_dict() → from_dict()."""
    d = TextAnnotationData(text="x", x=1.0, y=2.0, box_height_mm=25.5)
    out = TextAnnotationData.from_dict(d.to_dict())
    assert abs(out.box_height_mm - 25.5) < 1e-9


def test_box_height_mm_legacy_default():
    """from_dict on a dict missing box_height_mm defaults to 0.0."""
    out = TextAnnotationData.from_dict({"text": "x"})
    assert out.box_height_mm == 0.0


def test_boundingrect_grows_to_box_height(qapp):
    """boundingRect height grows to box_height_mm / scale when that exceeds content."""
    data = TextAnnotationData(text="x", height_mm=3.0, wrap_width_mm=50.0,
                              box_height_mm=100.0)
    item = TextAnnotationItem(data)
    br = item.boundingRect()
    scale = item.scale()
    expected_min_height = 100.0 / scale
    assert br.height() >= expected_min_height - 0.1


def test_boundingrect_auto_fits_when_box_height_zero(qapp):
    """When box_height_mm == 0, _box_rect_local() matches the natural text height.

    boundingRect() is padded with the grip halo (Fix 1, 2026-07-20), so it will
    be slightly larger than the natural text rect; we verify _box_rect_local()
    (the logical box) against the natural content rect instead.
    """
    from PyQt6.QtWidgets import QGraphicsTextItem
    data = TextAnnotationData(text="x", height_mm=3.0, wrap_width_mm=50.0,
                              box_height_mm=0.0)
    item = TextAnnotationItem(data)
    natural = QGraphicsTextItem.boundingRect(item)
    box = item._box_rect_local()
    assert abs(box.height() - natural.height()) < 0.01
    # boundingRect is padded beyond the box
    br = item.boundingRect()
    assert br.height() > box.height()


def test_selected_text_gets_manipulator_scale_handles(qapp):
    """A selected sheet-text item shows the manipulator's resize handles.

    (Replaces the retired per-item grip-press test: the item no longer owns the
    grips — the scene SelectionManipulator draws them when a single scalable
    item is selected.)
    """
    from PyQt6.QtWidgets import QGraphicsView
    from firepro3d.paper_space import PaperScene
    from firepro3d.manip_math import _RESIZE_ROLES
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 10, x=10.0, y=10.0, wrap_width_mm=50.0)
    item = TextAnnotationItem(data)
    scene.addItem(item)
    item.setPos(10.0, 10.0)
    _view = QGraphicsView(scene)
    item.setSelected(True)
    manip = scene._manipulator
    manip.rebake()
    assert item in manip.selection_items()
    # 8 resize handles are visible for the single scalable text item.
    assert all(manip._handles[role].isVisible() for role in _RESIZE_ROLES)


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


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1: boundingRect covers grip halo (stale drag trails, 2026-07-20)
# ─────────────────────────────────────────────────────────────────────────────

def test_bounding_rect_covers_grip_halo(qapp):
    # Painted extent (grips centred on box corners) must lie inside boundingRect,
    # or Qt leaves stale trails on drag (2026-07-20 smoke artifact).
    from firepro3d.constants import (SELECTION_GRIP_SIZE_MM,
                                     SELECTION_GRIP_OUTLINE_WIDTH_MM)
    item = TextAnnotationItem(TextAnnotationData(text="X", wrap_width_mm=50.0))
    s = item.scale() or 1.0
    halo = (SELECTION_GRIP_SIZE_MM / 2 + SELECTION_GRIP_OUTLINE_WIDTH_MM) / s
    box = item._box_rect_local()
    br = item.boundingRect()
    assert br.left() <= box.left() - halo + 1e-6
    assert br.top() <= box.top() - halo + 1e-6
    assert br.right() >= box.right() + halo - 1e-6
    assert br.bottom() >= box.bottom() + halo - 1e-6


def test_viewport_manip_bounds_within_bounding_rect(qapp):
    # Grips retired (Task 7): the SelectionManipulator now draws the frame +
    # handles as its own scene children.  The viewport's manip_bounds() (the
    # on-paper rect the frame wraps) must lie inside the item's boundingRect.
    from firepro3d.paper_space import SheetViewport, SheetViewData
    from PyQt6.QtCore import QRectF
    data = SheetViewData(source_view_type="unknown", source_view_name="none",
                         title="Test", scale=1.0,
                         x=0.0, y=0.0, w=100.0, h=80.0)
    resolver = _stub_resolver()
    vp = SheetViewport(data, resolver)
    vp.setSelected(True)
    br = vp.boundingRect()
    # manip_bounds is in scene coords; boundingRect is item-local at pos (0,0).
    mb = vp.manip_bounds().translated(-vp.pos())
    assert br.left() <= mb.left() + 1e-6
    assert br.top() <= mb.top() + 1e-6
    assert br.right() >= mb.right() - 1e-6
    assert br.bottom() >= mb.bottom() - 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# Fix 2: Inner text-box margin (TEXT_BOX_MARGIN_MM)
# ─────────────────────────────────────────────────────────────────────────────

def test_document_margin_applied_after_format(qapp):
    """document().documentMargin() equals TEXT_BOX_MARGIN_MM / scale after _apply_format."""
    import pytest
    from firepro3d.constants import TEXT_BOX_MARGIN_MM
    item = TextAnnotationItem(TextAnnotationData(text="Hello", wrap_width_mm=50.0))
    s = item.scale() or 1.0
    expected = TEXT_BOX_MARGIN_MM / s
    assert item.document().documentMargin() == pytest.approx(expected, abs=1e-6)


def test_document_margin_rescales_on_height_change(qapp):
    """Margin recomputes with new scale when height changes via set_property.

    set_property uses panel key "Height" (not field name "height_mm").
    Off-scene items go through the direct setattr+_apply_format path.
    """
    import pytest
    from firepro3d.constants import TEXT_BOX_MARGIN_MM
    item = TextAnnotationItem(TextAnnotationData(text="Hello", height_mm=3.0, wrap_width_mm=50.0))
    s_before = item.scale() or 1.0
    # Panel key is "Height" (not "height_mm") — see _text_panel_change
    item.set_property("Height", 6.0)
    s_after = item.scale() or 1.0
    assert abs(s_after - s_before) > 1e-6, "Scale should change when height changes"
    expected = TEXT_BOX_MARGIN_MM / s_after
    assert item.document().documentMargin() == pytest.approx(expected, abs=1e-6)
