"""Code-level System block table (System Blocks concept F4 / Q8; SB3 slice).

``SYSTEM_DEFAULTS`` guarantees a fallback block for every intrinsic-label
category: a mapped id missing from the project and every library resolves
here (``Model_Space.annotation_block``, design Q6 / G5). The ids are frozen
(concept F4): the promoted shipped file's id, never minted here.
"""
from __future__ import annotations

# Categories that carry an intrinsic label drawn by a System block (one
# Project Settings > Annotation row each).
ANNOTATION_CATEGORIES: tuple[str, ...] = ("Room", "Pipe", "Gridline", "Level",
                                          "Elevation", "Section", "Detail",
                                          "View Title", "Hydraulic Node")

# category -> the host field whose empty raw value means "nothing to show"
# (SB3 F1, ratified): an unresolved tag draws the orphan placeholder only
# when this field is present with a non-None raw value.
LABEL_FIELD: dict[str, str] = {"Room": "Name", "Pipe": "Diameter", "Gridline": "Mark",
                               "Level": "Level.Name", "Elevation": "Direction",
                               "Section": "Mark", "Detail": "Mark",
                               "View Title": "Scale", "Hydraulic Node": "NodeNumber"}

# Categories whose static geometry still draws when every host-bound field
# is blank (SB4b D3, user ruling 2026-11-02: an unlabelled gridline keeps its
# empty bubble). Every other category follows the Q13 "paints nothing" rule.
PAINT_WHEN_BLANK: frozenset[str] = frozenset({"Gridline", "Elevation", "Section", "Detail"})
# SB4f: an unplaced section or detail binds only Number and Sheet, both blank, and must still draw.
# "Level" is not listed: Level.Elevation is never None, so a datum head never has every field blank (SB4c).

# category -> frozen System block id (concept F4): the id of the promoted
# ``firepro3d/system_blocks/Tags/RoomTag.fpdb`` (SB3 U2 / U3, 2026-10-28).
# Never minted here; a re-promote keeps the id (system_promote Q5).
SYSTEM_DEFAULTS: dict[str, str] = {
    "Room": "system-tags-roomtag",
    "Pipe": "system-tags-pipelabel",
    "Gridline": "system-tags-gridlinebubble",
    "Level": "system-tags-leveldatum",
    "Elevation": "system-tags-elevationhead",      # SB4d D2 seeds
    "Section": "system-tags-sectionhead",
    "Detail": "system-tags-detailcallout",
    "View Title": "system-tags-viewtitle",      # SB4f
    "Hydraulic Node": "system-tags-hydraulicnode",      # SB4e
}

# The shipped Note block (design 2026-11-04-text-leader-annotations D8). Kept out of
# SYSTEM_DEFAULTS: it is not an intrinsic-label category, so no Annotation row.
NOTE_BLOCK_ID = "system-annotations-note"

# SB4g D7 / R10: the categories a real-size symbol block may draw. Values of
# ``BlockDefinition.symbol_for`` and the Block Editor "Symbol for" row. Riser is
# not an element category (D2: hence not ``host_category``).
SYMBOL_CATEGORIES: tuple[str, ...] = ("Sprinkler", "Water Supply", "Riser")
