"""V Align Middle centres the ink (notes design N6 to N8, guard G2). Every gap is measured
from what is drawn: pixels of a real TextItem paint, and the real bound_text_ops paths."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFont, QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from firepro3d.block_attributes import bound_text_ops, normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
from firepro3d.render_op import TEXT
from firepro3d.text_item import TextAnnotationData, TextItem

FONTS = ["Arial", "Times New Roman", "Consolas"]
TEXTS = ["HEIGHT", "Typical gyp", "gyp\nHEIGHT"]
PX_PER_MM = 16
TOL_MM = 0.15


def _text(text, box_h=60.0, valign="M", font="Arial"):
    return TextItem(TextAnnotationData(text=text, x=0.0, y=0.0, height_mm=10.0,
                                       wrap_width_mm=120.0, box_height_mm=box_h,
                                       valign=valign, font_family=font, color="#000000"))


def _ink_gaps(item):
    """Paint *item* on white and read its ink rows: (mm above the ink, mm below it)."""
    box = item.manip_bounds()
    h = int(round(box.height() * PX_PER_MM))
    img = QImage(int(round(box.width() * PX_PER_MM)), h, QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.white)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    s = item.scale()
    p.scale(PX_PER_MM * s, PX_PER_MM * s)
    item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    rows = [y for y in range(h)
            if any(img.pixelColor(x, y).lightness() < 128 for x in range(img.width()))]
    assert rows, "nothing painted"
    return rows[0] / PX_PER_MM, (h - 1 - rows[-1]) / PX_PER_MM


@pytest.mark.parametrize("font", FONTS)
@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("box_h", [60.0, 0.0])
def test_painted_ink_gaps_are_equal_at_middle(qapp, font, text, box_h):
    above, below = _ink_gaps(_text(text, box_h, font=font))
    assert above == pytest.approx(below, abs=TOL_MM)


def _bound_gaps(text, font):
    """Ink gaps from the real placement ops: the glyph path against the border path."""
    d = BlockDefinition.new(name="T", library="", series="", origin=(0.0, 0.0), primitives=[
        {"type": "text", "text": "@[Name]", "x": 0.0, "y": 0.0, "height_mm": 10.0,
         "valign": "M", "font_family": font, "border": True, "color": "#000000"}])
    d.attributes = [normalise_attr({"key": "Name", "default": text})]
    ops, _cache = bound_text_ops(d, {}, None, False, 1.0, None, None,
                                 patch={"wrap_width_mm": 120.0, "box_height_mm": 60.0})
    glyphs = [o for o in ops if o.kind == TEXT]
    frame = [o for o in ops if o.kind != TEXT]
    assert len(glyphs) == 1 and frame
    ink, box = glyphs[0].path.boundingRect(), frame[0].path.boundingRect()
    assert box.height() == pytest.approx(60.0, abs=0.5)
    return ink.top() - box.top(), box.bottom() - ink.bottom()


@pytest.mark.parametrize("font", FONTS)
@pytest.mark.parametrize("text", ["HEIGHT", "Typical gyp"])
def test_a_note_box_with_a_patch_is_typed_text_and_centres(qapp, font, text):
    """A Note's words are typed, though they travel as a field: the patch marks them."""
    above, below = _bound_gaps(text, font)
    assert above == pytest.approx(below, abs=TOL_MM)


def test_the_compiled_outline_is_centred_too(qapp):
    item = _text("Typical gyp")
    ink = item.render_outline_path().boundingRect()
    box = item._box_rect_local()
    above, below = ink.top() - box.top(), box.bottom() - ink.bottom()
    assert above * item.scale() == pytest.approx(below * item.scale(), abs=0.02)


def test_the_measure_follows_the_typed_text(qapp):
    """The baseline moves with the content (user ruling): a stale cache would keep it."""
    item = _text("HEIGHT")
    caps = item._layout_offsets().voff
    item.setPlainText("gyp")
    item.sync_data_from_item()
    above, below = _ink_gaps(item)
    assert above == pytest.approx(below, abs=TOL_MM)
    assert item._layout_offsets().voff != pytest.approx(caps, abs=0.01)


def test_the_measure_follows_a_font_change(qapp):
    item = _text("Typical gyp", font="Arial")
    arial = item._ink_band()
    item.set_property("Font", "Consolas")
    assert item._ink_band() != arial
    above, below = _ink_gaps(item)
    assert above == pytest.approx(below, abs=TOL_MM)


def test_the_measure_follows_a_bare_font_swap(qapp):
    """setFont alone leaves the document revision: the key must carry the font."""
    item = _text("Typical gyp", font="Arial")
    arial = item._ink_band()
    font = QFont(item.font())
    font.setFamily("Consolas")
    item.setFont(font)
    assert item._ink_band() != arial


def test_the_measure_follows_a_reflow(qapp):
    item = _text("WORD WORD WORD")
    one = item._ink_band()
    item.setTextWidth(item.textWidth() / 3.0)
    assert item._ink_band() != one


def test_the_ink_measure_is_cached(qapp, monkeypatch):
    item = _text("HEIGHT")
    item._layout_offsets()
    calls = []
    real = TextItem._glyph_outline_at
    monkeypatch.setattr(TextItem, "_glyph_outline_at",
                        lambda self, o: calls.append(1) or real(self, o))
    for _ in range(5):
        item._layout_offsets()
    assert calls == []


@pytest.mark.parametrize("valign, slack", [("T", 0.0), ("B", 1.0)])
def test_top_and_bottom_keep_their_line_box_rule(qapp, valign, slack):
    """Top and Bottom are unchanged: the same offset, by the raw content height."""
    item = _text("Typical gyp", valign=valign)
    room = item._box_rect_local().height() - QTextItemHeight(item)
    assert item._layout_offsets().voff == pytest.approx(room * slack, abs=1e-6)


def QTextItemHeight(item):
    """The document's own height, past TextItem's boundingRect override."""
    return item.document().size().height()


def test_empty_text_keeps_the_line_box_rule(qapp):
    item = _text("")
    room = item._box_rect_local().height() - QTextItemHeight(item)
    assert item._layout_offsets().voff == pytest.approx(room / 2.0, abs=1e-6)


def test_sheet_text_keeps_the_line_box_rule(qapp):
    """N8: sheet text has no V Align row and its paint ignores the offset."""
    p = PaperScene(Sheet.create_default(), ViewResolver(None, None, None, None))
    item = _text("Typical gyp")
    p.addItem(item)
    room = item._box_rect_local().height() - QTextItemHeight(item)
    assert item._layout_offsets().voff == pytest.approx(room / 2.0, abs=1e-6)


def _tag(values):
    """Glyph tops of one placed @[Name] tag per value, from the real ops."""
    tops = []
    for value in values:
        d = BlockDefinition.new(name="T", library="", series="", origin=(0.0, 0.0), primitives=[
            {"type": "text", "text": "@[Name]", "x": 0.0, "y": 0.0, "height_mm": 10.0,
             "valign": "M", "font_family": "Arial", "box_height_mm": 20.0}])
        d.attributes = [normalise_attr({"key": "Name", "default": value})]
        ops, _cache = bound_text_ops(d, {"Name": value}, None, False, 1.0, None, None)
        tops.append([o for o in ops if o.kind == TEXT][0].path.boundingRect().top())
    return tops


def test_placed_field_text_keeps_a_shared_baseline(qapp):
    """User ruling 2026-11-05: tags line up. Ink centring would drop the two apart by 1.3 mm."""
    plain, descender = _tag(["HIT", "Hgy"])
    assert plain == pytest.approx(descender, abs=0.05)


def test_field_text_in_the_block_editor_keeps_the_line_box_rule(qapp):
    scene = Model_Space(scene_role="block_editor")
    item = _text("@[Name]")
    scene.addItem(item)
    room = item._box_rect_local().height() - QTextItemHeight(item)
    assert item._layout_offsets().voff == pytest.approx(room / 2.0 + item._shrink_off.y(), abs=1e-6)


def test_the_field_flag_is_sparse_and_round_trips(qapp):
    assert "line_box_middle" not in TextAnnotationData(text="a").to_dict()
    d = TextAnnotationData(text="a", line_box_middle=True).to_dict()
    assert TextAnnotationData.from_dict(d).line_box_middle is True
