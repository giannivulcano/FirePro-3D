"""Red→green tests for the dual-serializer divergences (decomposition slice 3,
surgical fixes).

Each test asserts that the undo path (`_capture_network`/`_restore_network`)
agrees with the file path (`save_to_file`/`load_from_file`) for one field that
the 2026-08-28 decomposition map flagged as divergent (spec §4). Written to be
RED on the pre-fix code and GREEN after the surgical fix.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.annotations import NoteAnnotation
from firepro3d.wall import WallSegment


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
