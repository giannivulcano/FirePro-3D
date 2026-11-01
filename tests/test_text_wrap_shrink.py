"""Text Wrap / Shrink to fit (text-sizing design 2026-11-01, D4-D7, AC9-AC16).

Expected sizes come from a raw ``QTextDocument`` laid out the way the sizing
contract prescribes (D1: Arial at ``TEXT_METRIC_REF_PX``, scale = h / cap,
margin = padding / scale) -- never from ``TextItem`` itself.
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QTextDocument

from firepro3d.constants import TEXT_METRIC_REF_PX
from firepro3d.text_item import TextAnnotationData, TextItem

LONG = "alpha beta gamma delta epsilon zeta"


def _raw_doc(text, h=3.0, pad=1.0, wrap_mm=None):
    """Raw-Qt ground truth: ``(doc, scale)`` for *text* unwrapped (width =
    idealWidth) or wrapped at *wrap_mm* surface mm."""
    f = QFont("Arial")
    f.setPixelSize(TEXT_METRIC_REF_PX)
    s = h / QFontMetricsF(f).capHeight()
    doc = QTextDocument()
    doc.setDefaultFont(f)
    doc.setDocumentMargin(pad / s)
    doc.setPlainText(text)
    doc.setTextWidth(-1)
    doc.setTextWidth(doc.idealWidth() if wrap_mm is None else wrap_mm / s)
    return doc, s


def _lines(doc) -> int:
    doc.documentLayout().documentSize()
    n, b = 0, doc.begin()
    while b.isValid():
        n += b.layout().lineCount()
        b = b.next()
    return n


def _box(item) -> QRectF:
    """The drawn box in scene/paper mm (unrotated): grips TL..BR."""
    g = item.grip_points()
    return QRectF(g[0], g[4])


def _model(role="plan"):
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    ms = Model_Space(scene_role=role)
    ms._level_manager = LevelManager()
    return ms


def _add(ms, **kw):
    rec = dict(text=LONG, x=10.0, y=20.0, height_mm=3.0, cell_padding_mm=1.0)
    rec.update(kw)
    t = TextItem(TextAnnotationData(**rec))
    ms.addItem(t)
    ms._texts.append(t)
    ms.push_undo_state()
    return t


def _process():
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()


def _reformat(t):
    t.prepareGeometryChange()
    t._apply_format()


# ── T21: data model (D4) ────────────────────────────────────────────────────

@pytest.mark.parametrize("rec,wrap", [({"wrap_width_mm": 0.0}, False),
                                      ({"wrap_width_mm": 120.0}, True)])
def test_legacy_record_flags_are_absent_and_derived(qapp, rec, wrap):
    """AC15 / T-legacy: a pre-flag record loads with no stored flag; Wrap
    follows wrap_width_mm > 0, Shrink is off; nothing new is written."""
    d = TextAnnotationData.from_dict({"type": "text", "text": "Hi", **rec})
    assert (d.wrap, d.shrink) == (None, None)
    assert (d.wrap_on(), d.shrink_on()) == (wrap, False)
    out = d.to_dict()
    assert "wrap" not in out and "shrink" not in out


def test_bound_seed_is_shrink_on_wrap_off(qapp):
    """G12/G13: the bound-text legacy default is the hug (Shrink ON + Wrap
    OFF) even with an authored wrap width; off the block layer it is plain."""
    d = TextAnnotationData.from_dict({"text": "@[Name]", "wrap_width_mm": 13.9})
    assert (d.wrap_on(bound=True), d.shrink_on(bound=True)) == (False, True)
    assert (d.wrap_on(), d.shrink_on()) == (True, False)


@pytest.mark.parametrize("wrap,shrink", [(True, True), (True, False),
                                         (False, True), (False, False)])
def test_flags_round_trip_sparse(qapp, wrap, shrink):
    """AC16 / T-roundtrip: authored flags write and read back exactly."""
    d = TextAnnotationData(text="Hi", wrap_width_mm=30.0, wrap=wrap, shrink=shrink)
    out = d.to_dict()
    assert (out["wrap"], out["shrink"]) == (wrap, shrink)
    back = TextAnnotationData.from_dict(out)
    assert (back.wrap, back.shrink) == (wrap, shrink)
    item = TextItem.from_dict(out)
    assert (item.to_dict()["wrap"], item.to_dict()["shrink"]) == (wrap, shrink)


# ── T22: Wrap OFF layout (D5, G2) ───────────────────────────────────────────

def test_wrap_off_lays_out_one_line_and_wrap_on_restores_the_width(qapp):
    """AC10 / T-wrap-off: Wrap OFF -> one line, width = longest line + 2 pad;
    the authored wrap width is kept and Wrap ON restores it."""
    ms = _model()
    t = _add(ms, wrap_width_mm=20.0)
    wrapped, _s = _raw_doc(LONG, wrap_mm=20.0)
    assert _lines(t.document()) == _lines(wrapped) > 1
    assert _box(t).width() == pytest.approx(20.0, abs=1e-6)
    t.data.wrap = False
    _reformat(t)
    one, s = _raw_doc(LONG)
    assert _lines(t.document()) == 1
    assert _box(t).width() == pytest.approx(one.idealWidth() * s, abs=1e-6)
    assert t.data.wrap_width_mm == 20.0
    t.data.wrap = True
    _reformat(t)
    assert _box(t).width() == pytest.approx(20.0, abs=1e-6)
    assert _lines(t.document()) == _lines(wrapped)


def test_wrap_off_breaks_only_at_a_typed_enter(qapp):
    """G2: with Wrap OFF the only line breaks are the typed ones."""
    ms = _model()
    t = _add(ms, text="alpha beta gamma\ndelta", wrap_width_mm=6.0, wrap=False)
    assert _lines(t.document()) == 2


# ── T23: Shrink sizing (D5, G3) ─────────────────────────────────────────────

def test_shrink_hugs_both_axes_wrap_off(qapp):
    """AC11 / T-shrink: Shrink ON + Wrap OFF -> box = one-line content + pad
    on both axes; the authored 12 mm height floor is ignored."""
    ms = _model()
    t = _add(ms, text="Short", wrap_width_mm=40.0, box_height_mm=12.0,
             wrap=False, shrink=True)
    doc, s = _raw_doc("Short")
    b = _box(t)
    assert b.width() == pytest.approx(doc.idealWidth() * s, abs=1e-6)
    assert b.height() == pytest.approx(doc.size().height() * s, abs=1e-6)


def test_shrink_with_wrap_hugs_the_widest_wrapped_line(qapp):
    """G3: Shrink ON + Wrap ON -> the lines break at the wrap width and the
    box is as wide as the widest of them (idealWidth of the wrapped raw doc);
    the authored 60 mm height floor is ignored."""
    ms = _model()
    t = _add(ms, wrap_width_mm=20.0, box_height_mm=60.0, wrap=True, shrink=True)
    doc, s = _raw_doc(LONG, wrap_mm=20.0)
    b = _box(t)
    assert _lines(t.document()) == _lines(doc) > 1
    assert b.width() == pytest.approx(doc.idealWidth() * s, abs=1e-6)
    assert b.width() < 20.0
    assert b.height() == pytest.approx(doc.size().height() * s, abs=1e-6)
    assert b.height() < 60.0


# ── T24: Shrink keeps the authored alignment point (D5) ─────────────────────

@pytest.mark.parametrize("align,valign,anchor", [
    ("L", "T", (10.0, 20.0)),               # authored top-left
    ("C", "M", (30.0, 26.0)),               # authored centre
    ("R", "B", (50.0, 32.0)),               # authored bottom-right
])
def test_shrink_keeps_the_authored_alignment_point(qapp, align, valign, anchor):
    """AC11 / T-shrink: raw source = the authored box (10, 20, 40 x 12); the
    hugged box's align x valign point sits on the authored box's, before and
    after the text changes."""
    ms = _model()
    t = _add(ms, text="Short", wrap_width_mm=40.0, box_height_mm=12.0,
             align=align, valign=valign, wrap=False, shrink=True)
    fx = {"L": 0.0, "C": 0.5, "R": 1.0}[align]
    fy = {"T": 0.0, "M": 0.5, "B": 1.0}[valign]
    for text in ("Short", "A much longer value"):
        t.set_property("Content", text)
        b = _box(t)
        doc, s = _raw_doc(text)
        assert b.width() == pytest.approx(doc.idealWidth() * s, abs=1e-6)
        got = (b.left() + fx * b.width(), b.top() + fy * b.height())
        assert got == pytest.approx(anchor, abs=1e-6)


def test_shrink_offset_never_reaches_data_xy(qapp):
    """T-shrink-anchor-probe: the hug moves the drawn box by a LOCAL offset;
    pos() and data.x/y stay the authored origin through value changes, a
    save and an itemChange position sync."""
    ms = _model()
    t = _add(ms, text="Short", wrap_width_mm=40.0, box_height_mm=12.0,
             align="C", valign="M", wrap=False, shrink=True)
    for text in ("Short", "A much longer value", "x"):
        t.set_property("Content", text)
        t.setPos(QPointF(15.0, 25.0))        # a REAL move: itemChange live-sync fires
        assert (t.data.x, t.data.y) == pytest.approx((15.0, 25.0), abs=1e-9)
        t.setPos(QPointF(10.0, 20.0))        # ... and back to the authored origin
        d = t.to_dict()
        assert (t.pos().x(), t.pos().y()) == pytest.approx((10.0, 20.0), abs=1e-9)
        assert (d["x"], d["y"]) == pytest.approx((10.0, 20.0), abs=1e-9)
    assert _box(t).left() > 10.0             # the drawn box did move off the origin


def test_shrink_glyphs_and_caret_follow_the_box(qapp):
    """D5: glyphs, caret and hit-test ride the same offset as the box."""
    ms = _model()
    t = _add(ms, text="Short", wrap_width_mm=40.0, box_height_mm=12.0,
             align="C", valign="M", wrap=False, shrink=True)
    r = t._box_rect_local()
    g = t._glyph_outline_local().boundingRect()
    assert r.contains(g)
    k = t.caret_rect_local()
    assert r.contains(QPointF(k.x(), k.center().y()))
    first = t.content_rects_local()[0]
    assert t.cursor_position_at(QPointF(first.left() + 0.01 / t.scale(),
                                        first.center().y())) == 0


def test_rotated_shrink_box_keeps_the_rotated_authored_anchor(qapp):
    """Edge (rotated): a right-middle anchored box rotated 90 turns about the
    authored box's centre. Raw source: authored box (10, 20, 40 x 12), centre
    (30, 26), right-middle (50, 26) -> rotated +90 (Y-up CCW = Qt -90) about
    the centre = (30, 6)."""
    ms = _model()
    t = _add(ms, text="Short", wrap_width_mm=40.0, box_height_mm=12.0,
             align="R", valign="M", wrap=False, shrink=True, angle=90.0)
    t.set_angle(90.0)
    g = t.grip_points()
    assert (g[3].x(), g[3].y()) == pytest.approx((30.0, 6.0), abs=1e-6)   # RM grip


# ── T25: paper paint at the offset (D5) ─────────────────────────────────────

def _paper():
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    return PaperScene(Sheet.create_default(), ViewResolver(None, None, None, None))


def _paper_text(sc, **kw):
    from firepro3d.paper_commands import _find_text_item
    rec = dict(text="Short", x=100.0, y=100.0, height_mm=3.0, cell_padding_mm=1.0,
               wrap_width_mm=40.0, box_height_mm=12.0, align="C", valign="M",
               color="#000000", wrap=False, shrink=True)
    rec.update(kw)
    data = TextAnnotationData(**rec)
    sc._do_add_annotation(data)
    return data, _find_text_item(sc, data)


def _ink(scene, src: QRectF, px_per_mm=8):
    w, h = int(src.width() * px_per_mm), int(src.height() * px_per_mm)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), src)
    p.end()
    xs = [x for y in range(h) for x in range(w) if QColor(img.pixel(x, y)).lightness() < 128]
    ys = [y for y in range(h) for x in range(w) if QColor(img.pixel(x, y)).lightness() < 128]
    return (src.left() + min(xs) / px_per_mm, src.top() + min(ys) / px_per_mm,
            src.left() + (max(xs) + 1) / px_per_mm, src.top() + (max(ys) + 1) / px_per_mm)


def test_paper_shrink_paints_the_glyphs_centred_on_the_authored_box(qapp):
    """D5 paper: the native document paint lands at the Shrink offset -- the
    inked glyphs of a centred hug are centred on the authored box centre
    (100 + 20 = 120 mm), inside the authored box, and unclipped (same ink
    width as the same text drawn at the origin with no hug)."""
    sc = _paper()
    data, it = _paper_text(sc)
    src = QRectF(90.0, 95.0, 60.0, 22.0)
    x0, y0, x1, y1 = _ink(sc, src)
    assert (x0 + x1) / 2.0 == pytest.approx(120.0, abs=0.25)
    assert 100.0 <= y0 and y1 <= 112.0
    ref = _paper()
    _paper_text(ref, align="L", valign="T", wrap=False, shrink=False)
    r0, _t, r1, _b = _ink(ref, src)
    assert x1 - x0 == pytest.approx(r1 - r0, abs=0.13)


# ── T26: paper inline edit through the offset (D5) ──────────────────────────

def test_paper_edit_click_on_the_first_glyph_puts_the_caret_first(qapp):
    """D5 paper edit: a click on the shifted first glyph lands at position 0
    (the native control would map it to the unshifted document)."""
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QGraphicsView
    sc = _paper()
    data, it = _paper_text(sc, text="Shift me")
    view = QGraphicsView(sc)
    view.resize(600, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    try:
        view.scale(5.0, 5.0)
        view.centerOn(it)
        it.begin_edit()
        cur = it.textCursor()
        cur.setPosition(len(it.toPlainText()))
        it.setTextCursor(cur)
        r0 = it.content_rects_local()[0]
        first = it.mapToScene(QPointF(r0.left() + 0.2 / it.scale(), r0.center().y()))
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, view.mapFromScene(first))
        assert it.textCursor().position() == 0
    finally:
        it.commit_edit()
        view.close()


# ── T27: a grip drag on a Shrink box (D6, G4, G14) ──────────────────────────

def test_grip_drag_on_shrink_box_sets_size_turns_shrink_off_one_undo(qapp):
    """AC12 / T-drag-off: a posted BR-grip drag on a Shrink box -> Shrink
    OFF, the dragged size, one undo step that restores both."""
    from tests._snap_polish_helpers import close_view, drag, make_view
    view, ms = make_view(role="plan", scale=10.0)
    try:
        ms._snap_engine.enabled = False
        t = _add(ms, text="Short", x=-20.0, y=-10.0, wrap_width_mm=40.0,
                 box_height_mm=12.0, align="C", valign="M", wrap=False, shrink=True)
        b0 = _box(t)
        t.setSelected(True)
        _process()
        p0 = ms._undo_pos
        br = t.grip_points()[4]
        # The drag lands on the editor's whole-mm input grid: aim at a grid point.
        target = QPointF(round(br.x() + 6.0), round(br.y() + 4.0))
        drag(view, br, target)
        _process()
        t = ms._texts[0]
        assert t.data.shrink is False and t.data.wrap is True
        b1 = _box(t)
        assert (b1.left(), b1.top()) == pytest.approx((b0.left(), b0.top()), abs=1e-6)
        assert (b1.right(), b1.bottom()) == pytest.approx((target.x(), target.y()), abs=1e-6)
        assert ms._undo_pos == p0 + 1
        ms.undo()
        t = ms._texts[0]
        assert t.data.shrink is True and t.data.wrap is False
        assert (_box(t).left(), _box(t).top()) == pytest.approx((b0.left(), b0.top()), abs=1e-6)
        assert (_box(t).width(), _box(t).height()) == pytest.approx((b0.width(), b0.height()), abs=1e-6)
    finally:
        close_view(view, ms)


def test_width_drag_on_wrap_off_box_turns_wrap_on_at_the_width(qapp):
    """AC13 / G14: a right-mid width drag on a Wrap-OFF box -> Wrap ON at the
    dragged width, one undo step."""
    from tests._snap_polish_helpers import close_view, drag, make_view
    view, ms = make_view(role="plan", scale=10.0)
    try:
        ms._snap_engine.enabled = False
        t = _add(ms, x=-30.0, y=-5.0, wrap_width_mm=20.0, wrap=False)
        w0 = _box(t).width()
        t.setSelected(True)
        _process()
        p0 = ms._undo_pos
        rm = t.grip_points()[3]
        target = QPointF(round(rm.x() - w0 / 2.0), rm.y())     # whole-mm input grid
        want = target.x() - _box(t).left()
        drag(view, rm, target)
        _process()
        t = ms._texts[0]
        assert t.data.wrap is True
        assert t.data.wrap_width_mm == pytest.approx(want, abs=1e-6)
        assert _box(t).width() == pytest.approx(want, abs=1e-6)
        assert _lines(t.document()) > 1
        assert ms._undo_pos == p0 + 1
        ms.undo()
        assert ms._texts[0].data.wrap is False
    finally:
        close_view(view, ms)


# ── T28: sheet resize (ResizeTextBoxCommand carries the flags) ──────────────

def test_sheet_resize_on_shrink_box_one_command_restores_flags(qapp):
    """AC12 sheet: a manipulator resize gesture on a Shrink sheet text ->
    one ResizeTextBoxCommand; Shrink OFF + Wrap ON; undo restores both."""
    from PyQt6.QtWidgets import QGraphicsView
    from firepro3d.manip_handle import HandleRole
    sc = _paper()
    data, it = _paper_text(sc)
    it.setSelected(True)
    _view = QGraphicsView(sc)
    manip = sc._manipulator
    manip.rebake()
    assert it in manip.selection_items()
    idx0 = sc.undo_stack.index()
    r0 = QRectF(manip._rect)
    start = r0.bottomRight()
    manip._begin("resize", start, QPointF(0, 0), HandleRole.BOTTOM_RIGHT)
    manip._moved = True
    manip._last_factors = ((r0.width() + 10.0) / r0.width(),
                           (r0.height() + 5.0) / r0.height())
    manip._finish(QPointF(start.x() + 10, start.y() + 5), Qt.KeyboardModifier.NoModifier)
    assert sc.undo_stack.index() == idx0 + 1
    assert data.shrink is False and data.wrap is True
    assert data.wrap_width_mm == pytest.approx(r0.width() + 10.0, abs=1e-3)
    sc.undo_stack.undo()
    assert (data.wrap, data.shrink) == (False, True)
    assert (data.x, data.y) == pytest.approx((100.0, 100.0), abs=1e-9)


# ── T29: constraint write (_TextBoxAdapter, D59) ────────────────────────────

def test_constraint_width_write_on_shrink_box_sets_size_shrink_off(qapp):
    """AC12 constraint: a solved width on a Shrink box writes it as the wrap
    width, Shrink OFF, Wrap ON; the solved centre holds."""
    from firepro3d.sketch_adapters import _TextBoxAdapter
    ms = _model(role="block_editor")
    t = _add(ms, text="Short", wrap_width_mm=40.0, box_height_mm=12.0,
             align="C", valign="M", wrap=False, shrink=True)
    a = _TextBoxAdapter()
    cx, cy, w, h = a.read(t)
    a.write(t, [cx, cy, w + 8.0, h])
    assert (t.data.shrink, t.data.wrap) == (False, True)
    assert t.data.wrap_width_mm == pytest.approx(w + 8.0, abs=1e-6)
    assert a.read(t) == pytest.approx([cx, cy, w + 8.0, h], abs=1e-6)


def test_constraint_move_of_shrink_box_keeps_shrink(qapp):
    """A pure centre move of a Shrink box translates it and keeps the hug;
    the authored origin moves by the same delta (raw: 10 + 5, 20 - 3)."""
    from firepro3d.sketch_adapters import _TextBoxAdapter
    ms = _model(role="block_editor")
    t = _add(ms, text="Short", wrap_width_mm=40.0, box_height_mm=12.0,
             align="C", valign="M", wrap=False, shrink=True)
    a = _TextBoxAdapter()
    cx, cy, w, h = a.read(t)
    a.write(t, [cx + 5.0, cy - 3.0, w, h])
    assert t.data.shrink is True
    assert a.read(t) == pytest.approx([cx + 5.0, cy - 3.0, w, h], abs=1e-6)
    assert (t.data.x, t.data.y) == pytest.approx((15.0, 17.0), abs=1e-6)


# ── T30: bound text seeds the hug through the record (D5, G12) ──────────────

def test_hugged_record_freezes_the_seeded_flags_and_keeps_the_authored_box(qapp):
    """AC14: hugged_text_record writes the bound seed (Shrink ON + Wrap OFF)
    explicitly and keeps the authored box fields (D4) -- no geometry rewrite."""
    from firepro3d.block_attributes import hugged_text_record
    rec = {"type": "text", "text": "@[Name]", "x": -6.95, "y": -3.5,
           "wrap_width_mm": 13.9, "box_height_mm": 7.0}
    out = hugged_text_record(rec, "Office")
    assert (out["text"], out["wrap"], out["shrink"]) == ("Office", False, True)
    assert (out["x"], out["y"], out["wrap_width_mm"], out["box_height_mm"]) == \
        (-6.95, -3.5, 13.9, 7.0)
    off = hugged_text_record({**rec, "shrink": False}, "Office")
    assert (off["wrap"], off["shrink"]) == (True, False)    # G12: Shrink OFF = fixed wrapping box
    static = {"type": "text", "text": "Plain", "wrap_width_mm": 13.9}
    assert hugged_text_record(static, None) is static


def test_bound_text_with_shrink_off_wraps_in_the_authored_box(qapp):
    """AC14: the author turned Shrink off on a bound tag -> the long value
    wraps inside the authored 13.9 mm box (raw wrapped-doc height)."""
    from firepro3d.block_attributes import bound_text_ops, normalise_attr
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.render_op import STROKE
    prim = {"type": "text", "text": "@[Name]", "x": -6.95, "y": -3.5, "height_mm": 3.0,
            "wrap_width_mm": 13.9, "box_height_mm": 7.0, "align": "C", "valign": "M",
            "border": True, "cell_padding_mm": 1.0, "shrink": False}
    d = BlockDefinition.new(name="FixedTag", library="", series="", origin=(0.0, 0.0),
                            primitives=[prim])
    d.attributes = [normalise_attr({"key": "Name", "default": "Mechanical Equipment Room"})]
    ops, _c = bound_text_ops(d, {}, None, False, 1.0, None, None)
    f = [o for o in ops if o.kind == STROKE][0].path.boundingRect()
    doc, s = _raw_doc("Mechanical Equipment Room", wrap_mm=13.9)
    assert _lines(doc) > 1
    assert f.width() == pytest.approx(13.9, abs=0.05)
    assert f.height() == pytest.approx(max(7.0, doc.size().height() * s), abs=0.05)


def test_hide_empty_collapse_reads_the_authored_box(qapp):
    """SB4a D7 kept: the Hide-when-empty collapse measures each bound line's
    AUTHORED box, not its hug -- even with Shrink ON stored on the record.
    Raw source: line A authored at y 2..12 (box height 10, a 3 mm line
    inside), line B at 14..24; A blank and dropped -> B moves in by A's slot,
    near edge 14 to near edge 2 = -12."""
    from PyQt6.QtGui import QTransform
    from firepro3d.block_attributes import hide_empty_shifts
    a = {"type": "text", "text": "@[A]", "x": 0.0, "y": 2.0, "height_mm": 3.0,
         "wrap_width_mm": 20.0, "box_height_mm": 10.0, "align": "C", "valign": "B",
         "hide_empty": True, "shrink": True}           # a hug would sit at the slot's bottom
    b = {**a, "text": "@[B]", "y": 14.0, "hide_empty": False, "shrink": False}
    got = hide_empty_shifts([(a, QTransform()), (b, QTransform())], frozenset({"A"}))
    assert got[0] is None
    assert got[1] == pytest.approx(-12.0, abs=1e-6)


# ── T31: explode / legacy note map (D6) ─────────────────────────────────────

def test_explode_copies_the_flags_and_scales_the_sizes(qapp, make_model_space):
    """AC16 explode: a static text's authored flags survive explode, and the
    scaled record (DD9) keeps them while its sizes scale x2."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_explode import explode_instances
    ms = make_model_space()
    prim = {"type": "text", "text": "Static", "x": 0.0, "y": 0.0, "height_mm": 3.0,
            "wrap_width_mm": 30.0, "box_height_mm": 10.0, "align": "C", "valign": "M",
            "wrap": True, "shrink": True}
    d = BlockDefinition.new(name="FlagTag", library="", series="", origin=(0.0, 0.0),
                            primitives=[prim])
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (100.0, 50.0), scale=2.0)
    made = explode_instances(ms, [inst], flatten=True)
    t = [m for m in made if isinstance(m, TextItem)][0]
    assert (t.data.wrap, t.data.shrink) == (True, True)
    assert t.data.wrap_width_mm == pytest.approx(60.0)
    assert (t.to_dict()["wrap"], t.to_dict()["shrink"]) == (True, True)


def test_exploded_shrink_text_lands_in_the_drawn_box(qapp, make_model_space):
    """Explode parity: a static Shrink text explodes to the box it is drawn
    in (the block's border op), at the instance origin."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_explode import explode_instances
    from firepro3d.render_op import STROKE
    ms = make_model_space()
    prim = {"type": "text", "text": "Static", "x": -20.0, "y": -6.0, "height_mm": 3.0,
            "wrap_width_mm": 40.0, "box_height_mm": 12.0, "align": "C", "valign": "M",
            "border": True, "cell_padding_mm": 1.0, "wrap": False, "shrink": True}
    d = BlockDefinition.new(name="HugStatic", library="", series="", origin=(0.0, 0.0),
                            primitives=[prim])
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (100.0, 50.0))
    drawn = [o for o in inst.render_ops() if o.kind == STROKE][0].path.boundingRect()
    assert drawn.center().x() == pytest.approx(0.0, abs=1e-6)        # authored centre
    made = explode_instances(ms, [inst], flatten=True)
    g = [m for m in made if isinstance(m, TextItem)][0].grip_points()
    assert (g[4] - g[0]).x() == pytest.approx(drawn.width(), abs=1e-6)
    assert (g[8].x(), g[8].y()) == pytest.approx((100.0 + drawn.center().x(),
                                                  50.0 + drawn.center().y()), abs=1e-6)


@pytest.mark.parametrize("tw,wrap", [(0, False), (80.0, True)])
def test_legacy_note_maps_wrap_from_its_text_width(qapp, tw, wrap):
    """AC15 / T-legacy: a legacy "note" record maps text_width to the derived
    Wrap (no stored flag, nothing new written)."""
    from firepro3d.network_codec import deserialize_note
    ms = _model()
    item = deserialize_note(ms, {"type": "note", "x": 0.0, "y": 0.0, "text_width": tw,
                                 "properties": {"Text": "Legacy note"}})
    assert (item.data.wrap, item.data.shrink) == (None, None)
    assert (item.wrap_on(), item.shrink_on()) == (wrap, False)
    out = item.to_dict()
    assert "wrap" not in out and "shrink" not in out


# ── T32: model / Block Editor panel toggles (D7) ────────────────────────────

@pytest.mark.parametrize("role", ["plan", "block_editor"])
def test_model_panel_wrap_and_shrink_rows_are_undo_routed(qapp, role):
    """AC9 model + Block Editor: bool rows, one undo step per commit."""
    ms = _model(role)
    t = _add(ms, wrap_width_mm=20.0)
    props = t.get_properties()
    assert props["Wrap"] == {"type": "bool", "value": True}
    assert props["Shrink to fit"] == {"type": "bool", "value": False}
    p0 = ms._undo_pos
    t.set_property("Wrap", False)
    assert ms._undo_pos == p0 + 1 and t.data.wrap is False
    t.set_property("Shrink to fit", True)
    assert ms._undo_pos == p0 + 2 and t.data.shrink is True
    t.set_property("Shrink to fit", True)                     # no-op: no step
    assert ms._undo_pos == p0 + 2
    ms.undo()
    ms.undo()
    t = ms._texts[0]
    assert (t.data.wrap, t.data.shrink) == (None, None)
    assert t.get_properties()["Wrap"]["value"] is True


def test_wrap_on_seeds_the_width_from_the_drawn_box(qapp):
    """D7: Wrap ON on a box with no authored width wraps at the width it is
    drawn at -- nothing moves."""
    ms = _model()
    t = _add(ms, wrap_width_mm=0.0)
    w0 = _box(t).width()
    t.set_property("Wrap", True)
    assert t.data.wrap is True
    assert t.data.wrap_width_mm == pytest.approx(w0, abs=1e-6)
    assert _box(t).width() == pytest.approx(w0, abs=1e-6)
    assert _lines(t.document()) == 1


def test_shrink_on_keeps_the_wrap_it_hugs(qapp):
    """G3: Shrink ON on a wrapping box freezes Wrap ON -- it hugs the wrapped
    lines rather than unwrapping."""
    ms = _model()
    t = _add(ms, wrap_width_mm=20.0, box_height_mm=30.0)
    t.set_property("Shrink to fit", True)
    assert (t.data.wrap, t.data.shrink) == (True, True)
    assert _lines(t.document()) > 1


# ── T33: sheet panel toggles (D7) ───────────────────────────────────────────

def test_sheet_panel_wrap_and_shrink_rows_are_undo_routed(qapp):
    """AC9 sheet: bool rows; a commit is one FormatTextCommand and undo
    restores every field it wrote (Wrap ON also seeds the width)."""
    sc = _paper()
    data, it = _paper_text(sc, wrap=None, shrink=None, wrap_width_mm=0.0,
                           box_height_mm=0.0, align="L", valign="T")
    props = it.get_properties()
    assert props["Wrap"] == {"type": "bool", "value": False}
    assert props["Shrink to fit"] == {"type": "bool", "value": False}
    w0 = _box(it).width()
    i0 = sc.undo_stack.index()
    it.set_property("Wrap", True)
    assert sc.undo_stack.index() == i0 + 1
    assert data.wrap is True and data.wrap_width_mm == pytest.approx(w0, abs=1e-6)
    sc.undo_stack.undo()
    assert (data.wrap, data.wrap_width_mm) == (None, 0.0)
    it.set_property("Shrink to fit", True)
    assert sc.undo_stack.index() == i0 + 1 and data.shrink is True
