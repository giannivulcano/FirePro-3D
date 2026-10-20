""" UPDATES
- On selection highlight handles
- add handle to centerline
- Sprint Q: tick marks, label above line, draggable offset, text overhaul

"""

# annotations.py
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


# ---------------------------------------------------------------------------
# NOTE: HatchItem has been RETIRED (2026-08-22).
# Fills are now a property of 2-D geometry items (PolylineItem, RectangleItem,
# CircleItem) via Geometry2DMixin (two-layer fill_layers, UP1).
# Legacy "hatches" entries in old .fpd files are migrated on load in scene_io.
# ---------------------------------------------------------------------------
