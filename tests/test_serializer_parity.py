"""Red→green tests for the dual-serializer divergences (decomposition slice 3,
surgical fixes).

Each test asserts that the undo path (`_capture_network`/`_restore_network`)
agrees with the file path (`save_to_file`/`load_from_file`) for one field that
the 2026-08-28 decomposition map flagged as divergent (spec §4). Written to be
RED on the pre-fix code and GREEN after the surgical fix.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.annotations import NoteAnnotation, DimensionAnnotation
from firepro3d.wall import WallSegment
from firepro3d.water_supply import WaterSupply
from firepro3d.design_area import DesignArea
from firepro3d.level_manager import LevelManager

# The hand-serialized entity types the NetworkCodec unifies (slice 4).
_CODEC_KEYS = ("nodes", "pipes", "annotations", "water_supply", "design_areas")


def _scene_with_hand_serialized_entities(with_sprinkler=True):
    """A Model_Space carrying one of each codec-owned entity type.

    ``with_sprinkler=False`` omits the sprinkler head, whose derived properties
    (K-Factor/Coverage/Model options) are not byte-stable across load→save — a
    pre-existing sprinkler-serialization quirk unrelated to the codec.
    """
    ms = Model_Space()
    ms._level_manager = LevelManager()
    n1 = ms.add_node(0.0, 0.0)
    n2 = ms.add_node(1000.0, 0.0)
    ms.add_pipe(n1, n2)
    if with_sprinkler:
        ms.add_sprinkler(n1)
    note = NoteAnnotation(x=50.0, y=50.0, text_width=120.0)
    ms.addItem(note)
    ms.annotations.add_note(note)
    dim = DimensionAnnotation(QPointF(0.0, 0.0), QPointF(100.0, 0.0))
    ms.addItem(dim)
    ms.annotations.add_dimension(dim)
    ws = WaterSupply(200.0, 200.0)
    ms.addItem(ws)
    ms.water_supply_node = ws
    ms.sprinkler_system.supply_node = ws
    da = DesignArea([n1.sprinkler] if n1.has_sprinkler() else [])
    ms.addItem(da)
    ms.design_areas.append(da)
    return ms


def _capture_via_two_paths(build_scene, tmp_path):
    """Drive one network through BOTH deserialize paths; return (undo_scene, file_scene).

    undo_scene  = a fresh scene after _restore_network(capture_dict)
    file_scene  = a fresh scene after save_to_file -> load_from_file
    Both start from the SAME source scene so their resulting entity state must match
    field-for-field (Class-A parity).
    """
    src = build_scene()
    snap = src._capture_network()

    undo_scene = Model_Space()
    undo_scene._level_manager = LevelManager()
    undo_scene._restore_network(snap)

    fp = str(tmp_path / "parity.fpd")
    assert src.save_to_file(fp)
    file_scene = Model_Space()
    file_scene._level_manager = LevelManager()
    file_scene.load_from_file(fp)

    return undo_scene, file_scene


def test_undo_snapshot_pipe_props_are_stored_props(qapp):
    """#1: undo pipe props must equal the stored _properties (the file path's
    source), not pipe.get_properties() which injects synthesized display rows."""
    ms = Model_Space()
    n1 = ms.add_node(0.0, 0.0)
    n2 = ms.add_node(1000.0, 0.0)
    pipe = ms.add_pipe(n1, n2)
    snap = ms._capture_network()
    stored = {k: v["value"] for k, v in pipe._properties.items()}
    assert snap["pipes"][0]["properties"] == stored


def test_note_text_width_survives_undo(qapp):
    """#3: a note's wrap width must survive an undo round-trip (the file path
    passes text_width to the ctor; _restore_network dropped it)."""
    ms = Model_Space()
    note = NoteAnnotation(x=10.0, y=20.0, text_width=150.0)
    ms.addItem(note)
    ms.annotations.add_note(note)
    snap = ms._capture_network()
    ms._restore_network(snap)
    restored = ms.annotations.notes[0]
    assert abs(restored.textWidth() - 150.0) < 1e-6


def test_name_counters_recomputed_after_undo(qapp):
    """#2b: name counters must be recomputed on restore, as load_from_file does,
    so the next auto-name doesn't skip a number after undo."""
    ms = Model_Space()
    for i in (1, 2):
        w = WallSegment(QPointF(0, i * 100), QPointF(1000, i * 100))
        w.name = f"Wall {i}"
        ms.addItem(w)
        ms._walls.append(w)
    snap = ms._capture_network()
    ms._next_wall_num = 99  # stale counter
    ms._restore_network(snap)
    assert ms._next_wall_num == 3


def test_pipe_geometry_correct_after_undo(qapp):
    """#2a (empirical): pipe geometry must be correct after restore. If this is
    already green, Pipe.__init__ sets the line and no fix is needed."""
    ms = Model_Space()
    n1 = ms.add_node(0.0, 0.0)
    n2 = ms.add_node(1000.0, 0.0)
    pipe = ms.add_pipe(n1, n2)
    len_before = pipe.line().length()
    snap = ms._capture_network()
    ms._restore_network(snap)
    restored = ms.sprinkler_system.pipes[0]
    assert abs(restored.line().length() - len_before) < 1.0


# ── NetworkCodec (slice 4): file & undo now share one serialize home ──────────

def test_save_and_capture_agree_on_hand_serialized_types(qapp, tmp_path):
    """The file path (save_to_file) and undo path (_capture_network) must emit
    IDENTICAL dicts for every codec-owned entity type — structurally guaranteed
    now that both route through network_codec."""
    ms = _scene_with_hand_serialized_entities()
    fp = str(tmp_path / "codec.fpd")
    assert ms.save_to_file(fp)
    saved = json.load(open(fp, encoding="utf-8"))
    cap = ms._capture_network()
    for key in _CODEC_KEYS:
        assert saved[key] == cap[key], f"file/undo diverge on {key!r}"


def test_codec_sections_stable_across_file_roundtrip(qapp, tmp_path):
    """save -> load -> save reproduces the codec-owned sections byte-for-byte
    (round-trip stability of the file format for these types)."""
    ms = _scene_with_hand_serialized_entities(with_sprinkler=False)
    fp1 = str(tmp_path / "a.fpd")
    assert ms.save_to_file(fp1)
    ms2 = Model_Space()
    ms2._level_manager = LevelManager()
    ms2.load_from_file(fp1)
    fp2 = str(tmp_path / "b.fpd")
    assert ms2.save_to_file(fp2)
    a = json.load(open(fp1, encoding="utf-8"))
    b = json.load(open(fp2, encoding="utf-8"))
    for key in _CODEC_KEYS:
        assert a[key] == b[key], f"codec section {key!r} not stable across round-trip"


# ── Slice 4b: deserialize field-application parity (undo-restore vs file-load) ──

def test_deserialize_parity_dimensions_notes(qapp, tmp_path):
    """Dimension + note field state is identical via undo-restore and file-load."""
    u, f = _capture_via_two_paths(
        lambda: _scene_with_hand_serialized_entities(with_sprinkler=False), tmp_path)
    # dimensions
    ud, fd = u.annotations.dimensions[0], f.annotations.dimensions[0]
    assert (ud._p1.x(), ud._p1.y()) == (fd._p1.x(), fd._p1.y())
    assert (ud._p2.x(), ud._p2.y()) == (fd._p2.x(), fd._p2.y())
    assert ud._offset_dist == fd._offset_dist
    assert ud.level == fd.level
    # notes
    un, fn = u.annotations.notes[0], f.annotations.notes[0]
    assert abs(un.textWidth() - fn.textWidth()) < 1e-6
    assert (un.scenePos().x(), un.scenePos().y()) == (fn.scenePos().x(), fn.scenePos().y())
    assert un.level == fn.level


def test_deserialize_parity_water_supply(qapp, tmp_path):
    u, f = _capture_via_two_paths(
        lambda: _scene_with_hand_serialized_entities(with_sprinkler=False), tmp_path)
    uw, fw = u.water_supply_node, f.water_supply_node
    assert (uw.pos().x(), uw.pos().y()) == (fw.pos().x(), fw.pos().y())
    uprops = {k: v["value"] for k, v in uw.get_properties().items()}
    fprops = {k: v["value"] for k, v in fw.get_properties().items()}
    assert uprops == fprops


def test_deserialize_parity_nodes_pipes(qapp, tmp_path):
    u, f = _capture_via_two_paths(
        lambda: _scene_with_hand_serialized_entities(with_sprinkler=False), tmp_path)
    un = list(u.sprinkler_system.nodes)
    fn = list(f.sprinkler_system.nodes)
    assert len(un) == len(fn)
    for a, b in zip(un, fn):
        assert (a.scenePos().x(), a.scenePos().y()) == (b.scenePos().x(), b.scenePos().y())
        assert a.level == b.level
        assert a.ceiling_level == b.ceiling_level
        assert abs(a.ceiling_offset - b.ceiling_offset) < 1e-6
        assert abs(a.z_pos - b.z_pos) < 1e-6
        assert a._room_name == b._room_name
    up = u.sprinkler_system.pipes[0]
    fp = f.sprinkler_system.pipes[0]
    assert {k: v["value"] for k, v in up._properties.items()} == \
           {k: v["value"] for k, v in fp._properties.items()}
    assert up.level == fp.level


def test_sprinkler_ceiling_parity_across_paths(qapp, tmp_path):
    """A sprinklered node's ceiling fields AND sprinkler scene position must be
    identical whether restored via undo or loaded from file (slice 4b converges
    the ceiling-vs-add_sprinkler ordering)."""
    def build():
        ms = Model_Space()
        ms._level_manager = LevelManager()
        n = ms.add_node(300.0, 400.0)
        ms.add_sprinkler(n)
        n.ceiling_level = "Level 1"
        n.ceiling_offset = -101.6  # -4 in, non-default
        n._properties["Ceiling Level"]["value"] = n.ceiling_level
        n._properties["Ceiling Offset"]["value"] = str(n.ceiling_offset)
        n._recompute_z_pos()
        return ms
    u, f = _capture_via_two_paths(build, tmp_path)
    un = next(iter(u.sprinkler_system.nodes))
    fn = next(iter(f.sprinkler_system.nodes))
    assert un.ceiling_level == fn.ceiling_level
    assert abs(un.ceiling_offset - fn.ceiling_offset) < 1e-6
    assert abs(un.z_pos - fn.z_pos) < 1e-6
    assert un.has_sprinkler() and fn.has_sprinkler()
    assert (un.sprinkler.scenePos().x(), un.sprinkler.scenePos().y()) == \
           (fn.sprinkler.scenePos().x(), fn.sprinkler.scenePos().y())


def test_full_roundtrip_and_capture_bytes_stable(qapp, tmp_path):
    """After the 4b unify: save->load->save reproduces the codec sections byte-for-byte,
    and _capture_network of the reloaded scene equals the original capture (undo bytes
    stable — a deserialize-only slice must not perturb serialize)."""
    ms = _scene_with_hand_serialized_entities(with_sprinkler=False)
    cap_before = ms._capture_network()
    fp1 = str(tmp_path / "a.fpd")
    assert ms.save_to_file(fp1)
    ms2 = Model_Space()
    ms2._level_manager = LevelManager()
    ms2.load_from_file(fp1)
    fp2 = str(tmp_path / "b.fpd")
    assert ms2.save_to_file(fp2)
    a = json.load(open(fp1, encoding="utf-8"))
    b = json.load(open(fp2, encoding="utf-8"))
    for key in _CODEC_KEYS:
        assert a[key] == b[key], f"codec section {key!r} not stable across round-trip"
    cap_after = ms2._capture_network()
    for key in _CODEC_KEYS:
        assert cap_before[key] == cap_after[key], f"capture {key!r} drifted"
