"""Code-level System block table (System Blocks concept F4 / Q8; SB3 slice).

``SYSTEM_DEFAULTS`` guarantees a fallback block for every intrinsic-label
category: a mapped id missing from the project and every library resolves
here (``Model_Space.annotation_block``, design Q6 / G5). The ids are frozen
(concept F4): the promoted shipped file's id, never minted here.
"""
from __future__ import annotations

# Categories that carry an intrinsic label drawn by a System block (one
# Project Settings > Annotation row each).
ANNOTATION_CATEGORIES: tuple[str, ...] = ("Room",)

# category -> frozen System block id. Filled by the SB3 plan's Task 11 from
# the promoted ``firepro3d/system_blocks/Tags/RoomTag.fpdb`` (user step U3);
# empty until then (a tag then draws the orphan placeholder, never vanishes).
SYSTEM_DEFAULTS: dict[str, str] = {}
