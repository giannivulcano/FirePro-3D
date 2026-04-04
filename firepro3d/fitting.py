import math
import os
from .assets import asset_path
from .cad_math import CAD_Math
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QTransform, QPainterPath
from PyQt6.QtSvgWidgets import QGraphicsSvgItem


class _TintedSvg(QGraphicsSvgItem):
    """QGraphicsSvgItem subclass that stores ``_svg_source_path`` for
    direct SVG recolouring via ``_set_svg_tint``."""
    pass


class Fitting():
    SIZE = 1
    TARGET_PAPER_MM = 6.0   # desired fitting symbol size in paper mm
    TARGET_SCREEN_PX = 20.0 # zoom-independent screen-pixel size

    # Nominal OD table: use Pipe.NOMINAL_OD_IN (single source of truth)
    SYMBOLS = {
        "no fitting": {
            "path": asset_path("fitting_symbols", "no_fitting.svg")
        },
        "cap": {
            "path": asset_path("fitting_symbols", "cap.svg"),
            "through": QPointF(0, 1)  # entry/exit
        },
        "45elbow": {
            "path": asset_path("fitting_symbols", "45_elbow.svg"),
            "through": (QPointF(1,0), QPointF(-(math.sqrt(2) / 2), -(math.sqrt(2) / 2)))
        },
        "90elbow": {
            "path": asset_path("fitting_symbols", "90_elbow.svg"),
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "tee": {
            "path": asset_path("fitting_symbols", "tee.svg"),
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "wye": {
            "path": asset_path("fitting_symbols", "wye.svg"),
            "through": (QPointF(1, 0), QPointF(-(math.sqrt(2) / 2), -(math.sqrt(2) / 2)))
        },
        "cross": {
            "path": asset_path("fitting_symbols", "double_tee.svg"),
            "through": QPointF(0, -1)
        },
        "tee_up": {
            "path": asset_path("fitting_symbols", "tee_up.svg"),
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "tee_down": {
            "path": asset_path("fitting_symbols", "tee_down.svg"),
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "elbow_up": {
            "path": asset_path("fitting_symbols", "elbow_up.svg"),
            "through": QPointF(1, 0)
        },
        "elbow_down": {
            "path": asset_path("fitting_symbols", "elbow_down.svg"),
            "through": QPointF(-1, 0)   # opening faces toward the horizontal pipe
        },
    }

    def __init__(self, node):
        self.node = node       # back-reference to owning Node
        self.symbol = None
        self.symbol_scale = 0.5
        self.type = "no fitting"
        self._display_overrides: dict = {}    # per-instance display overrides
        self._display_scale: float = 1.0      # display scale multiplier
        self._display_color: str | None = None # display color override
        self._display_fill_color: str | None = None  # display fill override
        self._display_opacity: float = 100    # display opacity (0-100)
        self._display_visible: bool = True    # display visibility

    def update(self,visibility=True):
        pipes = self.node.pipes
        self.type = self.determine_type(pipes)
        self.update_symbol()
        self.align_fitting()
        if self.node.has_sprinkler():
            visibility = False
        # For nodes that overlap in XY (vertical drop/riser), only show the
        # fitting on the node with the highest z_pos — hide the lower one.
        if visibility:
            node = self.node
            for p in pipes:
                if self._is_vertical(p, node):
                    other = p.node2 if p.node1 is node else p.node1
                    if other is not None:
                        np = node.scenePos()
                        op = other.scenePos()
                        if (np.x() - op.x()) ** 2 + (np.y() - op.y()) ** 2 < 100:
                            my_z = getattr(node, "z_pos", 0)
                            ot_z = getattr(other, "z_pos", 0)
                            if my_z < ot_z:
                                visibility = False
                            elif my_z == ot_z:
                                # Tie-break: hide the one with lower ceiling_offset
                                my_off = getattr(node, "ceiling_offset", 0)
                                ot_off = getattr(other, "ceiling_offset", 0)
                                if my_off < ot_off:
                                    visibility = False
                                elif my_off == ot_off:
                                    # Final tie-break: hide by id
                                    if id(node) < id(other):
                                        visibility = False
                            break
        self.symbol.setVisible(visibility)

    # ── Vertical pipe helpers ────────────────────────────────────────────

    @staticmethod
    def _is_vertical(pipe, node) -> bool:
        """True if *pipe* is vertical (same XY, different z_pos)."""
        if pipe.node1 is None or pipe.node2 is None:
            return False
        p1 = pipe.node1.scenePos()
        p2 = pipe.node2.scenePos()
        dx = p1.x() - p2.x()
        dy = p1.y() - p2.y()
        dz = abs(getattr(pipe.node1, "z_pos", 0) - getattr(pipe.node2, "z_pos", 0))
        return (dx * dx + dy * dy) < 100 and dz > 0.01  # 10 px tol, 0.01 ft z tol

    @staticmethod
    def _vertical_direction(pipe, node) -> str:
        """Return ``'up'`` or ``'down'`` relative to *node*."""
        other = pipe.node2 if pipe.node1 is node else pipe.node1
        return "up" if getattr(other, "z_pos", 0) > getattr(node, "z_pos", 0) else "down"

    # ── Type determination ─────────────────────────────────────────────

    def determine_type(self, pipes) -> str:
        """Decide fitting type based on connected pipes."""
        count = len(pipes)
        if count == 0:
            return "no fitting"

        node = self.node
        vertical   = [p for p in pipes if self._is_vertical(p, node)]
        horizontal = [p for p in pipes if not self._is_vertical(p, node)]

        # ── Vertical pipe present ──────────────────────────────────────
        if vertical:
            direction = self._vertical_direction(vertical[0], node)
            if len(horizontal) <= 1:
                return f"elbow_{direction}"
            else:
                return f"tee_{direction}"

        # ── Pure horizontal logic (unchanged) ──────────────────────────
        if count == 1:
            return "cap"
        elif count == 2:
            v1 = CAD_Math.get_unit_vector(pipes[0].node1.scenePos(),pipes[0].node2.scenePos())
            v2 = CAD_Math.get_unit_vector(pipes[1].node1.scenePos(),pipes[1].node2.scenePos())
            angle = abs(CAD_Math.get_angle_between_vectors(v1, v2, signed=False))

            if math.isclose(angle, 180, abs_tol=10):
                return "no fitting"
            elif math.isclose(angle, 90, abs_tol=10):
                return "90elbow"
            elif math.isclose(angle, 45, abs_tol=5) or math.isclose(angle, 135, abs_tol=5):
                return "45elbow"
            else:
                return "no fitting"
        elif count == 3:
            V = [CAD_Math.get_unit_vector(p.node1.scenePos(),p.node2.scenePos()) for p in pipes]
            angles = [
                round(CAD_Math.get_angle_between_vectors(V[i], V[j], signed=False))
                for i in range(3) for j in range(i+1, 3)
            ]
            if 90 in angles:
                return "tee"
            else:
                return "wye"
        elif count == 4:
            # Cross is only valid when all 4 pipes form two perpendicular
            # collinear pairs.  Vectors must point OUTWARD from the junction.
            pipe_vectors = CAD_Math.get_outward_vectors(node, pipes)
            if len(pipe_vectors) == 4:
                pairs_ok = False
                for i in range(4):
                    for j in range(i + 1, 4):
                        a = abs(CAD_Math.get_angle_between_vectors(
                            pipe_vectors[i], pipe_vectors[j], signed=False))
                        if math.isclose(a, 180, abs_tol=10):
                            others = [k for k in range(4) if k != i and k != j]
                            a2 = abs(CAD_Math.get_angle_between_vectors(
                                pipe_vectors[others[0]], pipe_vectors[others[1]],
                                signed=False))
                            if math.isclose(a2, 180, abs_tol=10):
                                pairs_ok = True
                                break
                    if pairs_ok:
                        break
                return "cross" if pairs_ok else "no fitting"
            return "no fitting"
        else:
            return "no fitting"


    def _max_connected_width_mm(self) -> float:
        """Return the largest display width (mm) among pipes on this node."""
        best = 75.0  # fallback: branch width
        for pipe in self.node.pipes:
            w = pipe.display_width_mm()
            if w > best:
                best = w
        return best

    def update_symbol(self):

        # Kill old symbol by just dropping the reference (Qt handles deletion via parent)
        if self.symbol is not None:
            self.symbol.setParentItem(None)
            self.symbol = None

        # Build new symbol as child of node
        path = self.SYMBOLS[self.type]["path"]
        # Resolve relative to this module's directory (not CWD)
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(__file__), path)
        self.symbol = _TintedSvg(path, self.node)
        self.symbol._svg_source_path = os.path.abspath(path)
        # No ItemIgnoresTransformations — symbol scales with zoom (real-world size)

        # Rotation origin at the center of its bounding box
        self.symbol.setTransformOriginPoint(self.symbol.boundingRect().center())

        # Re-apply display overrides after symbol recreation
        self._reapply_display_effects()



    def align_fitting(self):
        pipes = self.node.pipes
        node = self.node

        if self.symbol is None:
            return

        # Build 2D direction vectors only for horizontal pipes
        # (vertical pipes have zero-length 2D vectors and would break angle math)
        horiz_pipes = [p for p in pipes if not self._is_vertical(p, node)]
        pipe_vectors = []
        for pipe in horiz_pipes:
            p1 = node.scenePos()
            if pipe.node1 is node:
                p2 = pipe.node2.scenePos()
            elif pipe.node2 is node:
                p2 = pipe.node1.scenePos()
            pipe_vectors.append(CAD_Math.get_unit_vector(p1, p2))
        transform = None

        if self.type in ("no fitting"):
            transform = CAD_Math.rotate_unit_vector(QPointF(1, 0), QPointF(1, 0))

        elif self.type in ("elbow_up", "elbow_down"):
            # Align the fitting with the horizontal pipe direction (if any)
            V2 = self.SYMBOLS[self.type].get("through")
            if pipe_vectors:
                V1 = pipe_vectors[0]
            else:
                V1 = QPointF(1, 0)
            transform = CAD_Math.rotate_unit_vector(V2, V1)

        elif self.type in ("tee_up", "tee_down"):
            # Use the horizontal pipe vectors for alignment
            M2_spec = self.SYMBOLS[self.type].get("through")
            if len(pipe_vectors) >= 2:
                M1 = pipe_vectors[:2]
                try:
                    transform = CAD_Math.make_qtransform_from_qpoints(M2_spec, M1)
                except (ValueError, TypeError, ZeroDivisionError):
                    transform = QTransform()
            elif pipe_vectors:
                V2 = M2_spec[0] if isinstance(M2_spec, tuple) else M2_spec
                transform = CAD_Math.rotate_unit_vector(V2, pipe_vectors[0])
            else:
                transform = QTransform()

        elif self.type == "cap":
            V1 = pipe_vectors[0] if pipe_vectors else QPointF(1, 0)
            V2 = self.SYMBOLS[self.type].get("through")
            transform = CAD_Math.rotate_unit_vector(V2, V1)

        elif self.type == "cross":
            # Align cross using one of the collinear pairs
            V2 = self.SYMBOLS[self.type].get("through")
            if len(pipe_vectors) >= 2:
                # Find a collinear pair to use as the through-run
                M1 = pipe_vectors[:2]  # default
                for i in range(len(pipe_vectors)):
                    for j in range(i + 1, len(pipe_vectors)):
                        a = abs(CAD_Math.get_angle_between_vectors(
                            pipe_vectors[i], pipe_vectors[j], signed=False))
                        if math.isclose(a, 180, abs_tol=10):
                            M1 = [pipe_vectors[i], pipe_vectors[j]]
                            break
                try:
                    transform = CAD_Math.make_qtransform_from_qpoints(V2, M1)
                except (ValueError, TypeError, ZeroDivisionError):
                    transform = CAD_Math.rotate_unit_vector(
                        V2[0] if isinstance(V2, (list, tuple)) else V2,
                        pipe_vectors[0])
            else:
                V1 = pipe_vectors[0] if pipe_vectors else QPointF(1, 0)
                transform = CAD_Math.rotate_unit_vector(
                    V2[0] if isinstance(V2, (list, tuple)) else V2, V1)

        elif self.type in ("90elbow", "45elbow"):
            M1 = pipe_vectors
            M2 = self.SYMBOLS[self.type].get("through")
            transform = CAD_Math.make_qtransform_from_qpoints(M2, M1)

        elif self.type in ("tee", "wye"):

            M1 = pipe_vectors
            M2 = M1[:2]  # safe default — use first two vectors
            #find the pipe vectors angle that is 135 or 90 and assign these to M1
            if (math.isclose(CAD_Math.get_angle_between_vectors(M1[0],M1[1],signed=False), 180, rel_tol=1e-2) or 
                math.isclose(CAD_Math.get_angle_between_vectors(M1[0],M1[1],signed=False), 0, rel_tol=1e-2)):
                if self.type == "tee":
                    M2 = [M1[0],M1[2]]
                elif self.type == "wye":
                    angle = CAD_Math.get_angle_between_vectors(M1[0],M1[2],signed=False)
                    if math.isclose(angle,135, rel_tol=1e-2):
                        M2 = [M1[0],M1[2]]
                    else:
                        M2 = [M1[1],M1[2]]
                
            elif (math.isclose(CAD_Math.get_angle_between_vectors(M1[0],M1[2],signed=False), 180, rel_tol=1e-2) or
                  math.isclose(CAD_Math.get_angle_between_vectors(M1[0],M1[2],signed=False), 0, rel_tol=1e-2)):
                if self.type == "tee":
                    M2 = [M1[0],M1[1]]
                elif self.type == "wye":
                    angle = CAD_Math.get_angle_between_vectors(M1[0],M1[1],signed=False)
                    if math.isclose(angle,135, rel_tol=1e-2):
                        M2 = [M1[0],M1[1]]
                    else:
                        M2 = [M1[2],M1[1]]

            elif (math.isclose(CAD_Math.get_angle_between_vectors(M1[1],M1[2],signed=False),180,rel_tol=1e-2) or
                  math.isclose(CAD_Math.get_angle_between_vectors(M1[1],M1[2],signed=False),0,rel_tol=1e-2)):
                if self.type == "tee":
                    M2 = [M1[1],M1[0]]
                elif self.type == "wye":
                    angle = CAD_Math.get_angle_between_vectors(M1[1],M1[0],signed=False)
                    if math.isclose(angle, 135,rel_tol=1e-2):
                        M2 = [M1[1],M1[0]]
                    else:
                        M2 = [M1[2],M1[0]]
            M3 = self.SYMBOLS[self.type].get("through")
            try:
                transform = CAD_Math.make_qtransform_from_qpoints(M3, M2)
            except (ValueError, TypeError, ZeroDivisionError, UnboundLocalError):
                pass  # fallback to identity transform below
            
        # Fallback: if no condition produced a transform, use identity
        if transform is None:
            transform = QTransform()

        bounds = self.symbol.boundingRect()
        center = bounds.center()
        self.symbol.setTransformOriginPoint(center)

        # Scale fitting to 4× the largest connected pipe display width
        # Branch (75mm) → 300mm, Main (150mm) → 600mm
        svg_natural = max(bounds.width(), bounds.height())
        if svg_natural > 0:
            target_mm = self._max_connected_width_mm() * 4 * self._display_scale
            self.symbol_scale = target_mm / svg_natural
        else:
            self.symbol_scale = 1.0

        transform.scale(self.symbol_scale, self.symbol_scale)

        # Adjust the transform so the SVG centre maps to local (0, 0),
        # anchoring the fitting on the parent node.
        cx, cy = center.x(), center.y()
        mc_x = transform.m11() * cx + transform.m21() * cy + transform.dx()
        mc_y = transform.m12() * cx + transform.m22() * cy + transform.dy()
        final = QTransform(transform.m11(), transform.m12(),
                           transform.m21(), transform.m22(),
                           transform.dx() - mc_x, transform.dy() - mc_y)
        self.symbol.setTransform(final)
        self.symbol.setPos(0, 0)

    def _reapply_display_effects(self):
        """Re-apply colour effect and opacity after symbol recreation."""
        if self.symbol is None:
            return
        from .display_manager import _set_svg_tint
        _set_svg_tint(self.symbol, self._display_color,
                      self._display_fill_color)
        op = self._display_opacity
        self.symbol.setOpacity(op / 100.0 if op > 1 else op)
        if not self._display_visible:
            self.symbol.setVisible(False)

    def clip_region_scene(self) -> "QPainterPath | None":
        """Return the fitting's bounding circle in scene coords for pipe clipping.

        Returns None if the fitting shouldn't clip (invisible, no fitting, etc.).
        """
        if self.symbol is None or not self.symbol.isVisible():
            return None
        if self.type == "no fitting":
            return None
        # Use the symbol's scene bounding rect to derive a clipping circle
        rect = self.symbol.sceneBoundingRect()
        if rect.isNull() or rect.isEmpty():
            return None
        center = rect.center()
        radius = max(rect.width(), rect.height()) / 2.0
        path = QPainterPath()
        path.addEllipse(center, radius, radius)
        return path

    def rescale(self, sm=None) -> None:
        """Re-draw fitting at real-world scale (sized to largest connected pipe)."""
        if self.symbol is None:
            return
        self.update()