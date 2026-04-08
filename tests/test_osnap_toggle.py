"""Unit tests for Model_Space OSNAP toggle state machine and signal."""

from __future__ import annotations

import pytest

from firepro3d.model_space import Model_Space


@pytest.fixture
def scene(qapp):
    """Fresh Model_Space per test."""
    s = Model_Space()
    yield s


def test_osnap_default_enabled(scene):
    assert scene._osnap_enabled is True
    assert scene._snap_engine.enabled is True


def test_toggle_flips_both_flags(scene):
    scene.toggle_osnap()
    assert scene._osnap_enabled is False
    assert scene._snap_engine.enabled is False
    scene.toggle_osnap()
    assert scene._osnap_enabled is True
    assert scene._snap_engine.enabled is True


def test_toggle_explicit_true_false(scene):
    scene.toggle_osnap(False)
    assert scene._osnap_enabled is False
    scene.toggle_osnap(False)
    assert scene._osnap_enabled is False
    scene.toggle_osnap(True)
    assert scene._osnap_enabled is True


def test_toggle_clears_snap_result(scene):
    scene._snap_result = object()
    scene.toggle_osnap()
    assert scene._snap_result is None


def test_toggle_emits_signal(scene):
    received: list[bool] = []
    scene.osnapToggled.connect(received.append)
    scene.toggle_osnap()  # True -> False
    scene.toggle_osnap()  # False -> True
    scene.toggle_osnap(False)  # True -> False
    assert received == [False, True, False]


def test_toggle_signal_emits_even_when_state_unchanged(scene):
    received: list[bool] = []
    scene.osnapToggled.connect(received.append)
    scene.toggle_osnap(True)  # already True
    assert received == [True]
