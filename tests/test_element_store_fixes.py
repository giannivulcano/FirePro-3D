"""Element store drift fixes (docs/specs/element-store.md D6 commits 8-10; G6, G7)."""
from __future__ import annotations

from tests._ph1_helpers import add_block, add_roof, ph1_cleanup, scene  # noqa: F401


def test_g6_roof_has_scale_manager_after_undo(qapp):
    ms = scene()
    add_roof(ms)
    ms.push_undo_state()
    add_roof(ms)
    ms.push_undo_state()
    ms.undo()                                   # the real restore path
    assert ms._roofs and all(r._scale_manager_ref is ms.scale_manager for r in ms._roofs)
