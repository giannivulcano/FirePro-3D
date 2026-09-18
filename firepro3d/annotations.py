""" UPDATES
- On selection highlight handles
- add handle to centerline
- Sprint Q: tick marks, label above line, draggable offset, text overhaul

"""

# annotations.py
from PyQt6.QtGui import QPainterPath
from .constants import DEFAULT_ANNOTATION_GROUP

class Annotation:
    """Base class for CAD annotations."""

    def __init__(self):
        self._properties = {
            "Layer": {"type": "enum", "options": [DEFAULT_ANNOTATION_GROUP, "Notes", "Dimensions"], "value": DEFAULT_ANNOTATION_GROUP},
            "Color": {"type": "enum", "options": ["Black", "Red", "Blue"], "value": "Black"},
        }
        self.dimensions = [] #list of dimensions
        self.notes = [] #list of notes
        self.base_point_A = None
        self.base_point_B = None


    def get_properties(self):
        return self._properties

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value

    def add_dimension(self, dim):
        self.dimensions.append(dim)

    def add_note(self, note):
        self.notes.append(note)


# ═════════════════════════════════════════════════════════════════════════════
# Legacy migration helper — kept as a module-level function so scene_io.py
# can import it when loading old .fpd files that contain "hatches" entries.
# HatchItem itself has been retired; fills are now properties of the geometry.
# ═════════════════════════════════════════════════════════════════════════════

def _rebuild_path_from_elements(elements: list) -> "QPainterPath":
    """Rebuild a QPainterPath from a serialised element list.

    Each element is ``[el_type, x, y]`` where el_type follows
    QPainterPath.ElementType integer values (0=MoveTo, 1=LineTo, 2=CurveTo).
    Cubic curves consume three consecutive elements (control1, control2, end).
    This is the exact format that the retired HatchItem.to_dict() produced.
    """
    path = QPainterPath()
    i = 0
    while i < len(elements):
        el_type, x, y = elements[i]
        if el_type == 0:        # MoveToElement
            path.moveTo(x, y)
            i += 1
        elif el_type == 1:      # LineToElement
            path.lineTo(x, y)
            i += 1
        elif el_type == 2:      # CurveToElement — next 2 entries are data
            if i + 2 < len(elements):
                _, cx2, cy2 = elements[i + 1]
                _, ex, ey = elements[i + 2]
                path.cubicTo(x, y, cx2, cy2, ex, ey)
                i += 3
            else:
                i += 1  # malformed — skip
        else:
            i += 1
    return path


# ---------------------------------------------------------------------------
# NOTE: HatchItem has been RETIRED (2026-08-22).
# Fills are now a property of 2-D geometry items (PolylineItem, RectangleItem,
# CircleItem) via Geometry2DMixin (fill_type / fill_pattern / fill_opacity).
# Legacy "hatches" entries in old .fpd files are migrated on load in scene_io.
# ---------------------------------------------------------------------------
