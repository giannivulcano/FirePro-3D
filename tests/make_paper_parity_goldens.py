"""Write the AC3 parity goldens. Run ONLY at base code (Task 1), never after
G1: a regenerated golden re-baselines its own guard (VC8).
Usage (worktree root): python -m pytest tests/make_paper_parity_goldens.py -q
(an explicit path is collected despite the name; tests/conftest.py loads as usual)
"""
import pytest

from tests.paper_parity_support import (GOLDEN_DIR, MODES, build_scene,
                                        load_mode_via_project,
                                        pin_model_colours, render)


@pytest.mark.parametrize("mode", MODES)
def test_write(qapp, shipped_hatches, mode):
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    pin_model_colours()
    load_mode_via_project(mode)
    ms = build_scene(shipped_hatches)
    assert render(ms).save(str(GOLDEN_DIR / f"{mode}.png"))
