"""PipeNetworkController — the pipe/node network concern extracted from
``Model_Space`` (decomposition slice 5).

A plain object (not a QObject) holding a back-ref to the scene. All scene-graph
mutation, signal emission, undo, and serialization stay on the scene and are
reached via ``self._scene``; this controller owns the pipe placement/creation/
deletion/geometry-correction behavior and the pipe Tab-cycle transient state.

Design: docs/superpowers/specs/2026-09-02-pipe-network-slice-design.md
Behavior (Rule A): docs/specs/pipe-placement-methodology.md
"""
from __future__ import annotations


class PipeNetworkController:
    def __init__(self, scene):
        self._scene = scene
        # pipe Tab-cycle transient (was Model_Space._pipe_tab_*)
        self._tab_candidates = []
        self._tab_index = 0
        self._tab_pos = None

    def clear(self):
        """Idempotent teardown of pipe placement transient state.

        Populated in a later slice (C3, set_mode + cancel wiring). Kept
        no-op-safe here so C1 wiring is inert until then.
        """
        self._tab_candidates = []
        self._tab_index = 0
        self._tab_pos = None
