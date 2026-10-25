"""SB2b G-M2 + blank-revert -- duplicate Mark look on the panel row; clearing a Mark is refused."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest

from firepro3d import marks
from firepro3d import theme as th
from firepro3d.property_manager import PropertyManager
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


def _doors(scene, n):
    w = WallSegment(QPointF(0, 0), QPointF(8000, 0), thickness_mm=200.0)
    w.level = scene.active_level
    scene.addItem(w)
    scene._walls.append(w)
    out = []
    for i in range(n):
        op = WallOpening(w, feature_id="door_914", offset_along=1000.0 + 2000 * i)
        op.level = w.level
        w.openings.append(op)
        scene.addItem(op)
        marks.mint(scene, op)
        out.append(op)
    return out


@pytest.fixture
def app_sheet(qapp):
    """The app stylesheet installed the way main.py does (the panel keeps its own sheet)."""
    old = qapp.styleSheet()
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    yield
    qapp.setStyleSheet(old)


def _panel(item):
    pm = PropertyManager()          # production: its own _field_qss on the form container
    pm.show_properties(item)
    return pm


def _commit(pm, text):
    edit = pm._prop_widgets["Mark"]
    edit.setText(text)
    edit.editingFinished.emit()


def _flag(pm):
    return pm._prop_widgets["Mark"].property("markDup")


def _show(pm, qapp):
    pm.resize(320, 600)
    pm.show()
    qapp.processEvents()


def _label_of(pm):
    return pm._form.labelForField(pm._prop_widgets["Mark"])


def _near(c, ref, tol=60):
    return abs(c.red() - ref.red()) + abs(c.green() - ref.green()) + abs(c.blue() - ref.blue()) < tol


def _inner_hits(widget, ref, inset=4):
    """Pixels near *ref* strictly inside *widget* (past the border), DPR-aware."""
    img = widget.grab().toImage()
    d = max(1, int(round(img.devicePixelRatio()))) * inset
    return sum(_near(QColor(img.pixel(x, y)), ref)
               for y in range(d, img.height() - d) for x in range(d, img.width() - d))


def test_duplicate_flags_row_with_count_tooltip_and_clears(qapp, shown_model_view):
    view, scene = shown_model_view
    d1, d2, d3 = _doors(scene, 3)
    pm = _panel(d2)
    _commit(pm, "D1")
    pm._do_refresh()
    edit = pm._prop_widgets["Mark"]
    assert edit.property("markDup") == "true"
    assert edit.toolTip() == "2 doors share Mark D1"
    pm.show_properties(d1)
    assert _flag(pm) == "true"
    pm.show_properties(d2)
    _commit(pm, "D9")
    pm._do_refresh()
    assert _flag(pm) in (None, "")


def test_warn_field_text_border_and_label_render_warn(qapp, app_sheet, shown_model_view):
    """Production cascade (app sheet + the panel's own): field text AND border and the
    label text are warn-coloured; the label keeps its height and has no card fill."""
    view, scene = shown_model_view
    d1, d2 = _doors(scene, 2)
    warn = QColor(th.detect().warn)
    uniq = _panel(d2)
    _show(uniq, qapp)
    base_h = _label_of(uniq).height()
    base_px = _label_of(uniq).grab().toImage().pixel(1, 1)
    ctl_field = _inner_hits(uniq._prop_widgets["Mark"], warn)      # control: unique = ink
    ctl_label = _inner_hits(_label_of(uniq), warn)
    marks.set_mark(d2, "D1")
    pm = _panel(d2)
    _show(pm, qapp)
    edit = pm._prop_widgets["Mark"]
    assert _inner_hits(edit, warn) > ctl_field + 10                              # glyph pixels are warn
    img = edit.grab().toImage()
    edge = [QColor(img.pixel(x, 0)) for x in range(img.width())] + \
           [QColor(img.pixel(x, img.height() - 1)) for x in range(img.width())]
    assert sum(_near(c, warn) for c in edge) > img.width() // 2     # border is warn
    lbl = _label_of(pm)
    assert _inner_hits(lbl, warn) > ctl_label + 10                               # label text is warn
    assert lbl.height() == base_h                                   # no card padding
    assert lbl.grab().toImage().pixel(1, 1) == base_px              # no warn_soft card fill


def test_blank_mark_is_refused_with_status(qapp, shown_model_view, monkeypatch):
    view, scene = shown_model_view
    (d1,) = _doors(scene, 1)
    msgs = []
    monkeypatch.setattr(scene, "_show_status", lambda m, timeout=5000: msgs.append((m, timeout)))
    pm = _panel(d1)
    _commit(pm, "   ")
    assert marks.get_mark(d1) == "D1"
    assert pm._prop_widgets["Mark"].text() == "D1"
    assert msgs == [("Mark can't be blank - restored to D1", 4000)]


def test_mixed_multiselect_blank_is_silent_unless_user_clears(qapp, shown_model_view, monkeypatch):
    view, scene = shown_model_view
    d1, d2 = _doors(scene, 2)
    msgs = []
    monkeypatch.setattr(scene, "_show_status", lambda m, timeout=5000: msgs.append(m))
    pm = PropertyManager()
    pm.show_properties([d1, d2])
    edit = pm._prop_widgets["Mark"]
    assert edit.placeholderText() == "< mixed >" and edit.text() == ""
    edit.editingFinished.emit()                    # tabbed through, untouched
    assert msgs == []
    QTest.keyClicks(edit, "  ")                    # the user really typed a blank
    edit.editingFinished.emit()
    assert msgs == ["Mark can't be blank - unchanged"]
    assert (marks.get_mark(d1), marks.get_mark(d2)) == ("D1", "D2")


def test_panel_mark_edit_is_one_undo_step(qapp, shown_model_view):
    view, scene = shown_model_view
    (d1,) = _doors(scene, 1)
    scene.push_undo_state()
    pm = _panel(d1)
    _commit(pm, "X7")
    scene.undo()
    assert marks.get_mark(scene._walls[0].openings[0]) == "D1"


def test_unchanged_mark_focus_out_pushes_no_undo_step(qapp, shown_model_view):
    view, scene = shown_model_view
    (d1,) = _doors(scene, 1)
    scene.push_undo_state()
    scene._dirty = False
    n = len(scene._undo_stack)
    pm = _panel(d1)
    _commit(pm, "D1")                              # focus-out on the same text
    assert len(scene._undo_stack) == n
    assert scene._dirty is False
    _commit(pm, "D5")                              # a real change still pushes one
    assert len(scene._undo_stack) == n + 1


def test_refresh_duplicates_flips_the_visible_row_without_a_selection_change(qapp, shown_model_view):
    view, scene = shown_model_view
    d1, d2 = _doors(scene, 2)
    d2.setSelected(True)
    pm = PropertyManager()
    scene.requestPropertyUpdate.connect(pm.show_properties)     # as main.py wires it
    pm.show_properties(d2)
    assert _flag(pm) in (None, "")
    marks.set_mark(d1, marks.get_mark(d2))        # a bulk change to a NON-selected element
    assert _flag(pm) in (None, "")                # stale until the refresh
    marks.refresh_duplicates(scene)
    assert _flag(pm) == "true"
    marks.set_mark(d1, "D9")
    marks.refresh_duplicates(scene)
    assert _flag(pm) in (None, "")


def test_paste_items_refreshes_the_panel(qapp, shown_model_view):
    view, scene = shown_model_view
    d1, d2 = _doors(scene, 2)
    d2.setSelected(True)
    seen = []
    scene.requestPropertyUpdate.connect(lambda sel: seen.append(sel))
    scene.paste_items(QPointF(0, 5000), data=scene._clipboard_item_dicts([scene._walls[0]]))
    assert any(s and d2 in s for s in seen)


def _paper_digest(scene, monkeypatch):
    import copy
    import hashlib
    from unittest.mock import MagicMock
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter
    import firepro3d.paper_display as pd
    from firepro3d.paper_space import Sheet, SheetViewData, PaperScene, ViewResolver

    monkeypatch.setattr(pd, "load_paper_categories",
                        lambda settings=None: copy.deepcopy(pd.factory_paper_categories()))
    monkeypatch.setattr(pd, "load_paper_color_mode",
                        lambda settings=None: pd.PaperColorMode.FULL_COLOR)
    monkeypatch.setattr(pd, "load_line_weights",
                        lambda settings=None: list(pd.FACTORY_LINE_WEIGHTS))
    crop = QRectF(-500.0, -2000.0, 9000.0, 4000.0)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (scene, QRectF(crop))
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"
    sheet.sheet_views = [SheetViewData("plan", "V", "V", 0.01, 60.0, 60.0, 90.0, 40.0)]
    paper = PaperScene(sheet, resolver)
    try:
        r = paper.sceneRect()
        img = QImage(int(r.width() * 4), int(r.height() * 4), QImage.Format.Format_RGB32)
        img.fill(0xFFFFFFFF)
        p = QPainter(img)
        paper.render(p, QRectF(0, 0, img.width(), img.height()), r,
                     Qt.AspectRatioMode.IgnoreAspectRatio)
        p.end()
        blank = QImage(img.size(), QImage.Format.Format_RGB32)
        blank.fill(0xFFFFFFFF)
        digest = hashlib.sha256(bytes(img.constBits().asarray(img.sizeInBytes()))).hexdigest()
        return digest, img != blank
    finally:
        paper.dispose()


def test_duplicates_never_reach_paper(qapp, shown_model_view, monkeypatch):
    """Same doors, unique vs duplicate Marks: the paper sheet is pixel-identical, while
    the on-screen panel does show the duplicate (so the guard is not vacuous)."""
    view, scene = shown_model_view
    d1, d2 = _doors(scene, 2)
    unique, has_content = _paper_digest(scene, monkeypatch)
    assert has_content
    marks.set_mark(d2, "D1")                      # now a duplicate pair
    pm = _panel(d2)
    assert _flag(pm) == "true"
    marks.refresh_duplicates(scene)
    dup, _ = _paper_digest(scene, monkeypatch)
    assert dup == unique


def test_held_refresh_runs_once_for_a_multi_paste_batch(qapp, shown_model_view):
    """Array pastes once per copy; the panel rebuild is synchronous, so it batches."""
    view, scene = shown_model_view
    d1, d2 = _doors(scene, 2)
    d2.setSelected(True)
    seen = []
    scene.requestPropertyUpdate.connect(lambda sel: seen.append(sel))
    data = scene._clipboard_item_dicts([scene._walls[0]])
    marks.hold_duplicate_refresh(scene)
    try:
        d2.setSelected(True)
        scene.paste_items(QPointF(0, 5000), data=data)
        scene.paste_items(QPointF(0, 6000), data=data)
        d2.setSelected(True)
    finally:
        n_before = len(seen)
        marks.release_duplicate_refresh(scene)
    assert len(seen) == n_before + 1
