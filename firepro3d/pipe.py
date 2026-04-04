import math
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsItem, QGraphicsTextItem, QStyle
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath, QPainterPathStroker
from PyQt6.QtCore import Qt, QPointF
from CAD_Math import CAD_Math

from constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER, DEFAULT_CEILING_OFFSET_MM
from displayable_item import DisplayableItemMixin

class Pipe(DisplayableItemMixin, QGraphicsLineItem):
    SNAP_TOLERANCE_DEG = 7.5  # snap if within this angle

    # Line Type display widths (mm, real-world, scales with zoom)
    BRANCH_WIDTH_MM = 75.0
    MAIN_WIDTH_MM = 150.0

    # Diameters that auto-assign as "Main" (≥ 3")
    _MAIN_DIAMETERS = {"3\"Ø", "4\"Ø", "5\"Ø", "6\"Ø", "8\"Ø"}

    # Internal diameter keys (stored in _properties and serialization)
    _INTERNAL_DIAMETERS = ["1\"Ø", "1-½\"Ø", "2\"Ø", "3\"Ø", "4\"Ø", "5\"Ø", "6\"Ø", "8\"Ø"]

    # Imperial display strings (Ø sign first, space before value)
    _IMPERIAL_DIAMETERS = ["Ø 1\"", "Ø 1-½\"", "Ø 2\"", "Ø 3\"", "Ø 4\"", "Ø 5\"", "Ø 6\"", "Ø 8\""]

    # Metric nominal diameter display strings (DN / nominal mm)
    _METRIC_DIAMETERS = ["Ø 25 mm", "Ø 40 mm", "Ø 50 mm", "Ø 80 mm", "Ø 100 mm", "Ø 125 mm", "Ø 150 mm", "Ø 200 mm"]

    # Mappings: internal key ↔ display strings
    _INT_TO_IMPERIAL = dict(zip(_INTERNAL_DIAMETERS, _IMPERIAL_DIAMETERS))
    _INT_TO_METRIC = dict(zip(_INTERNAL_DIAMETERS, _METRIC_DIAMETERS))
    _DISPLAY_TO_INT = {**dict(zip(_IMPERIAL_DIAMETERS, _INTERNAL_DIAMETERS)),
                       **dict(zip(_METRIC_DIAMETERS, _INTERNAL_DIAMETERS))}

    # Nominal pipe OD in inches — used to set the 2D line width to the real
    # pipe size (1 scene unit = 1 mm, so OD_in × 25.4 = pen width in scene units).
    NOMINAL_OD_IN: dict[str, float] = {
        '1"Ø': 1.315, '1-½"Ø': 1.900, '2"Ø': 2.375, '3"Ø': 3.500,
        '4"Ø': 4.500, '5"Ø': 5.563, '6"Ø': 6.625, '8"Ø': 8.625,
        # Legacy keys without Ø (for backward-compat with older projects / 3D view)
        '1"': 1.315, '1-½"': 1.900, '2"': 2.375, '3"': 3.500,
        '4"': 4.500, '5"': 5.563, '6"': 6.625, '8"': 8.625,
    }

    # Inside diameter (inches) by schedule and nominal pipe size.
    # Used by the hydraulic solver (Hazen-Williams requires actual ID, not nominal).
    # Keys match the "Diameter" property option strings.
    INNER_DIAMETER_IN: dict[str, dict[str, float]] = {
        "Sch 10":  {"1\"Ø": 1.097, "1-½\"Ø": 1.682, "2\"Ø": 2.157, "3\"Ø": 3.260,
                    "4\"Ø": 4.260, "5\"Ø": 5.295, "6\"Ø": 6.357, "8\"Ø": 8.329},
        "Sch 40":  {"1\"Ø": 1.049, "1-½\"Ø": 1.610, "2\"Ø": 2.067, "3\"Ø": 3.068,
                    "4\"Ø": 4.026, "5\"Ø": 5.047, "6\"Ø": 6.065, "8\"Ø": 7.981},
        "Sch 80":  {"1\"Ø": 0.957, "1-½\"Ø": 1.500, "2\"Ø": 1.939, "3\"Ø": 2.900,
                    "4\"Ø": 3.826, "5\"Ø": 4.813, "6\"Ø": 5.761, "8\"Ø": 7.625},
        "Sch 40S": {"1\"Ø": 1.049, "1-½\"Ø": 1.610, "2\"Ø": 2.067, "3\"Ø": 3.068,
                    "4\"Ø": 4.026, "5\"Ø": 5.047, "6\"Ø": 6.065, "8\"Ø": 7.981},
        "Sch 10S": {"1\"Ø": 1.097, "1-½\"Ø": 1.682, "2\"Ø": 2.157, "3\"Ø": 3.260,
                    "4\"Ø": 4.260, "5\"Ø": 5.295, "6\"Ø": 6.357, "8\"Ø": 8.329},
    }

    def __init__(self, node1, node2):

        super().__init__()
        # Properties
        self._properties = {
            "Diameter":    {"type": "enum",   "value": "1\"Ø",            "options": ["1\"Ø", "1-½\"Ø", "2\"Ø","3\"Ø","4\"Ø","5\"Ø","6\"Ø","8\"Ø"]},
            "Schedule":    {"type": "enum",   "value": "Sch 40",         "options": ["Sch 10", "Sch 40", "Sch 80", "Sch 40S", "Sch 10S"]},
            "C-Factor":    {"type": "string", "value": "120"},
            "Material":    {"type": "enum",   "value": "Galvanized Steel","options": ["Galvanized Steel", "Stainless Steel", "Black Steel", "PVC"]},
            "Ceiling Level":      {"type": "level_ref", "value": DEFAULT_LEVEL},
            "Ceiling Offset":{"type": "string", "value": "-50.8"},
            "Line Type":   {"type": "enum",   "value": "Branch",         "options": ["Branch", "Main"]},
            "Colour":      {"type": "enum",   "value": "Red",            "options": ["Black", "White", "Red", "Blue", "Grey"]},
            "Phase":       {"type": "enum",   "value": "New",            "options": ["New", "Existing", "Demo"]},
            "── Label ──": {"type": "label",  "value": ""},
            "Show Label":  {"type": "enum",   "value": "True",           "options": ["True", "False"]},
            "Label Size": {"type": "string", "value": "12"},
        }

        self.node1 = node1
        self.node2 = node2
        self.colour = None
        self.length = 0.0

        # Shared display-manager attributes
        self.init_displayable()

        # Pipe-specific attributes
        self.ceiling_level: str = DEFAULT_LEVEL
        self.ceiling_offset: float = DEFAULT_CEILING_OFFSET_MM
        self._display_scale: float = 1.0

        # Per-node elevation for template placement
        self.node1_ceiling_level: str = DEFAULT_LEVEL
        self.node1_ceiling_offset: float = DEFAULT_CEILING_OFFSET_MM
        self.node2_ceiling_level: str = DEFAULT_LEVEL
        self.node2_ceiling_offset: float = DEFAULT_CEILING_OFFSET_MM
        self._placement_phase: int = 0  # 0=before 1st click, 1=before 2nd click

        self.label = QGraphicsTextItem("", self)  # Child of pipe

        self.set_pipe_display()
        
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(5)    # above walls (-50) and floors (-80), below nodes (10)
        
        # track node movement
        if node1 and node2:
            self.node1.pipes.append(self)
            self.node2.pipes.append(self)
            self.update_geometry()

    def set_pipe_display(self):
        colour = QColor(self._display_color or self._properties["Colour"]["value"])
        line_weight = self.display_width_mm() * self._display_scale
        pen = QPen(colour, line_weight)
        # Use RoundCap unless both ends are cap fittings; mixed case is
        # handled in paint() by drawing a manual round end on the non-cap side.
        n1_cap = (self.node1 and hasattr(self.node1, "fitting")
                  and self.node1.fitting and self.node1.fitting.type == "cap")
        n2_cap = (self.node2 and hasattr(self.node2, "fitting")
                  and self.node2.fitting and self.node2.fitting.type == "cap")
        if n1_cap and n2_cap:
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        elif n1_cap or n2_cap:
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)  # mixed: paint() adds round end
        else:
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)

    # --------------------------------------------
    # PIPE LABEL HELPERS
    def _is_vertical(self) -> bool:
        """True when both endpoints share the same XY but differ in z_pos."""
        if not self.node1 or not self.node2:
            return False
        p1, p2 = self.node1.scenePos(), self.node2.scenePos()
        dx, dy = p1.x() - p2.x(), p1.y() - p2.y()
        dz = abs(getattr(self.node1, "z_pos", 0) - getattr(self.node2, "z_pos", 0))
        return (dx * dx + dy * dy) < 100 and dz > 0.01

    def update_label(self, visible=None):
        if not self.node1 or not self.node2:
            return  # cannot position label yet

        if not hasattr(self, "label") or self.label is None:
            self.label = QGraphicsTextItem(parent=self)
            self.label.setDefaultTextColor(Qt.GlobalColor.black)
            # No ItemIgnoresTransformations — label is in model-space units

        # Hide label for vertical pipes (same XY, different z) in plan view
        if self._is_vertical():
            self.label.setVisible(False)
            return

        visible = True if self._properties["Show Label"]["value"] == "True" else False
        self.label.setVisible(visible)
        if not visible:
            return  # skip extra work if hidden

        # Format text — show display diameter (Ø prefix, metric when metric)
        diameter = self._properties.get('Diameter', {}).get('value', 'N/A')
        if self._is_metric_display():
            diameter = self._INT_TO_METRIC.get(diameter, diameter)
        else:
            diameter = self._INT_TO_IMPERIAL.get(diameter, diameter)
        scene = self.scene()
        if scene and hasattr(scene, "scale_manager"):
            length = scene.scale_manager.scene_to_display(getattr(self, "length", 0.0))
        else:
            length = f"{self.length:.1f} mm"

        # Text height from Label Size property (inches → mm for scene units)
        try:
            _label_in = float(self._properties.get(
                "Label Size", {}).get("value", "12"))
        except (ValueError, TypeError):
            _label_in = 12.0
        text_h = _label_in * 25.4   # inches → mm
        # Gap between rows = actual rendered pipe width (incl. display scale) + margin
        gap = self.display_width_mm() * self._display_scale + text_h * 0.3

        # Include hydraulic results if available
        hr_lines = ""
        if scene and hasattr(scene, "hydraulic_result") and scene.hydraulic_result is not None:
            result = scene.hydraulic_result
            q = result.pipe_flows.get(self)
            hf = result.pipe_friction_loss.get(self)
            if q is not None:
                hr_lines += (f"<div style='font-size:{text_h:.0f}px; "
                             f"margin-top:{gap:.0f}px; color:#00aaff;'>"
                             f"{q:.1f} gpm</div>")
            if hf is not None:
                hr_lines += (f"<div style='font-size:{text_h:.0f}px; "
                             f"margin-top:{gap:.0f}px; color:#ffaa00;'>"
                             f"{hf:.2f} psi</div>")

        html = (f"<div style='text-align:center;'>"
                f"<div style='font-size:{text_h:.0f}px;'>{diameter}</div>"
                f"<div style='font-size:{text_h:.0f}px; "
                f"margin-top:{gap:.0f}px;'>{length}</div>"
                f"{hr_lines}</div>")
        self.label.setHtml(html)
        # Measure natural width then lock it so text-align:center works
        self.label.setTextWidth(-1)
        ideal = self.label.document().idealWidth()
        self.label.setTextWidth(ideal)

        self.set_label_position()


    def set_label_position(self):
        line = self.line()  # QLineF
    
        v1 = CAD_Math.get_unit_vector(line.p1(),line.p2())
        # If pointing left, flip direction
        if v1.x() < 0:
            v1 = QPointF(-v1.x(), -v1.y())
        v2 = QPointF(1, 0)
        angle = -CAD_Math.get_angle_between_vectors(v1, v2, signed=True)
        if angle == 90:
            angle = -90
        
        mid_point = QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
        bounds = self.label.boundingRect()
        center = bounds.center()

        # set transform origin so future rotations work around the center
        self.label.setTransformOriginPoint(center)

        # move label so its center sits on line midpoint
        self.label.setPos(mid_point - center)
        self.label.setRotation(angle)

    # --------------------------------------------------------------
    # PIPE HELPERS

    def update_geometry(self):
        start = self.node1.scenePos()
        end = self.node2.scenePos()

        # Snap visually for the pipe line
        snapped_end = self.snap_point_45_if_close(start, end)
        self.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())

        # Store the 2D scene-pixel length (used by label, get_length_ft, etc.)
        self.length = CAD_Math.get_vector_length(self.node1.scenePos(), self.node2.scenePos())

        self.update_label()  # <- move here

    def shape(self):
        """Viewport-scale-aware hit path — always at least ~10 screen pixels wide.

        Pipes use a non-cosmetic scene-unit pen whose width shrinks when the scale
        manager converts mm → scene units.  Without this override, a thin calibrated
        pipe can become nearly impossible to click.
        """
        ln = self.line()
        path = QPainterPath()
        path.moveTo(ln.p1())
        path.lineTo(ln.p2())
        stroker = QPainterPathStroker()
        sc = self.scene()
        views = sc.views() if sc else []
        scale = views[0].transform().m11() if views else 1.0
        # Take max of actual pen width and 16 screen-pixel equivalent
        hit_w = max(self.pen().widthF(), 16.0 / max(scale, 1e-6))
        stroker.setWidth(hit_w)
        return stroker.createStroke(path)


    @classmethod
    def snap_point_45_if_close(cls, start: QPointF, end: QPointF) -> QPointF:
        dx = end.x() - start.x()
        dy = end.y() - start.y()

        angle = math.degrees(math.atan2(dy, dx))
        snap_angle = round(angle / 45) * 45

        # only snap if within tolerance
        if abs(angle - snap_angle) <= cls.SNAP_TOLERANCE_DEG:
            length = math.hypot(dx, dy)
            rad = math.radians(snap_angle)
            return QPointF(start.x() + length * math.cos(rad),
                           start.y() + length * math.sin(rad))
        else:
            return end
        
    def _is_metric_display(self) -> bool:
        """True when the current display unit is metric (mm or m)."""
        sm = self._get_scale_manager()
        if sm is not None:
            from scale_manager import DisplayUnit
            return sm.display_unit in (DisplayUnit.METRIC_MM, DisplayUnit.METRIC_M)
        return True  # default to metric when no scale manager

    def _get_scene(self):
        """Return the scene, checking fallbacks for template pipes."""
        sc = self.scene() if callable(getattr(self, "scene", None)) else None
        if sc is not None:
            return sc
        return getattr(self, "_scene_ref", None)

    def _ceiling_elevation_str(self) -> str:
        """Return the effective ceiling elevation (level minus slab thickness)."""
        sc = self._get_scene()
        lm = getattr(sc, "_level_manager", None) if sc else None
        if lm is None:
            return ""
        lvl = lm.get(self.ceiling_level)
        if lvl is None:
            return ""
        # Find thickest floor slab on the ceiling level
        slab_thickness = 0.0
        for slab in getattr(sc, "_floor_slabs", []):
            if getattr(slab, "level", None) == self.ceiling_level:
                slab_thickness = max(slab_thickness, slab._thickness_mm)
        elev = lvl.elevation - slab_thickness
        return f"({self._fmt(elev)})"

    def get_properties(self):
        props = self._properties.copy()
        # Format ceiling offset for display using project units
        props["Ceiling Offset"] = dict(props["Ceiling Offset"])
        props["Ceiling Offset"]["value"] = self._fmt(self.ceiling_offset)
        # Annotate Ceiling Level with effective elevation
        props["Ceiling Level"] = dict(props["Ceiling Level"])
        ceil_str = self._ceiling_elevation_str()
        if ceil_str:
            props["Ceiling Level"]["suffix"] = ceil_str
        # Show diameter with Ø prefix; metric nominal sizes when metric display
        props["Diameter"] = dict(props["Diameter"])
        int_val = props["Diameter"]["value"]
        if self._is_metric_display():
            props["Diameter"]["options"] = list(self._METRIC_DIAMETERS)
            props["Diameter"]["value"] = self._INT_TO_METRIC.get(int_val, int_val)
        else:
            props["Diameter"]["options"] = list(self._IMPERIAL_DIAMETERS)
            props["Diameter"]["value"] = self._INT_TO_IMPERIAL.get(int_val, int_val)
        # Read-only 3D length in display units
        z1 = self.node1.z_pos if self.node1 else 0.0
        z2 = self.node2.z_pos if self.node2 else 0.0
        dz = abs(z2 - z1)
        sc = self._get_scene()
        sm = getattr(sc, "scale_manager", None) if sc else None
        if sm:
            # Convert 2D scene-pixel length to real-world mm
            if sm.is_calibrated:
                horiz_mm = self.length / sm.pixels_per_mm
            else:
                horiz_mm = self.length  # uncalibrated: 1 scene unit ≈ 1 mm
            length_mm = math.sqrt(horiz_mm ** 2 + dz ** 2)
            length_str = sm.format_length(length_mm)
        else:
            length_mm = math.sqrt(self.length ** 2 + dz ** 2)
            length_str = f"{length_mm:.1f} mm"
        props["Length"] = {"type": "label", "value": length_str}

        # Template node elevation sections (node1/node2 are None for templates)
        if self.node1 is None and self.node2 is None:
            # Remove pipe-level ceiling props — they're replaced by per-node ones
            props.pop("Ceiling Level", None)
            props.pop("Ceiling Offset", None)

            phase = getattr(self, "_placement_phase", 0)
            n1_ro = phase != 0
            n2_ro = phase != 1

            props["── Node 1 ──"] = {"type": "label", "value": ""}
            props["N1 Ceiling Level"] = {
                "type": "level_ref", "value": self.node1_ceiling_level,
                "readonly": n1_ro,
            }
            props["N1 Ceiling Offset"] = {
                "type": "string", "value": self._fmt(self.node1_ceiling_offset),
                "readonly": n1_ro,
            }
            props["── Node 2 ──"] = {"type": "label", "value": ""}
            props["N2 Ceiling Level"] = {
                "type": "level_ref", "value": self.node2_ceiling_level,
                "readonly": n2_ro,
            }
            props["N2 Ceiling Offset"] = {
                "type": "string", "value": self._fmt(self.node2_ceiling_offset),
                "readonly": n2_ro,
            }

        return props

    def set_property(self, key, value):
        # Accept legacy names from old save files
        if key in ("Elevation 1", "Elevation 2", "Line Weight", "Length"):
            return  # discard old/removed or read-only properties
        # Per-node template ceiling properties
        if key in ("N1 Ceiling Level", "N2 Ceiling Level"):
            attr = "node1_ceiling_level" if key.startswith("N1") else "node2_ceiling_level"
            setattr(self, attr, str(value))
            return
        if key in ("N1 Ceiling Offset", "N2 Ceiling Offset"):
            attr = "node1_ceiling_offset" if key.startswith("N1") else "node2_ceiling_offset"
            sm = self._get_scale_manager()
            if isinstance(value, (int, float)):
                setattr(self, attr, float(value))
            elif sm:
                parsed = sm.parse_dimension(str(value), sm.bare_number_unit())
                if parsed is not None:
                    setattr(self, attr, parsed)
            else:
                try:
                    setattr(self, attr, float(value))
                except (ValueError, TypeError):
                    pass
            return
        if key in ("Elevation", "Elevation Offset", "Ceiling Offset (in)"):
            key = "Ceiling Offset"
        if key == "Ceiling Offset":
            # Parse dimension input and store canonical mm value
            if isinstance(value, (int, float)):
                self.ceiling_offset = float(value)
            else:
                sm = self._get_scale_manager()
                if sm:
                    parsed = sm.parse_dimension(str(value), sm.bare_number_unit())
                    if parsed is not None:
                        self.ceiling_offset = parsed
                else:
                    try:
                        self.ceiling_offset = float(value)
                    except (ValueError, TypeError):
                        pass
            self._properties["Ceiling Offset"]["value"] = str(self.ceiling_offset)
        elif key in self._properties:
            # Convert display diameter string back to internal key
            if key == "Diameter" and value in self._DISPLAY_TO_INT:
                value = self._DISPLAY_TO_INT[value]
            self._properties[key]["value"] = value

            if key == "Diameter":
                # Auto-assign Line Type based on diameter threshold
                if value in self._MAIN_DIAMETERS:
                    self._properties["Line Type"]["value"] = "Main"
                else:
                    self._properties["Line Type"]["value"] = "Branch"
            if key in ("Diameter", "Show Label", "Label Size"):
                self.update_label()
            if key in ("Colour", "Diameter", "Line Type"):
                self.set_pipe_display()
            if key == "Level":
                self.level = str(value)
            elif key == "Ceiling Level":
                self.ceiling_level = str(value)
    
    def set_properties(self, template: "Pipe"):
        """Copy property values from a template pipe."""
        for key, meta in template.get_properties().items():
            if key == "Ceiling Offset":
                # Copy raw mm value directly — the display-formatted string
                # from get_properties() can't be parsed when the new pipe
                # has no scene (no ScaleManager available yet).
                self.ceiling_offset = template.ceiling_offset
                self._properties["Ceiling Offset"]["value"] = str(template.ceiling_offset)
                continue
            self.set_property(key, meta["value"])
        # Ensure pipe-level ceiling properties are copied even when
        # get_properties() omits them (template mode replaces with N1/N2)
        self.ceiling_level = template.ceiling_level
        self._properties["Ceiling Level"]["value"] = template.ceiling_level
        if self.ceiling_offset == DEFAULT_CEILING_OFFSET_MM:
            self.ceiling_offset = template.ceiling_offset
            self._properties["Ceiling Offset"]["value"] = str(template.ceiling_offset)

    def z_range_mm(self) -> tuple[float, float] | None:
        """Return (z_bottom, z_top) spanning the full storey range of both nodes.

        Uses the nodes' floor-to-ceiling range so the pipe is visible in
        plan views even though the hanging z_pos is near the ceiling.
        """
        r1 = self.node1.z_range_mm() if self.node1 else None
        r2 = self.node2.z_range_mm() if self.node2 else None
        if r1 is None and r2 is None:
            return None
        if r1 is None:
            return r2
        if r2 is None:
            return r1
        return (min(r1[0], r2[0]), max(r1[1], r2[1]))

    def display_width_mm(self) -> float:
        """Return display line width in mm based on Line Type (Main/Branch)."""
        return self.MAIN_WIDTH_MM if self._properties["Line Type"]["value"] == "Main" else self.BRANCH_WIDTH_MM

    def get_od_mm(self) -> float:
        """Return the display width in mm.

        Now delegates to display_width_mm() (Main/Branch system).
        Kept for backward compatibility with display_manager.py and label gap calc.
        """
        return self.display_width_mm()

    def get_inner_diameter(self) -> float:
        """Return the actual inside diameter in inches for the current nominal size and schedule.
        Used by the hydraulic solver (Hazen-Williams requires ID, not nominal diameter).
        Falls back to 2\"-Sch-40 (2.067 in) if the combination is not found.
        """
        schedule = self._properties["Schedule"]["value"]
        nominal  = self._properties["Diameter"]["value"]
        schedule_map = self.INNER_DIAMETER_IN.get(schedule, self.INNER_DIAMETER_IN["Sch 40"])
        return schedule_map.get(nominal, 2.067)

    def get_length_ft(self, sm=None) -> float:
        """Return the true 3D length in feet, accounting for elevation difference.

        Parameters
        ----------
        sm : ScaleManager, optional
            If provided, use this instead of looking up from scene.
        """
        if sm is None:
            scene = self.scene()
            sm = getattr(scene, 'scale_manager', None) if scene else None
        if not sm or not sm.is_calibrated:
            return 0.0
        # 2D horizontal distance in real-world mm, then feet
        horiz_mm = self.length / sm.pixels_per_mm
        horiz_ft = horiz_mm / 304.8
        # Vertical distance (z_pos is in mm, convert to ft)
        z1 = self.node1.z_pos if self.node1 else 0.0
        z2 = self.node2.z_pos if self.node2 else 0.0
        z_diff_ft = abs(z2 - z1) / 304.8
        return math.sqrt(horiz_ft ** 2 + z_diff_ft ** 2)

    def paint(self, painter, option, widget=None):
        colour = QColor(self._display_color or self._properties["Colour"]["value"])

        # Pen width = Main/Branch display width in scene units (mm).
        # Non-cosmetic: the line scales with zoom just like real geometry.
        line_weight = self.display_width_mm() * self._display_scale

        # Determine which ends get rounded caps (not cap fittings / dead ends)
        n1_is_cap = (self.node1 and hasattr(self.node1, "fitting")
                     and self.node1.fitting and self.node1.fitting.type == "cap")
        n2_is_cap = (self.node2 and hasattr(self.node2, "fitting")
                     and self.node2.fitting and self.node2.fitting.type == "cap")
        # If neither end is a cap fitting, use RoundCap for both (fast path)
        # If both are caps, use FlatCap for both
        # If mixed, use FlatCap and manually draw round end on the non-cap side
        if not n1_is_cap and not n2_is_cap:
            cap_style = Qt.PenCapStyle.RoundCap
        else:
            cap_style = Qt.PenCapStyle.FlatCap

        base_pen = QPen(colour, line_weight)
        base_pen.setCapStyle(cap_style)

        # Velocity color-coding — only for pipes on the hydraulic calculation path
        scene = self.scene()
        if scene and hasattr(scene, "hydraulic_result") and scene.hydraulic_result is not None:
            nn = scene.hydraulic_result.node_numbers
            on_calc_path = (nn.get(self.node1) is not None
                            and nn.get(self.node2) is not None)
            if on_calc_path:
                v = scene.hydraulic_result.pipe_velocity.get(self, -1)
                if v >= 0:
                    from constants import (VELOCITY_HIGH_FPS, VELOCITY_WARN_FPS,
                                           VELOCITY_COLOR_HIGH, VELOCITY_COLOR_WARN,
                                           VELOCITY_COLOR_OK)
                    if v > VELOCITY_HIGH_FPS:
                        colour = QColor(*VELOCITY_COLOR_HIGH)
                    elif v > VELOCITY_WARN_FPS:
                        colour = QColor(*VELOCITY_COLOR_WARN)
                    else:
                        colour = QColor(*VELOCITY_COLOR_OK)
                    base_pen = QPen(colour, line_weight)
                    base_pen.setCapStyle(cap_style)

        # Collect clip regions from higher-elevation fittings
        clip_regions = self._collect_clip_regions()

        if not clip_regions:
            # Fast path — no clipping needed
            painter.setPen(base_pen)
            painter.drawLine(self.line())
        else:
            # Clip the pipe line around fitting symbols
            self._draw_clipped(painter, colour, line_weight, clip_regions, cap_style)

        # Mixed cap: draw round end on the non-cap side only
        if n1_is_cap != n2_is_cap:
            half = line_weight / 2.0
            pt = self.line().p1() if not n1_is_cap else self.line().p2()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(colour))
            painter.drawEllipse(pt, half, half)

        # highlight if selected
        if self.isSelected():
            if not clip_regions:
                highlight_pen = QPen(colour, line_weight * 1.3)
                highlight_pen.setCapStyle(cap_style)
                painter.setPen(highlight_pen)
                painter.drawLine(self.line())
            else:
                self._draw_clipped(painter, colour, line_weight * 1.3, clip_regions, cap_style)

            # also show node endpoints — zoom-independent fixed screen size
            sc = self.scene()
            views = sc.views() if sc else []
            view_scale = abs(views[0].transform().m11()) if views else 1.0
            radius = 6.0 / max(view_scale, 1e-6)  # 6 screen pixels
            brush = QBrush(QColor("white"))
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)

            for node in (self.node1, self.node2):
                if node is not None:
                    pos = node.scenePos()
                    painter.drawEllipse(QPointF(pos.x(), pos.y()), radius, radius)


        # prevent the default dotted selection rect
        option.state &= ~QStyle.StateFlag.State_Selected

    # ── Pipe clipping around fittings ─────────────────────────────────────

    def _collect_clip_regions(self) -> list:
        """Return QPainterPaths for fittings at higher elevation that overlap this pipe."""
        scene = self.scene()
        if scene is None or not hasattr(scene, "sprinkler_system"):
            return []
        my_z = max(
            getattr(self.node1, "z_pos", 0) if self.node1 else 0,
            getattr(self.node2, "z_pos", 0) if self.node2 else 0,
        )
        regions = []
        line = self.line()
        # Build a rough bounding rect for the pipe line (expanded by line weight)
        lw = self.display_width_mm() * self._display_scale
        pipe_rect = self.sceneBoundingRect().adjusted(-lw, -lw, lw, lw)

        for node in scene.sprinkler_system.nodes:
            if not hasattr(node, "fitting") or node.fitting is None:
                continue
            node_z = getattr(node, "z_pos", 0)
            if node_z <= my_z:
                continue  # only clip for fittings at higher elevation
            clip = node.fitting.clip_region_scene()
            if clip is None:
                continue
            # Quick bounding rect overlap check before expensive path ops
            if not clip.boundingRect().intersects(pipe_rect):
                continue
            regions.append(clip)
        return regions

    def _draw_clipped(self, painter, colour, line_weight, clip_regions,
                       cap_style=Qt.PenCapStyle.RoundCap):
        """Draw the pipe line with regions subtracted (clipped out)."""
        line_path = QPainterPath()
        line_path.moveTo(self.line().p1())
        line_path.lineTo(self.line().p2())

        stroker = QPainterPathStroker()
        stroker.setWidth(line_weight)
        stroker.setCapStyle(cap_style)
        stroked = stroker.createStroke(line_path)

        for clip in clip_regions:
            stroked = stroked.subtracted(clip)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(colour))
        painter.drawPath(stroked)