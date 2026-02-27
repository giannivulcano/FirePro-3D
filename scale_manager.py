"""
ScaleManager
============
Handles the mapping between scene coordinates (pixels) and real-world units.

Internal canonical unit: millimeters (mm)
Display units: imperial (feet-inches) or metric (mm / m)

Calibration workflow:
    1. User picks two points on the underlay (scene coords).
    2. User enters the real-world distance between them + unit.
    3. ScaleManager computes pixels_per_mm and stores it.
    4. All length queries go through ScaleManager for conversion.
"""

from __future__ import annotations
import math
from enum import Enum
from math import floor
from PyQt6.QtCore import QPointF


class DisplayUnit(Enum):
    IMPERIAL = "imperial"   # feet & inches
    METRIC_MM = "mm"
    METRIC_M = "m"


class ScaleManager:
    """Converts between scene pixels and real-world millimeters."""

    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def __init__(self):
        self._pixels_per_mm: float = 1.0        # default: 1 px = 1 mm
        self._display_unit: DisplayUnit = DisplayUnit.IMPERIAL
        self._calibrated: bool = False
        self._drawing_scale: float = 100.0      # denominator (e.g. 100 for 1:100)
        self._precision: int = 3                # decimal places for metric display

        # Store the calibration points for save/load
        self._cal_pt1: QPointF | None = None
        self._cal_pt2: QPointF | None = None
        self._cal_real_mm: float = 0.0

    # -----------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------
    @property
    def pixels_per_mm(self) -> float:
        return self._pixels_per_mm

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    @property
    def display_unit(self) -> DisplayUnit:
        return self._display_unit

    @display_unit.setter
    def display_unit(self, unit: DisplayUnit):
        self._display_unit = unit

    @property
    def precision(self) -> int:
        """Decimal places used for metric display."""
        return self._precision

    @precision.setter
    def precision(self, value: int):
        self._precision = max(0, min(6, int(value)))

    @property
    def drawing_scale(self) -> float:
        """Denominator of the drawing scale (e.g. 100 for 1:100)."""
        return self._drawing_scale

    @drawing_scale.setter
    def drawing_scale(self, value: float):
        if value <= 0:
            raise ValueError("Drawing scale must be positive")
        self._drawing_scale = value

    # -----------------------------------------------------------------
    # Calibration
    # -----------------------------------------------------------------
    def calibrate(self, scene_pt1: QPointF, scene_pt2: QPointF,
                  real_distance: float, unit: str = "mm"):
        """
        Compute pixels_per_mm from two scene points and a known real distance.

        Parameters
        ----------
        scene_pt1, scene_pt2 : QPointF
            Points picked in the scene.
        real_distance : float
            The real-world distance between the two points.
        unit : str
            Unit of *real_distance*: 'mm', 'm', 'in', 'ft'
        """
        if real_distance <= 0:
            raise ValueError("Real distance must be positive")

        real_mm = self._to_mm(real_distance, unit)
        scene_dist = math.hypot(
            scene_pt2.x() - scene_pt1.x(),
            scene_pt2.y() - scene_pt1.y()
        )
        if scene_dist == 0:
            raise ValueError("Scene points are identical")

        self._pixels_per_mm = scene_dist / real_mm
        self._calibrated = True

        # Store for serialisation
        self._cal_pt1 = QPointF(scene_pt1)
        self._cal_pt2 = QPointF(scene_pt2)
        self._cal_real_mm = real_mm

    def set_pixels_per_mm(self, value: float):
        """Set directly (e.g. when loading from file)."""
        if value <= 0:
            raise ValueError("pixels_per_mm must be positive")
        self._pixels_per_mm = value
        self._calibrated = True

    # -----------------------------------------------------------------
    # Conversion helpers
    # -----------------------------------------------------------------
    def scene_to_mm(self, scene_length: float) -> float:
        """Convert a scene-pixel distance to millimeters."""
        return scene_length / self._pixels_per_mm

    def mm_to_scene(self, mm: float) -> float:
        """Convert millimeters to scene-pixel distance."""
        return mm * self._pixels_per_mm

    def scene_to_display(self, scene_length: float) -> str:
        """Convert a scene distance to a formatted display string."""
        if not self._calibrated:
            return f"{scene_length:.0f} px"
        mm = self.scene_to_mm(scene_length)
        return self.format_length(mm)

    def paper_to_scene(self, paper_mm: float) -> float:
        """Convert a paper-drawing mm size to scene pixels.

        Uses both pixels_per_mm (measurement calibration) and drawing_scale
        (the denominator of the drawing's print scale, e.g. 100 for 1:100).
        Falls back to paper_mm when uncalibrated (1 px ≈ 1 mm default).
        """
        return paper_mm * self._pixels_per_mm * self._drawing_scale

    def format_length(self, mm: float) -> str:
        """Format a length in mm to the current display unit."""
        unit = self._display_unit
        p = self._precision
        if unit == DisplayUnit.IMPERIAL:
            inches = mm / 25.4
            return self._format_feet_inches(inches)
        elif unit == DisplayUnit.METRIC_M:
            m = mm / 1000.0
            return f"{m:.{p}f} m"
        else:  # METRIC_MM
            return f"{mm:.{p}f} mm"

    # -----------------------------------------------------------------
    # Unit conversion to canonical mm
    # -----------------------------------------------------------------
    @staticmethod
    def _to_mm(value: float, unit: str) -> float:
        """Convert *value* in the given unit to millimeters."""
        unit = unit.lower().strip()
        conversions = {
            "mm": 1.0,
            "m":  1000.0,
            "in": 25.4,
            "ft": 304.8,
        }
        factor = conversions.get(unit)
        if factor is None:
            raise ValueError(f"Unknown unit '{unit}'. Use mm, m, in, or ft.")
        return value * factor

    @staticmethod
    def mm_to_unit(mm: float, unit: str) -> float:
        """Convert mm to the given unit."""
        unit = unit.lower().strip()
        conversions = {
            "mm": 1.0,
            "m":  1000.0,
            "in": 25.4,
            "ft": 304.8,
        }
        factor = conversions.get(unit)
        if factor is None:
            raise ValueError(f"Unknown unit '{unit}'.")
        return mm / factor

    # -----------------------------------------------------------------
    # Imperial formatting  (moved from Pipe for reuse)
    # -----------------------------------------------------------------
    @staticmethod
    def _format_feet_inches(total_inches: float) -> str:
        """
        Format total inches as  feet' inches-fraction"
        Denominators: 2, 4, 8, 16.
        """
        feet = int(total_inches // 12)
        inches_decimal = total_inches % 12
        inches_whole = int(floor(inches_decimal))
        frac_decimal = inches_decimal - inches_whole

        denominators = [2, 4, 8, 16]
        best_num, best_den = 0, 1
        min_error = 1.0

        for d in denominators:
            n = round(frac_decimal * d)
            error = abs(frac_decimal - n / d)
            if error < min_error:
                min_error = error
                best_num, best_den = n, d

        if best_num == best_den:
            inches_whole += 1
            best_num, best_den = 0, 1

        if inches_whole == 12:
            feet += 1
            inches_whole = 0

        parts = []
        if feet > 0:
            parts.append(f"{feet}'")

        inch_part = ""
        if inches_whole > 0:
            inch_part += str(inches_whole)
        if best_num > 0:
            if inch_part:
                inch_part += f" {best_num}/{best_den}"
            else:
                inch_part = f"{best_num}/{best_den}"
        if inch_part:
            parts.append(f'{inch_part}"')

        if not parts:
            parts.append('0"')

        return " ".join(parts)

    # -----------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------
    def to_dict(self) -> dict:
        d = {
            "pixels_per_mm":  self._pixels_per_mm,
            "calibrated":     self._calibrated,
            "display_unit":   self._display_unit.value,
            "drawing_scale":  self._drawing_scale,
            "precision":      self._precision,
        }
        if self._cal_pt1 is not None:
            d["cal_pt1"] = [self._cal_pt1.x(), self._cal_pt1.y()]
            d["cal_pt2"] = [self._cal_pt2.x(), self._cal_pt2.y()]
            d["cal_real_mm"] = self._cal_real_mm
        return d

    @staticmethod
    def from_dict(d: dict) -> ScaleManager:
        sm = ScaleManager()
        sm._pixels_per_mm = d.get("pixels_per_mm", 1.0)
        sm._calibrated = d.get("calibrated", False)
        sm._display_unit = DisplayUnit(d.get("display_unit", "imperial"))
        sm._drawing_scale = d.get("drawing_scale", 100.0)
        sm._precision = d.get("precision", 3)
        if "cal_pt1" in d:
            sm._cal_pt1 = QPointF(d["cal_pt1"][0], d["cal_pt1"][1])
            sm._cal_pt2 = QPointF(d["cal_pt2"][0], d["cal_pt2"][1])
            sm._cal_real_mm = d.get("cal_real_mm", 0.0)
        return sm