from PyQt6.QtCore import QRectF
from firepro3d.model_space import Model_Space

# Node markers use ItemIgnoresTransformations, giving them a fixed-pixel shape
# that inflates to ~356 scene units when no view transform is attached (unit
# tests have no view). Window rects are therefore sized to fully contain a
# node's inflated marker shape, and entities are spaced far apart so their
# inflated shapes do not overlap. The window(contained) vs crossing(intersect)
# semantics are what these tests assert.


def test_window_selects_fully_contained_only(qapp):
    sc = Model_Space()
    inside = sc.add_node(5000.0, 5000.0)
    edge = sc.add_pipe(sc.add_node(0.0, 0.0), sc.add_node(100.0, 100.0))
    # Straddler crosses the window's left edge: it intersects the window but is
    # not fully contained, so a window (contains) query must exclude it. This
    # also falsifies a contains/intersects swap in the implementation.
    straddler = sc.add_pipe(sc.add_node(4600.0, 5000.0),
                            sc.add_node(5000.0, 5000.0))
    # Window fully contains the node marker at (5000,5000); the far pipe and the
    # straddler are excluded, so a window (contains) query selects only the node.
    sc.commit_rubber_band(QRectF(4800, 4800, 600, 600), crossing=False, additive=False)
    assert inside.isSelected()
    assert not edge.isSelected()
    assert not straddler.isSelected()


def test_crossing_selects_intersecting(qapp):
    sc = Model_Space()
    edge = sc.add_pipe(sc.add_node(0.0, 0.0), sc.add_node(100.0, 100.0))
    # Small box straddles the pipe diagonal: it intersects but does not contain.
    sc.commit_rubber_band(QRectF(40, 40, 20, 20), crossing=True, additive=False)
    assert edge.isSelected()


def test_additive_preserves_existing(qapp):
    sc = Model_Space()
    a = sc.add_node(0.0, 0.0)
    b = sc.add_node(5000.0, 5000.0)
    a.setSelected(True)
    # Window contains only b; additive must keep a's pre-existing selection.
    sc.commit_rubber_band(QRectF(4800, 4800, 600, 600), crossing=False, additive=True)
    assert a.isSelected() and b.isSelected()


def test_excluded_flag_never_selected(qapp):
    sc = Model_Space()
    n = sc.add_node(50.0, 50.0)
    n._exclude_from_bulk_select = True
    sc.commit_rubber_band(QRectF(-200, -200, 500, 500), crossing=True, additive=False)
    assert not n.isSelected()
