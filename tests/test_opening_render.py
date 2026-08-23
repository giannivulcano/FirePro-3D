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
