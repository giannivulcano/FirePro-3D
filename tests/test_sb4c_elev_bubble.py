"""SB4c half A -- elevation / section gridline bubbles drawn by the plan
gridline's annotation block (design
docs/superpowers/specs/2026-11-03-sb4c-elev-bubble-datum-design.md D1 D2 D6)."""
import pytest
from PyQt6.QtCore import QLineF, QPointF, QRectF

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.gridline import GridlineItem
from tests.test_sb4b_gridline_bubble import CIRCLE_R, _bubble_def, _gridline, _scene


def _k(ms):
    """Scene units per authored mm: the project drawing scale (plan and section
    canvas alike, annotative._drawing_scale); ScaleManager() defaults to 100."""
    return ms.scale_manager.drawing_scale


def _plan_gridline(ms, x=2500.0, label="1"):
    """A plan gridline vertical in plan at world x (start = bubble 1 at y=-3000);
    a North elevation shows it at h = -x."""
    gl = GridlineItem(QPointF(x, -3000.0), QPointF(x, 3000.0), label)
    ms.addItem(gl)
    ms._gridlines.append(gl)
    return gl


def _offset_box_def(ms, name="OffsetBox"):
    """A NON-circular, NON-symmetric Gridline bubble: a 12 x 6 mm box from
    y = -2 to y = +4 mm about the origin (Qt y-down block frame; drafter probe:
    its stroke op bounds are QRectF(-6, -2, 12, 6)), so a ray (0, +1) leaves at
    4 mm and (0, -1) at 2 mm -- a trim-sign probe. Mapped as the project default."""
    geom = {"type": "draw_rectangle", "x": -6.0, "y": -2.0, "w": 12.0, "h": 6.0,
            "color": "token:auto", "lineweight": 1.0}
    text = {"type": "text", "text": "@[Mark]", "x": -5.0, "y": -1.0, "height_mm": 3.0,
            "wrap_width_mm": 10.0, "box_height_mm": 4.0, "align": "C", "valign": "M"}
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[geom, text])
    d.scale_mode = "annotative"
    d.host_category = "Gridline"
    d.attributes = [normalise_attr({"key": "Mark", "source": "host", "host_key": "Mark",
                                    "placeholder": ""})]
    ms.register_block_definition(d)
    ms.annotation_defaults["Gridline"] = d.id
    return d


# -- D1 seam: data host vs graphics parent ----------------------------------

def test_d1_bound_label_parent_is_the_graphics_parent_and_host_stays_the_data_source(qapp):
    from PyQt6.QtWidgets import QGraphicsRectItem
    from firepro3d.bound_label import BoundLabelItem
    ms = _scene()
    _bubble_def(ms)
    gl = _gridline(ms, label="Q")
    holder = QGraphicsRectItem()
    ms.addItem(holder)
    lab = BoundLabelItem(gl, parent=holder)
    assert lab.parentItem() is holder
    assert lab.host is gl and lab.category == "Gridline"
    assert lab.host_values({"Mark"})["Mark"].raw == "Q"
    assert BoundLabelItem(gl).parentItem() is gl                    # default unchanged
    assert BoundLabelItem(gl, child=False).parentItem() is None     # SB4a D1 unchanged


def test_d1_outlined_label_base_has_no_overlays_and_gridline_bubble_extends_it(qapp):
    from PyQt6.QtWidgets import QGraphicsRectItem
    from firepro3d.bound_label import OutlinedLabel
    from firepro3d.gridline import GridlineBubble
    ms = _scene()
    k = _k(ms)
    _bubble_def(ms)
    gl = _gridline(ms)
    assert isinstance(gl.bubble1, GridlineBubble) and isinstance(gl.bubble1, OutlinedLabel)
    lab = OutlinedLabel(gl, child=False)
    ms.addItem(lab)
    assert lab.trim_distance(0.0, 1.0) == pytest.approx(CIRCLE_R * k, abs=0.05 * k)
    assert not lab.outline_path().isEmpty()
    gl.setSelected(True)
    assert lab.overlay_pens() == []                   # the base never rings
    # A GridlineBubble under another graphics parent still reads the plan gridline.
    holder = QGraphicsRectItem()
    ms.addItem(holder)
    b = GridlineBubble(gl, parent=holder)
    assert b.parentItem() is holder and b.host is gl and b.category == "Gridline"


def _static_width(label):
    """Width of the union of *label*'s painted non-text ops at its own k
    (the ops ``BoundLabelItem.paint`` hands ``paint_ops``)."""
    st = label._state()
    r = QRectF()
    for op in label._ops(label._k(None, st[0]), st):
        if op.kind != "text":
            r = r.united(op.path.boundingRect())
    return r.width()


def test_d1_section_scene_forwards_the_annotation_resolver(qapp, section_scene_for):
    """A label hosted on a plan gridline but living in a SectionScene draws the
    project's mapped block at the section canvas k (= the drawing scale)."""
    from firepro3d.bound_label import BoundLabelItem
    ms, sec = section_scene_for("north")
    k = _k(ms)
    d = _bubble_def(ms)
    gl = _plan_gridline(ms)
    assert sec.annotation_block("Gridline") is d
    lab = BoundLabelItem(gl, child=False)
    sec.addItem(lab)
    assert lab.definition() is d
    assert _static_width(lab) == pytest.approx(2 * CIRCLE_R * k, abs=0.1 * k)


def test_d1_cross_scene_host_deleted_first_reads_as_dead_not_a_raise(qapp, section_scene_for):
    """The data host now lives in ANOTHER scene than the label: when the plan
    gridline's C++ object is gone first (teardown order, undo restore), the
    label's host read must return None (placeholders, E9) -- a RuntimeError
    raised inside a Qt virtual (boundingRect / shape) is a native abort."""
    from PyQt6 import sip
    from firepro3d.bound_label import BoundLabelItem
    ms, sec = section_scene_for("north")
    _bubble_def(ms)
    gl = _plan_gridline(ms)
    lab = BoundLabelItem(gl, child=False)
    sec.addItem(lab)
    ms._gridlines.remove(gl)
    ms.removeItem(gl)
    sip.delete(gl)
    assert lab.host_values() is None
    lab.refresh()
    lab.boundingRect()                    # must not raise


# -- shared section helpers --------------------------------------------------

def _elev(sec, h=None):
    """The one ElevGridlineItem in *sec* (at scene h when given)."""
    from firepro3d.section_scene import ElevGridlineItem
    items = [i for i in sec.items() if isinstance(i, ElevGridlineItem)]
    if h is not None:
        items = [i for i in items if abs(i.line().x1() - h) < 1e-6]
    (eg,) = items
    return eg


def _flush_rebuild(sec):
    """Run the debounced rebuild now (the 100 ms single-shot a plan edit arms)."""
    sec._rebuild_timer.stop()
    sec.rebuild()


def _painted_lines(item):
    """Every ``drawLine`` call ``item.paint`` makes, item coords: a recording
    painter on a scratch image (the painted geometry, not a getter)."""
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    calls = []

    class _Rec(QPainter):
        def drawLine(self, *a):
            calls.append(QLineF(*a))
            return super().drawLine(*a)

    img = QImage(8, 8, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = _Rec(img)
    try:
        item.paint(p, QStyleOptionGraphicsItem(), None)
    finally:
        p.end()
    return calls


@pytest.fixture
def two_sections(qapp):
    """A real SectionManager over a fresh Model_Space (default LevelManager,
    ScaleManager drawing scale 100) wired as ``ms._section_manager`` the way
    main.py wires it. Scenes come from ``get_or_build_scene``; teardown frees
    them at a safe point (conftest ``section_scene_for`` recipe: a GC-timed
    SectionScene collection aborts natively, SB4b D1)."""
    import gc
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication, QTabWidget
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    ms = Model_Space()
    lm = LevelManager()
    ms._level_manager = lm
    sm = ScaleManager()
    ms.scale_manager = sm
    tabs = QTabWidget()
    m = SectionManager(ms, lm, sm, tabs)
    ms._section_manager = m
    yield m, ms
    scenes = list(m.open_scenes)
    m.close_all()
    ms._section_manager = None
    for sc in scenes:
        sc._rebuild_timer.stop()
        sc.deleteLater()
    ms.cleanup()
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    gc.collect()


# -- D2: the elevation bubble is the plan gridline's block ------------------

def test_d2_elevation_bubbles_are_gridline_bubbles_hosted_on_the_plan_gridline(qapp, section_scene_for):
    from firepro3d.gridline import GridlineBubble
    ms, sec = section_scene_for("north")
    k = _k(ms)
    _bubble_def(ms)
    gl = _plan_gridline(ms)
    sec.rebuild()
    eg = _elev(sec)
    line = eg.line()
    assert line.y1() < line.y2()                          # p1 = the TOP end (Qt y-down)
    assert eg._gridline is gl
    for b, end in ((eg.bubble1, line.p1()), (eg.bubble2, line.p2())):
        assert isinstance(b, GridlineBubble)
        assert b.parentItem() is eg and b.host is gl and b.category == "Gridline"
        assert b.pos() == end and b.rotation() == 0.0     # upright
        w = b.outline_path().boundingRect().width()
        assert w == pytest.approx(2 * CIRCLE_R * k, abs=0.05 * k)   # annotative: k = drawing scale


def test_d2_elevation_stops_reading_grid_line_fill_and_scale(qapp, section_scene_for):
    """AC6 (gridline half): a saved display/Grid Line/scale or /fill no longer
    sizes or fills anything in elevation. Expected extent from the drafter
    probe (default LevelManager, d4f27c62): line (-2500, -10349.2) -> (-2500,
    1253.2), pen 8.128 -- the scale-1.0 numbers."""
    from PyQt6.QtCore import QSettings
    ms, sec = section_scene_for("north")
    k = _k(ms)
    _bubble_def(ms)
    _plan_gridline(ms)
    s = QSettings("GV", "FirePro3D")                      # conftest-isolated store
    s.setValue("display/Grid Line/scale", 3.0)
    s.setValue("display/Grid Line/fill", "#ff0000")
    sec.rebuild()
    eg = _elev(sec)
    assert eg.line().y1() == pytest.approx(-10349.2)
    assert eg.line().y2() == pytest.approx(1253.2)
    assert eg._pen_w == pytest.approx(8.128)
    w = eg.bubble1.outline_path().boundingRect().width()
    assert w == pytest.approx(2 * CIRCLE_R * k, abs=0.05 * k)


def test_ac4_elevation_line_trims_at_a_non_circular_outline_on_screen(qapp, section_scene_for):
    """Painted line endpoints. Bubble 1 = top: its ray toward bubble 2 runs +y
    (Qt y-down) and leaves the offset box at y = +4 mm; bubble 2's ray runs -y
    and leaves at y = -2 mm. k = 100 (ScaleManager default)."""
    ms, sec = section_scene_for("north")
    k = _k(ms)
    _offset_box_def(ms)
    _plan_gridline(ms)
    sec.rebuild()
    eg = _elev(sec)
    line = eg.line()
    drawn = _painted_lines(eg)[0]
    assert drawn.x1() == pytest.approx(line.x1()) and drawn.x2() == pytest.approx(line.x1())
    assert drawn.y1() == pytest.approx(line.y1() + 4.0 * k, abs=0.05 * k)
    assert drawn.y2() == pytest.approx(line.y2() - 2.0 * k, abs=0.05 * k)


def test_ac4_hidden_plan_bubble_leaves_that_elevation_end_untrimmed(qapp, section_scene_for):
    ms, sec = section_scene_for("north")
    k = _k(ms)
    _bubble_def(ms)
    gl = _plan_gridline(ms)
    gl.set_bubble_visible(2, False)
    sec.rebuild()
    eg = _elev(sec)
    assert eg.bubble1.isVisible() and not eg.bubble2.isVisible()
    drawn = _painted_lines(eg)[0]
    assert drawn.y1() == pytest.approx(eg.line().y1() + CIRCLE_R * k, abs=0.05 * k)
    assert drawn.y2() == pytest.approx(eg.line().y2())


def test_ac4_trim_follows_the_bubbles_paper_scale_outline(qapp, section_scene_for):
    """Paper half of the trim, unit level: with the pass entered and each
    bubble given the paper scale ``paper_display._apply_block`` sets (half B
    wires the walk), the line ends at the PRINTED outline (k = 1 / S) and the
    rings are off."""
    ms, sec = section_scene_for("north")
    _offset_box_def(ms)
    _plan_gridline(ms)
    sec.rebuild()
    eg = _elev(sec)
    eg.setSelected(True)
    assert eg.bubble1.overlay_pens()                      # screen: the selection ring
    S = 0.02                                              # 1:50 -> k = 50
    saved = eg.enter_paper_pass(0.35, S)
    for b in (eg.bubble1, eg.bubble2):
        b._paper_scale = S
    try:
        drawn = _painted_lines(eg)[0]
        assert drawn.y1() == pytest.approx(eg.line().y1() + 4.0 / S, abs=0.05 / S)
        assert drawn.y2() == pytest.approx(eg.line().y2() - 2.0 / S, abs=0.05 / S)
        assert eg._paper_render and eg.bubble1.overlay_pens() == []
    finally:
        for b in (eg.bubble1, eg.bubble2):
            b._paper_scale = None
        eg.exit_paper_pass(saved)
    assert not eg._paper_render and eg._paper_line_w_mm == 0.0
    assert eg.bubble1.overlay_pens()                      # restored


@pytest.mark.parametrize("shape", ["circle", "square"])
def test_d2_bounding_rect_covers_the_bubble_hit_area_for_qt_native_picks(qapp, section_scene_for, shape):
    """SB4b M1 twin: shape() adds the bubble outlines and boundingRect() holds
    them, so items(pos) / the context menu find the gridline at a bubble's
    outer edge."""
    ms, sec = section_scene_for("north")
    k = _k(ms)
    _bubble_def(ms, shape)
    _plan_gridline(ms)
    sec.rebuild()
    eg = _elev(sec)
    assert eg.boundingRect().contains(eg.shape().boundingRect())
    c = eg.bubble1.scenePos()
    reach = (CIRCLE_R if shape == "circle" else 3.0) * k * 0.9    # inside the outline, outboard (up)
    outer = QPointF(c.x(), c.y() - reach)
    assert eg in sec.items(outer), "a Qt-native pick at the bubble's outer edge finds the gridline"


def test_d2_manipulator_never_wraps_the_bubble_children(qapp, section_scene_for):
    ms, sec = section_scene_for("north")
    _bubble_def(ms)
    _plan_gridline(ms)
    sec.rebuild()
    eg = _elev(sec)
    assert sec._manip_exclude(eg.bubble1) and sec._manip_exclude(eg.bubble2)
    assert not sec._manip_exclude(eg)


# -- D1: refresh walks --------------------------------------------------------

def test_d1_section_refresh_reshapes_elevation_bubbles_and_trim(qapp, section_scene_for):
    """A drawing-scale change reaches an open section through
    annotative.reprepare_annotative (main.py _on_project_settings_changed),
    which calls SectionScene.refresh_annotation_tags."""
    from firepro3d.annotative import reprepare_annotative
    ms, sec = section_scene_for("north")
    _bubble_def(ms)
    _plan_gridline(ms)
    sec.rebuild()
    eg = _elev(sec)
    # Prime the caches at k = 100 (Qt indexes lazily: nothing has queried the
    # outline yet), so a skipped refresh() is a stale outline, not a fresh one.
    assert eg.bubble1.outline_path().boundingRect().width() == pytest.approx(2 * CIRCLE_R * _k(ms), abs=5.0)
    assert _painted_lines(eg)[0].y1() == pytest.approx(eg.line().y1() + CIRCLE_R * _k(ms), abs=5.0)
    ms.scale_manager.drawing_scale = 50.0
    reprepare_annotative(sec)
    w = eg.bubble1.outline_path().boundingRect().width()
    assert w == pytest.approx(2 * CIRCLE_R * 50.0, abs=2.5)
    drawn = _painted_lines(eg)[0]
    assert drawn.y1() == pytest.approx(eg.line().y1() + CIRCLE_R * 50.0, abs=2.5)


def test_d1_model_refresh_reaches_open_sections(qapp, two_sections):
    """Model_Space.refresh_annotation_tags (Annotation pane, registry change,
    units) re-shapes every open section's elevation bubbles."""
    m, ms = two_sections
    k = _k(ms)
    _bubble_def(ms)
    _plan_gridline(ms)
    m.seed_cardinals()
    sec = m.get_or_build_scene("north")
    eg = _elev(sec)
    assert _painted_lines(eg)[0].y1() == pytest.approx(eg.line().y1() + CIRCLE_R * k, abs=0.05 * k)
    _offset_box_def(ms)              # registers (its own refresh runs BEFORE the remap) then remaps
    ms.refresh_annotation_tags()     # the call the Annotation pane makes after a mapping change
    assert _painted_lines(eg)[0].y1() == pytest.approx(eg.line().y1() + 4.0 * k, abs=0.05 * k)


def _text_width(label):
    """Width of the union of *label*'s painted TEXT ops (the bound @[Mark])."""
    st = label._state()
    r = QRectF()
    for op in label._ops(label._k(None, st[0]), st):
        if op.kind == "text":
            r = r.united(op.path.boundingRect())
    return r.width()


def _ring_pixels(sec, bubble, rgb, tol=40):
    """Pixels near *rgb* in a 200 x 200 render of *bubble*'s area of *sec*
    (SB4b ``_ring_pixels`` recipe: the ring is rendered, not a pen list)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage, QPainter
    r = bubble.sceneBoundingRect().adjusted(-50, -50, 50, 50)
    img = QImage(200, 200, QImage.Format.Format_RGB32)
    img.fill(0xFF101010)
    p = QPainter(img)
    sec.render(p, QRectF(0, 0, 200, 200), r, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    n = 0
    for y in range(200):
        for x in range(200):
            c = img.pixelColor(x, y)
            if abs(c.red() - rgb[0]) + abs(c.green() - rgb[1]) + abs(c.blue() - rgb[2]) <= tol:
                n += 1
    return n


def test_ac1_elevation_bubble_follows_the_plan_gridlines_tag_block(qapp, section_scene_for):
    """A Tag pick on the PLAN gridline (Properties Tag row) changes what the
    elevation bubbles paint, through the real rebuild the pick schedules."""
    ms, sec = section_scene_for("north")
    k = _k(ms)
    circ = _bubble_def(ms, "circle", name="CircBubble")
    _bubble_def(ms, "square", name="SquareBubble")           # 12 x 6 mm box
    ms.annotation_defaults["Gridline"] = circ.id
    gl = _plan_gridline(ms)
    sec.rebuild()
    assert _static_width(_elev(sec).bubble1) == pytest.approx(2 * CIRCLE_R * k, abs=0.1 * k)
    sec._rebuild_timer.stop()            # a block registration above may have armed it
    opts = gl.get_properties()["Tag"]["options"]
    gl.set_property("Tag", next(o for o in opts if o.startswith("SquareBubble")))
    assert sec._rebuild_timer.isActive(), "the Tag pick schedules the section rebuild (D6 probe)"
    _flush_rebuild(sec)
    eg = _elev(sec)
    for b in (eg.bubble1, eg.bubble2):
        assert _static_width(b) == pytest.approx(12.0 * k, abs=0.1 * k)


def test_ac1_mark_rename_repaints_without_a_rebuild(qapp, section_scene_for):
    """Pull-on-paint (D6): the elevation bubble reads Mark off the plan
    gridline at paint, so a rename shows before any section rebuild."""
    ms, sec = section_scene_for("north")
    _bubble_def(ms)
    gl = _plan_gridline(ms, label="1")
    sec.rebuild()
    eg = _elev(sec)
    w1 = _text_width(eg.bubble1)
    assert w1 > 0.0
    gl.grid_label = "WWW"
    assert _elev(sec) is eg                                  # no rebuild ran
    assert eg.bubble1.host_values({"Mark"})["Mark"].raw == "WWW"
    assert _text_width(eg.bubble1) > 2.0 * w1


@pytest.mark.parametrize("end", [1, 2])
def test_ac2_plan_bubble_toggle_hides_the_matching_end_in_every_section(qapp, two_sections, end):
    """Plan Bubble 1 -> elevation TOP, Bubble 2 -> BOTTOM, in North (h = -2500)
    and South (h = +2500) alike (drafter probe: both cardinals show the
    gridline; East / West are parallel). Driven through the real property
    panel commit, which arms each open section's rebuild."""
    from firepro3d.property_manager import PropertyManager
    m, ms = two_sections
    _bubble_def(ms)
    gl = _plan_gridline(ms)
    m.seed_cardinals()
    scenes = [m.get_or_build_scene(c) for c in ("north", "south")]
    for sc in scenes:
        eg = _elev(sc)
        assert eg.bubble1.isVisible() and eg.bubble2.isVisible()
        sc._rebuild_timer.stop()         # only the panel commit below may arm it
    pm = PropertyManager()
    try:
        pm.show_properties(gl)
        pm._apply_property(f"Bubble {end}", "Hidden")
    finally:
        pm.deleteLater()
    expect = (False, True) if end == 1 else (True, False)
    for sc in scenes:
        assert sc._rebuild_timer.isActive(), "the panel commit schedules every open section"
        _flush_rebuild(sc)
        eg = _elev(sc)
        assert (eg.bubble1.isVisible(), eg.bubble2.isVisible()) == expect
        drawn = _painted_lines(eg)[0]
        if end == 1:
            assert drawn.y1() == pytest.approx(eg.line().y1())   # hidden top: untrimmed
        else:
            assert drawn.y2() == pytest.approx(eg.line().y2())   # hidden bottom: untrimmed


def test_ac5_duplicate_and_selection_rings_render_on_screen_never_on_paper(qapp, section_scene_for):
    from firepro3d.gridline import apply_duplicate_warnings
    ms, sec = section_scene_for("north")
    _bubble_def(ms)
    _plan_gridline(ms, 2500.0, "1")
    other = _plan_gridline(ms, 4000.0, "2")
    sec.rebuild()
    orange = (0xFF, 0x88, 0x00)
    assert _ring_pixels(sec, _elev(sec, -2500.0).bubble1, orange) == 0
    other.grid_label = "1"
    apply_duplicate_warnings(ms._gridlines)
    _flush_rebuild(sec)                       # the panel path arms this rebuild (Task 1 probe)
    ea = _elev(sec, -2500.0)
    assert ea.bubble1._duplicate and ea.bubble2._duplicate
    assert _ring_pixels(sec, ea.bubble1, orange) > 100, "duplicate ring paints round the top bubble"
    saved = ea.enter_paper_pass(0.35, 0.02)
    try:
        assert _ring_pixels(sec, ea.bubble1, orange) == 0, "the duplicate ring never plots"
    finally:
        ea.exit_paper_pass(saved)
    other.grid_label = "2"
    apply_duplicate_warnings(ms._gridlines)
    _flush_rebuild(sec)
    ea = _elev(sec, -2500.0)
    sel = ea._grid_color.lighter(150)
    sel_rgb = (sel.red(), sel.green(), sel.blue())
    before = _ring_pixels(sec, ea.bubble1, sel_rgb, tol=12)
    ea.setSelected(True)
    assert _ring_pixels(sec, ea.bubble1, sel_rgb, tol=12) > before + 100, \
        "selection ring paints round the top bubble"


def test_ac8_click_on_an_elevation_bubble_selects_the_gridline(qapp, section_scene_for):
    """Posted hover + click at the bubble centre on a shown SectionView: HALO
    resolves the bubble to its gridline and the press selects it (the retired
    bespoke bubble's mousePressEvent is not needed)."""
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QApplication
    from firepro3d.elevation_view import SectionView
    from tests.test_elev_selection_interaction import _click, _move, _vp
    ms, sec = section_scene_for("north")
    _bubble_def(ms)
    _plan_gridline(ms)
    sec.rebuild()
    eg = _elev(sec)
    view = SectionView(sec)
    try:
        view.resize(600, 600)
        view.show()
        QApplication.processEvents()
        view.setTransform(QTransform.fromScale(0.2, 0.2))   # bubble radius 4.75 * 100 * 0.2 = 95 px
        c = eg.bubble1.scenePos()
        view.centerOn(c)
        QApplication.processEvents()
        pt = _vp(view, (c.x(), c.y()))
        _move(view, pt)
        assert sec.halo_item() is eg, "HALO resolves the bubble to its gridline"
        _click(view, pt)
        assert sec.selectedItems() == [eg]
    finally:
        view.close()
