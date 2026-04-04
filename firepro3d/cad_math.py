from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
import math

class CAD_Math:

    @staticmethod
    def get_vector(p1: QPointF, p2: QPointF) -> QPointF:
        """
        Returns the vector from p1 to p2.
        """
        return QPointF(p2 - p1)
    
    @staticmethod
    def get_vector_angle(p1: QPointF, p2: QPointF) -> QPointF:
        u = CAD_Math.get_unit_vector(p1,p2)
        angle = math.degrees(math.atan2(u.y(), u.x()))
        return (angle + 90) % 360   # 0° = up, 90° = right, etc.

    @staticmethod
    def get_unit_vector(p1: QPointF, p2: QPointF) -> QPointF:
        """
        Returns the unit vector from p1 to p2.
        """
        vec = CAD_Math.get_vector(p1, p2)
        length = math.hypot(vec.x(), vec.y())
        if length == 0:
            return QPointF(0.0, 0.0)
        return QPointF(vec.x() / length, vec.y() / length)
    
    @staticmethod
    def get_vector_length(p1: QPointF, p2: QPointF):
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        return math.hypot(dx, dy)

    @staticmethod
    def get_vector_length_3d(p1: QPointF, p2: QPointF, z1: float, z2: float):
        """Return the 3D distance between two points with separate z values."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dz = z2 - z1
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    
    @staticmethod
    def get_angle_between_vectors(v1: QPointF, v2: QPointF, signed: bool = True) -> float:
        """
        Returns the angle between v1 and v2 in degrees.
        
        Args:
            v1, v2: QPointF vectors
            signed: If True, returns signed angle (-180, 180],
                    If False, returns smallest positive angle [0, 180].
        """
        mag1 = math.hypot(v1.x(), v1.y())
        mag2 = math.hypot(v2.x(), v2.y())
        if mag1 == 0 or mag2 == 0:
            return 0.0

        # Normalize
        x1, y1 = v1.x() / mag1, v1.y() / mag1
        x2, y2 = v2.x() / mag2, v2.y() / mag2

        # Dot product (clamp for safety)
        dot = max(-1.0, min(1.0, x1 * x2 + y1 * y2))
        angle = math.degrees(math.acos(dot))

        if signed:
            # Cross product (determinant) to get sign
            cross = x1 * y2 - y1 * x2
            if cross < 0:
                angle = -angle

        return angle
    
    @staticmethod
    def get_outward_vectors(node, pipes):
        """Return unit vectors pointing outward from *node* for each pipe."""
        pos = node.scenePos()
        vecs = []
        for p in pipes:
            other = p.node2.scenePos() if p.node1 is node else p.node1.scenePos()
            vecs.append(CAD_Math.get_unit_vector(pos, other))
        return vecs

    # ---------------------------------------------------------|
    # ----------- POINT TRANSFORMS (Sprint) -------------------|
    # ---------------------------------------------------------|

    @staticmethod
    def rotate_point(pt: QPointF, pivot: QPointF, angle_deg: float) -> QPointF:
        """Rotate *pt* around *pivot* by *angle_deg* (CCW positive, screen Y-down)."""
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        ox, oy = pt.x() - pivot.x(), pt.y() - pivot.y()
        return QPointF(pivot.x() + ox * cos_a - oy * sin_a,
                       pivot.y() + ox * sin_a + oy * cos_a)

    @staticmethod
    def mirror_point(pt: QPointF, axis_p1: QPointF, axis_p2: QPointF) -> QPointF:
        """Reflect *pt* across the line defined by *axis_p1* → *axis_p2*."""
        dx, dy = axis_p2.x() - axis_p1.x(), axis_p2.y() - axis_p1.y()
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return QPointF(pt)
        t = ((pt.x() - axis_p1.x()) * dx + (pt.y() - axis_p1.y()) * dy) / len_sq
        foot_x = axis_p1.x() + t * dx
        foot_y = axis_p1.y() + t * dy
        return QPointF(2 * foot_x - pt.x(), 2 * foot_y - pt.y())

    @staticmethod
    def scale_point(pt: QPointF, base: QPointF, factor: float) -> QPointF:
        """Scale *pt* relative to *base* by *factor*."""
        return QPointF(base.x() + (pt.x() - base.x()) * factor,
                       base.y() + (pt.y() - base.y()) * factor)

    @staticmethod
    def point_on_line_nearest(pt: QPointF, lp1: QPointF, lp2: QPointF) -> QPointF:
        """Project *pt* onto the infinite line through *lp1* and *lp2*."""
        dx, dy = lp2.x() - lp1.x(), lp2.y() - lp1.y()
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return QPointF(lp1)
        t = ((pt.x() - lp1.x()) * dx + (pt.y() - lp1.y()) * dy) / len_sq
        return QPointF(lp1.x() + t * dx, lp1.y() + t * dy)

    # ---------------------------------------------------------|
    # ----------------- TRANSFORMS ----------------------------|
    # ---------------------------------------------------------|
    @staticmethod 
    def rotate_unit_vector(v_from: QPointF, v_to: QPointF) -> QTransform:
        """
        Returns a QTransform that rotates v_from to align with v_to.
        Both inputs must be QPointF.
        """
        if not isinstance(v_from, QPointF) or not isinstance(v_to, QPointF):
            raise TypeError("v_from and v_to must be QPointF")

        # Compute angle in radians
        angle_from = math.atan2(v_from.y(), v_from.x())
        angle_to   = math.atan2(v_to.y(), v_to.x())

        # Convert to degrees
        angle_deg = math.degrees(angle_to - angle_from)

        # Create rotation transform
        transform = QTransform()
        transform.rotate(angle_deg)

        return transform
    
    @staticmethod 
    def make_qtransform_from_qpoints(M1, M2):
        """
        M1 and M2: lists of two QPointF columns each
        Returns: QTransform that maps M2 -> M1
        """
        a1, a2 = M2
        b1, b2 = M1

        ax1, ay1 = a1.x(), a1.y()
        ax2, ay2 = a2.x(), a2.y()
        bx1, by1 = b1.x(), b1.y()
        bx2, by2 = b2.x(), b2.y()

        det = ax1*ay2 - ay1*ax2
        if abs(det) < 1e-12:
            raise ValueError("M2 columns are collinear; cannot invert")

        # inverse of M2
        inv00 = ay2 / det
        inv01 = -ax2 / det
        inv10 = -ay1 / det
        inv11 = ax1 / det

        # linear map Q = M1 @ inv(M2)
        m11 = bx1*inv00 + bx2*inv10
        m12 = bx1*inv01 + bx2*inv11
        m21 = by1*inv00 + by2*inv10
        m22 = by1*inv01 + by2*inv11

        transform = QTransform(m11, m12, 0.0,
                            m21, m22, 0.0,
                            0.0, 0.0, 1.0)

        return transform
