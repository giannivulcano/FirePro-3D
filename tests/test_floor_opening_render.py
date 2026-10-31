"""Floor void rendering: plan see-through + hit-test (A4 plan) and the 3D hole (A4 3D)."""
import math

import pytest
from PyQt6.QtCore import QPointF as P
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d.floor_slab import FloorSlab
from firepro3d.floor_opening import FloorOpening


def _rect(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


def _add(scene, slab, *voids):
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    for pts in voids:
        op = FloorOpening(pts, host=slab)
        slab.add_opening(op)
        scene.addItem(op)
    return slab


def _pixel(view, scene_pt):
    """Colour of the shown viewport at *scene_pt* (device-pixel aware)."""
    QApplication.processEvents()
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    vp = view.mapFromScene(scene_pt)
    return QColor(img.pixel(int(vp.x() * dpr), int(vp.y() * dpr)))


def test_plan_hole_shows_the_level_below(qapp, shown_model_view):
    view, scene = shown_model_view
    lower = FloorSlab(points=_rect(-1200, -1200, 1200, 1200), color="#3366cc")
    lower._top_mode = "absolute"
    lower._top_abs_z_mm = 0.0
    upper = FloorSlab(points=_rect(-1000, -1000, 1000, 1000), color="#cc3333")
    upper._top_mode = "absolute"
    upper._top_abs_z_mm = 5000.0
    _add(scene, lower)
    _add(scene, upper, _rect(-300, -300, 300, 300))
    scene._level_manager.apply_to_scene(scene, "Level 1",
                                        view_height=6000.0, view_depth=-1.0)
    # Preconditions: the upper slab masks what is under it and draws above it.
    assert upper._is_occluding and upper.zValue() > lower.zValue()
    in_hole = _pixel(view, P(0, 0))
    upper.setVisible(False)
    for op in upper.openings:
        op.setVisible(False)
    reference = _pixel(view, P(0, 0))           # the level below, no upper slab at all
    bg = view.viewport().palette().color(view.viewport().palette().ColorRole.Base)
    assert reference != bg                       # sanity: the lower slab tints the spot
    assert in_hole == reference                  # see-through: no mask, no upper fill


def test_click_in_hole_does_not_pick_the_slab(qapp, model_scene):
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)),
                _rect(1000, 1000, 2000, 2000))
    (op,) = slab.openings
    hits = scene.items(P(1500, 1500))
    assert slab not in hits and op in hits
    assert slab in scene.items(P(500, 500))     # material still picks the slab


def test_swallowed_slab_keeps_a_pickable_outline(qapp, model_scene):
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)),
                _rect(-100, -100, 4100, 3100))
    assert slab.cut_region() == []
    assert slab in scene.items(P(4000, 1500))   # on its boundary stroke
    assert slab not in scene.items(P(2000, 1500))
    assert slab.path().elementCount() == 5      # path() is still the full boundary


def test_void_outline_uses_its_display_colour(qapp, shown_model_view):
    view, scene = shown_model_view
    slab = _add(scene, FloorSlab(points=_rect(-1000, -1000, 1000, 1000)),
                _rect(-300, -300, 300, 300))
    slab._display_fill_color = ""               # no fill: only outlines paint
    (op,) = slab.openings
    op._display_color = "#00ff00"               # the Opening DM colour (PART B sets it)
    QApplication.processEvents()
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    vp = view.mapFromScene(P(0, -300))          # midpoint of the void's top edge
    greens = []
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            c = QColor(img.pixel(int((vp.x() + dx) * dpr), int((vp.y() + dy) * dpr)))
            greens.append(c.green() > 180 and c.red() < 90 and c.blue() < 90)
    assert any(greens)


def _area3(v, f):
    a, b, c = (v[i] for i in f)
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    wx, wy, wz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx, cy, cz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def test_mesh_has_a_true_hole_with_side_walls(qapp, model_scene):
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)),
                _rect(1000, 1000, 2000, 2000))
    mesh = slab.get_3d_mesh(scene._level_manager)
    v, faces = mesh["vertices"], mesh["faces"]
    # Top = Level 1 (0.0), bottom = 0.0 - 152.4 (thickness mode default)
    top = [f for f in faces if all(v[i][2] == 0.0 for i in f)]
    bottom = [f for f in faces if all(v[i][2] == pytest.approx(-152.4) for i in f)]
    side = [f for f in faces if len({v[i][2] for i in f}) == 2]
    assert sum(_area3(v, f) for f in top) == pytest.approx(11_000_000.0)      # 12e6 - 1e6
    assert sum(_area3(v, f) for f in bottom) == pytest.approx(11_000_000.0)
    # walls = (outer 2*(4000+3000) + hole 4*1000) * 152.4 = 18000 * 152.4
    assert sum(_area3(v, f) for f in side) == pytest.approx(2_743_200.0)


def test_swallowed_slab_has_no_mesh(qapp, model_scene):
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)),
                _rect(-100, -100, 4100, 3100))
    assert slab.get_3d_mesh(scene._level_manager) is None


def test_void_less_mesh_unchanged(qapp, model_scene):
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)))
    mesh = slab.get_3d_mesh(scene._level_manager)
    # today's layout: 2n vertices; 2 top + 2 bottom ear triangles + 2n side triangles
    assert len(mesh["vertices"]) == 8 and len(mesh["faces"]) == 12


def _side_probes(mesh):
    """For each side-wall triangle: (xy of a point 1 mm along its normal, xy centroid)."""
    v = mesh["vertices"]
    out = []
    for f in mesh["faces"]:
        a, b, c = (v[i] for i in f)
        if len({a[2], b[2], c[2]}) != 2:
            continue
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        wx, wy, wz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny = uy * wz - uz * wy, uz * wx - ux * wz
        nz = ux * wy - uy * wx
        assert nz == pytest.approx(0.0, abs=1e-6)       # walls are vertical
        ln = math.hypot(nx, ny)
        cx, cy = (a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3
        out.append(((cx + nx / ln, cy + ny / ln), (cx, cy)))
    return out


def test_mesh_side_walls_face_away_from_the_material(qapp, model_scene):
    """Outer walls face outward; hole walls face into the hole (void-less convention)."""
    scene = model_scene()
    plain = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)))
    holed = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)),
                 _rect(1000, 1000, 2000, 2000))
    # world mm = (x, -y): slab x 0..4000, y -3000..0; hole x 1000..2000, y -2000..-1000

    def in_material(p, with_hole):
        x, y = p
        if not (0 <= x <= 4000 and -3000 <= y <= 0):
            return False
        return not (with_hole and 1000 <= x <= 2000 and -2000 <= y <= -1000)

    plain_probes = _side_probes(plain.get_3d_mesh(scene._level_manager))
    assert plain_probes and not any(in_material(p, False) for p, _ in plain_probes)

    probes = _side_probes(holed.get_3d_mesh(scene._level_manager))
    assert len(probes) == 2 * 8                        # 8 wall quads (4 outer + 4 hole)
    assert not any(in_material(p, True) for p, _ in probes)
    # Both ring kinds are present and each faces the right way.
    hole_walls = [p for p, c in probes if 1000 <= c[0] <= 2000 and -2000 <= c[1] <= -1000]
    assert len(hole_walls) == 8


def _polydata(scene, slab):
    """The slab's 3D polydata, built exactly as View3D._build_slabs does."""
    import numpy as np
    from firepro3d.view_3d import _mesh_from_faces
    md = slab.get_3d_mesh(level_manager=scene._level_manager)
    return _mesh_from_faces(np.array(md["vertices"], dtype=np.float32),
                            np.array(md["faces"], dtype=np.uint32))


def _seam_cases():
    return {
        "rect_one_void": ([P(0, 0), P(4000, 0), P(4000, 3000), P(0, 3000)],
                          [_rect(1000, 1000, 2000, 2000)]),
        "polygon_two_voids": ([P(0, 0), P(6000, 0), P(6000, 2000), P(4000, 3500),
                               P(0, 3500)],
                              [_rect(500, 500, 1500, 1500), _rect(2500, 500, 3500, 1500)]),
        "void_crossing_edge": ([P(0, 0), P(4000, 0), P(4000, 3000), P(0, 3000)],
                               [_rect(3000, 1000, 5000, 2000)]),
    }


@pytest.mark.parametrize("case", list(_seam_cases()))
def test_holed_mesh_is_watertight_no_seam_edges(qapp, model_scene, case):
    pts, voids = _seam_cases()[case]
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=pts), *voids)
    mesh = _polydata(scene, slab)
    open_edges = mesh.extract_feature_edges(
        boundary_edges=True, non_manifold_edges=True,
        feature_edges=False, manifold_edges=False)
    assert open_edges.n_cells == 0


@pytest.mark.parametrize("case", list(_seam_cases()))
def test_holed_mesh_edge_pass_has_no_diagonal_lines(qapp, model_scene, case):
    """View3D._add_edge_actor's edge pass must draw only axis-aligned/vertical lines."""
    pts, voids = _seam_cases()[case]
    if case == "polygon_two_voids":
        pts_ok = False                      # slanted outer edge is legitimately diagonal
    else:
        pts_ok = True
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=pts), *voids)
    mesh = _polydata(scene, slab)
    edges = mesh.extract_feature_edges(          # same parameters as _add_edge_actor
        boundary_edges=True, feature_edges=True,
        non_manifold_edges=False, manifold_edges=False, feature_angle=1.0)
    assert edges.n_cells > 0
    diagonals = []
    for i in range(edges.n_cells):
        ids = edges.get_cell(i).point_ids
        a, b = edges.points[ids[0]], edges.points[ids[-1]]
        dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
        if dx > 1e-3 and dy > 1e-3:
            diagonals.append((tuple(a), tuple(b)))
    if pts_ok:
        assert diagonals == []
    else:
        # only the two copies (top + bottom) of the slanted outer edge (6000,2000)->(4000,3500)
        assert len(diagonals) == 2
        for a, b in diagonals:
            assert {round(a[0]), round(b[0])} == {4000, 6000}
