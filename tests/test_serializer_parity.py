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
