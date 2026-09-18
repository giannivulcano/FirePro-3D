"""RETIRED (containment C1/C8 — 2026-09-17).

DimensionAnnotation has been deleted as part of the model-space dimension
retirement (task 8.4). All tests in this file verified DimensionAnnotation grip
behavior (offset-drag parity, undo-per-gesture, Esc-restore, snap fallback) —
that behavior is intentionally removed per the containment contract.

No replacement tests needed: the class no longer exists and the authoring gate
(test_authoring_gate.py::test_dimension_press_handler_removed) confirms the
dispatch handler is gone.
"""
