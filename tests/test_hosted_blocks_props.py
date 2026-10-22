"""G13 rows + D10 re-host (keep offset value, keep h, keep elevation)."""
import pytest
from PyQt6.QtWidgets import QApplication

from firepro3d import hosted_blocks as hb
from firepro3d.property_manager import PropertyManager
from tests._hosted_blocks_helpers import gridline, defn


def _setup(ms):
    b = gridline(ms, (0, -3000), (6000, -3000), "B")
    c = gridline(ms, (6000, -5000), (0, -5000), "C")         # anti-parallel
    gridline(ms, (500, 0), (500, -6000), "1")                # perpendicular
    inst = ms.place_block_instance(defn(ms).id, (0, 0), host={
        "gridline": b._uid, "offset_mm": 200.0, "along_mm": 1500.0,
        "elevation_mm": 2400.0, "facing": 1})
    return b, c, inst


def test_rows(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    p = inst.get_properties()
    assert "Level" not in p and "Level Offset" not in p
    assert p["Reference"]["type"] == "enum"
    assert p["Reference"]["value"] == "B"
    assert p["Reference"]["options"] == ["B", "C"]           # parallel only
    assert p["Offset"]["value_mm"] == 200.0
    assert p["Elevation"]["value_mm"] == 2400.0
    assert list(p)[:4] == ["Type", "Reference", "Offset", "Elevation"]


def test_unhosted_rows_unchanged(qapp, make_model_space):
    ms = make_model_space()
    inst = ms.place_block_instance(defn(ms).id, (0, 0))
    p = inst.get_properties()
    assert "Level" in p and "Level Offset" in p and "Reference" not in p


def test_gridlines_parallel(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    perp = ms._gridlines[2]
    assert hb.gridlines_parallel(b, c) and not hb.gridlines_parallel(b, perp)


def test_offset_elevation_reference_edits(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    inst.set_property("Offset", 300.0)
    assert inst.block_pos() == pytest.approx((1500.0, -3300.0))
    inst.set_property("Elevation", 1000.0)
    assert inst.z_range_mm() == (1000.0, 1000.0)
    inst.set_property("Reference", "C")
    # W(offset 0) = (1500, 3000); C origin (6000, 5000), u=(-1,0): along = 4500;
    # n_B.n_C = -1 -> facing -1; offset 300 kept on n_C=(0,-1): world (1500, 4700)
    assert inst.host == {"gridline": c._uid, "offset_mm": 300.0,
                         "along_mm": pytest.approx(4500.0),
                         "elevation_mm": 1000.0, "facing": -1}
    assert inst.block_pos() == pytest.approx((1500.0, -4700.0))


def _commit(inst, key, value):
    pm = PropertyManager()
    pm.show_properties(inst)
    QApplication.processEvents()
    pm._apply_property(key, value)


@pytest.mark.parametrize("key,value,field,new", [
    ("Offset", 300.0, "offset_mm", 300.0),
    ("Elevation", 1000.0, "elevation_mm", 1000.0),
])
def test_each_edit_is_one_undo_step(qapp, make_model_space, key, value, field, new):
    ms = make_model_space(); b, c, inst = _setup(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    old = inst.host[field]
    _commit(inst, key, value)
    assert inst.host[field] == new
    assert ms._undo_pos == depth0 + 1
    ms.undo()
    (now,) = ms._block_instances
    assert now.host[field] == old
    assert now.host["offset_mm"] == (200.0 if field != "offset_mm" else old)


def test_reference_edit_is_one_undo_step(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    _commit(inst, "Reference", "C")
    assert inst.host["gridline"] == c._uid
    assert ms._undo_pos == depth0 + 1
    ms.undo()
    (now,) = ms._block_instances
    assert now.host["gridline"] == b._uid and now.host["offset_mm"] == 200.0


def test_noop_commit_is_no_step(qapp, make_model_space):
    ms = make_model_space(); b, c, inst = _setup(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    _commit(inst, "Offset", 200.0)
    assert ms._undo_pos == depth0


def _label_texts(pm):
    form = pm._form
    out = []
    for r in range(form.rowCount()):
        it = form.itemAt(r, form.ItemRole.LabelRole)
        w = it.widget() if it is not None else None
        if w is not None and hasattr(w, "text"):
            out.append(w.text())
    return out


def test_hosted_block_gets_no_legacy_level_combo(qapp, make_model_space):
    """G13: Level is hidden for a hosted block, including the legacy combo the
    manager adds for items with a bare `.level` and a level manager."""
    ms = make_model_space(); b, c, inst = _setup(ms)
    from firepro3d.level_manager import LevelManager
    pm = PropertyManager()
    pm.set_level_manager(LevelManager())
    pm.show_properties(inst)
    QApplication.processEvents()
    labels = _label_texts(pm)
    assert "Reference" in labels                    # the walk sees real rows
    assert "Level" not in labels
    # positive control: the same walk finds Level on an unhosted block
    plain = ms.place_block_instance(defn(ms).id, (0, 0))
    pm.show_properties(plain)
    QApplication.processEvents()
    assert "Level" in _label_texts(pm)


@pytest.mark.parametrize("key,value", [("Offset", 300.0), ("Elevation", 1000.0)])
def test_unresolved_host_refuses_edit(qapp, make_model_space, key, value):
    ms = make_model_space(); b, c, inst = _setup(ms)
    ms.push_undo_state()
    depth0 = ms._undo_pos
    before = dict(inst.host)
    ms._gridlines.remove(b)                          # host no longer resolves
    assert ms.gridline_by_uid(b._uid) is None
    inst.set_property(key, value)
    assert inst.host == before
    assert ms._undo_pos == depth0


@pytest.mark.parametrize("c_reversed", [False, True])
@pytest.mark.parametrize("back_view", [False, True])
def test_rehost_30deg_keeps_h_and_viewing_side(qapp, make_model_space,
                                               c_reversed, back_view):
    import math
    from firepro3d.section_marker import SectionBasis
    L = 6000.0
    c30, s30 = math.cos(math.radians(30)), 0.5
    ms = make_model_space()
    # B: world origin (0,0), u=(c30,s30), n=(-s30,c30). Plan scene is Y-down,
    # so scene = (wx, -wy), ppm 1.
    b = gridline(ms, (0, 0), (L * c30, -L * s30), "B")
    # C: same direction, 4000 mm along n_B: world origin (-2000, 4000*c30).
    co = (-2000.0, 4000.0 * c30)
    ce = (co[0] + L * c30, co[1] + L * s30)
    p, q = ((co[0], -co[1]), (ce[0], -ce[1]))
    c = gridline(ms, q if c_reversed else p, p if c_reversed else q, "C")
    inst = ms.place_block_instance(defn(ms).id, (0, 0), host={
        "gridline": b._uid, "offset_mm": 200.0, "along_mm": 1500.0,
        "elevation_mm": 2400.0, "facing": 1})
    if back_view:
        # cut from far end back: D=-u, N=-n; A = (L u) + 5000 n so both
        # gridlines (0 and 4000 along n) lie in front of it at depth 5000/1000.
        a = (L * c30 - 5000.0 * s30, L * s30 + 5000.0 * c30)
        basis = SectionBasis.from_cut(a, (a[0] - L * c30, a[1] - L * s30), 1, 8000.0)
    else:
        basis = SectionBasis.from_cut((0.0, 0.0), (L * c30, L * s30), 1, 8000.0)
    before = hb.section_pose(basis, b, inst.host, 30.0, False, 1.0)
    # Independent expectations. World point = 1500*u + 200*n, so its u-component
    # is 1500 (n.u = 0). Section h is P.D (absolute): front D=u -> 1500;
    # back D=-u -> -1500. Front looks along n (facing +1 = host facing:
    # not mirrored, rot 30); back looks along -n (facing -1 != host: mirrored,
    # rot -30). Block depth is 5000-200 (back) or 200 (front): inside 8000.
    exp_h = -1500.0 if back_view else 1500.0
    assert before[0] == pytest.approx(exp_h)
    assert before[3] is back_view
    assert before[4] == pytest.approx(-30.0 if back_view else 30.0)

    inst.set_property("Reference", "C")
    assert inst.host["gridline"] == c._uid
    assert inst.host["offset_mm"] == 200.0           # non-zero offset kept
    # Reversed C has n_C = -n_B, so facing re-signs to -1; same-direction C: +1.
    assert inst.host["facing"] == (-1 if c_reversed else 1)
    after = hb.section_pose(basis, c, inst.host, 30.0, False, 1.0)
    assert after is not None                          # C (d=4000) is in depth
    assert after[0] == pytest.approx(exp_h)           # h unchanged
    assert after[1] == before[1]                      # elevation unchanged
    assert after[3] == before[3]                      # mirroring (viewing side)
    assert after[4] == pytest.approx(before[4])
