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

# category -> the host field whose empty raw value means "nothing to show"
# (SB3 F1, ratified): an unresolved tag draws the orphan placeholder only
# when this field is present with a non-None raw value.
LABEL_FIELD: dict[str, str] = {"Room": "Name"}

# category -> frozen System block id (concept F4): the id of the promoted
# ``firepro3d/system_blocks/Tags/RoomTag.fpdb`` (SB3 U2 / U3, 2026-10-28).
# Never minted here; a re-promote keeps the id (system_promote Q5).
SYSTEM_DEFAULTS: dict[str, str] = {
    "Room": "system-tags-roomtag",
}
