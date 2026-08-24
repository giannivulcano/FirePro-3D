from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QColor, QPainterPath
from firepro3d.wall_opening import WallOpening
from firepro3d.wall import WallSegment


def _render_item(scene, item, size=200):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    br = item.mapToScene(item.boundingRect()).boundingRect()
    scene.render(p, QRectF(0, 0, size, size), br.adjusted(-50, -50, 50, 50))
    p.end()
    return img


def _has_non_white(img):
    return any(QColor(img.pixel(x, y)) != QColor("white")
               for x in range(0, img.width(), 3) for y in range(0, img.height(), 3))


def test_door_plan_symbol_draws_arc(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    scene.addItem(op); w.openings.append(op)
    op._reposition()
    assert not op.path().isEmpty()
    assert _has_non_white(_render_item(scene, op))


def test_hinge_mirror_changes_path(qapp, model_scene):
    """Flipping the hinge mirrors the swing left↔right. The swing correctly
    spans the opening in both cases, so the *bounding rect* is symmetric —
    assert the actual PATH changes (the mirror does real work)."""
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=500.0)
    op._reposition(); before = QPainterPath(op.path())     # copy
    op.mirror_hinge = True; op._reposition()
    assert op.path() != before


def test_blank_opening_has_no_swing(qapp, model_scene):
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(1000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="blank_900", offset_along=500.0)
    op._reposition()
    br = op.path().boundingRect()
    assert br.height() <= w.half_thickness_scene() * 2 + 1.0


def test_opening_projected_into_elevation(qapp, elevation_scene_for):
    """§7.8.2: _project_openings must tag at least one scene item with the
    WallOpening as _ROLE_SOURCE so elevation views can round-trip source refs."""
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from firepro3d.elevation_scene import _ROLE_SOURCE
    from PyQt6.QtCore import QPointF
    scene, elev = elevation_scene_for(direction="north")
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="window_900", offset_along=1000.0)
    op.sill_mm = 900.0; op.height_mm = 1200.0; op.level = w.level
    scene.addItem(op); w.openings.append(op)
    elev.rebuild()
    sources = [it.data(_ROLE_SOURCE) for it in elev.items()]
    assert op in sources


def test_opening_emits_3d_meshes(qapp, model_scene):
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from PyQt6.QtCore import QPointF
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=1000.0)
    scene.addItem(op); w.openings.append(op)
    meshes = op.get_3d_meshes(level_manager=scene._level_manager)
    assert len(meshes) >= 2                       # door → frame + closed leaf
    for m in meshes:
        assert len(m["vertices"]) >= 4 and len(m["faces"]) >= 2


def test_blank_opening_emits_no_3d_leaf(qapp, model_scene):
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from PyQt6.QtCore import QPointF
    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="blank_900", offset_along=1000.0)
    scene.addItem(op); w.openings.append(op)
    assert op.get_3d_meshes(level_manager=scene._level_manager) == []


# ── PDF visual-gate test (§7.8/§7.15) ────────────────────────────────────────

def test_opening_plots_to_pdf(qapp, model_scene, tmp_path):
    """Render a plan containing a door opening to PDF at architectural scale.

    This is the smoke-test artifact: non-empty output confirms the rendering
    path (WallOpening._paint_symbol) produces real drawing content.
    """
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from PyQt6.QtGui import QPdfWriter, QPainter
    from PyQt6.QtCore import QPointF, QRectF

    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    scene.addItem(w)
    scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=1500.0)
    scene.addItem(op)
    w.openings.append(op)
    op._reposition()

    out = tmp_path / "door.pdf"
    writer = QPdfWriter(str(out))
    writer.setResolution(300)
    p = QPainter(writer)
    scene.render(
        p,
        QRectF(0, 0, writer.width(), writer.height()),
        scene.itemsBoundingRect(),
    )
    p.end()

    assert out.exists() and out.stat().st_size > 1500, (
        f"PDF should be non-empty: {out.stat().st_size} bytes"
    )


def test_opening_gets_paper_override(qapp, model_scene):
    """Paper pipeline must handle WallOpening: register it in a category so
    apply_paper_overrides sets _display_color (pen colour normalised for paper)
    and sets _paper_gap_color to a light/white colour so the gap reads as a
    clean hole on white paper rather than a dark block."""
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from firepro3d.paper_display import apply_paper_overrides, restore_model_display
    from PyQt6.QtCore import QPointF, QRectF

    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    scene.addItem(w); scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=1500.0)
    scene.addItem(op); w.openings.append(op)
    op._reposition()

    rect = scene.itemsBoundingRect().adjusted(-100, -100, 100, 100)
    saved = apply_paper_overrides(scene, rect)

    # Opening is now handled (has a paper category → _display_color set to
    # the paper pen colour — not None).
    assert op._display_color is not None, (
        "_display_color should be set by paper override (opening is in a category)"
    )

    # Gap fill flag set — and it should be a light/white paper colour (not the
    # dark model background that sc.backgroundBrush() returns on screen).
    gap_color = getattr(op, "_paper_gap_color", None)
    assert gap_color is not None, (
        "_paper_gap_color should be set by paper override so gap renders white on paper"
    )
    from PyQt6.QtGui import QColor
    c = QColor(gap_color)
    # Paper background is white (or near-white). Lightness > 0.8 means
    # it is clearly a paper/white colour, not the dark screen background.
    assert c.lightnessF() > 0.8, (
        f"_paper_gap_color should be near-white for paper; got {c.name()} "
        f"(lightness={c.lightnessF():.2f})"
    )

    restore_model_display(saved)

    # After restore: flag cleared and _display_color back to None (screen default).
    assert getattr(op, "_paper_gap_color", None) is None, (
        "_paper_gap_color should be cleared / restored to None after restore"
    )
    assert op._display_color is None, (
        "_display_color should be restored to None (screen default) after restore"
    )


def test_wall_with_opening_mesh_is_watertight(qapp, model_scene):
    """§3D: wall with an opening must produce a watertight mesh (no open edges).

    The four reveal quads (sill cap, head cap, left jamb, right jamb) close the
    tunnel through the wall depth at every aperture, so PyVista reports 0 open
    (boundary) edges.
    """
    import numpy as np
    import pyvista as pv
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from PyQt6.QtCore import QPointF

    scene = model_scene()
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    scene.addItem(w)
    scene._walls.append(w)
    op = WallOpening(wall=w, feature_id="door_914", offset_along=1500.0)
    scene.addItem(op)
    w.openings.append(op)

    mesh_data = w.get_3d_mesh(level_manager=scene._level_manager)
    assert mesh_data is not None, "get_3d_mesh returned None for wall with opening"

    verts = np.array(mesh_data["vertices"], dtype=float)
    faces = np.array(mesh_data["faces"], dtype=np.int64)

    pd = pv.PolyData.from_regular_faces(verts, faces)
    open_edges = pd.n_open_edges
    assert open_edges == 0, (
        f"Wall mesh has {open_edges} open edge(s) — reveal caps are missing or "
        "wound incorrectly (open edges arise from unshared boundary edges)"
    )


def test_opening_perpendicular_on_joined_wall(qapp, model_scene):
    """#2 fix: on a mitered (joined) wall, the 3D opening jamb must stay
    perpendicular. get_3d_mesh uses the UN-mitered quad_points (parallel long
    edges → perpendicular jambs); the mitered_quad edges skew (the old bug).
    Asserts the geometric ground truth + watertightness on a real L-joint."""
    import math
    import numpy as np
    import pyvista as pv
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from PyQt6.QtCore import QPointF

    scene = model_scene()
    a = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    b = WallSegment(QPointF(3000, 0), QPointF(3000, 3000), thickness_mm=200.0)
    for w in (a, b):
        scene.addItem(w); scene._walls.append(w)

    def _len(p, q):
        return math.hypot(q.x() - p.x(), q.y() - p.y())

    # Precondition: wall A IS mitered — the two long edges have UNEQUAL length
    # (one corner is pushed out to meet the neighbour), so same-parameter
    # interpolation of a jamb lands off-square (the old bug).
    mq0, mq1, mq2, mq3 = a.mitered_quad()
    assert abs(_len(mq0, mq3) - _len(mq1, mq2)) > 1.0, "test wall not mitered"

    # Fix: quad_points long edges are EQUAL length → same-t jamb is perpendicular.
    qp0, qp1, qp2, qp3 = a.quad_points()
    assert abs(_len(qp0, qp3) - _len(qp1, qp2)) < 1e-6

    op = WallOpening(wall=a, feature_id="door_914", offset_along=2400.0)
    scene.addItem(op); a.openings.append(op)
    mesh = a.get_3d_mesh(level_manager=scene._level_manager)
    verts = np.array(mesh["vertices"], dtype=float)
    faces = np.array(mesh["faces"], dtype=np.int64)
    pd = pv.PolyData.from_regular_faces(verts, faces)
    assert pd.n_open_edges == 0
