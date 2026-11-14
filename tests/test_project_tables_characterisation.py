"""Project tables characterisation (design DD6): parity against goldens
captured at base 2509b668. Regenerate only at base: FP3D_REGEN_GOLDENS=1."""
from __future__ import annotations

import pytest

from tests._mainwindow_helpers import dispose_main_window
from tests._project_tables_helpers import FIXDIR, open_main_window, prepared_copy, resave_text


def test_resave_is_deterministic(qapp, monkeypatch, tmp_path):
    src = prepared_copy(FIXDIR / "hf5_legacy.fpd", tmp_path)
    w = open_main_window(monkeypatch, tmp_path)
    try:
        assert w._apply_loaded_file(str(src)) is not False
        a = resave_text(w.scene, tmp_path)
        b = resave_text(w.scene, tmp_path)
        assert a == b
    finally:
        dispose_main_window(w)
