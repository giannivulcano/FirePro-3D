import math
from CAD_Math import CAD_Math
from PyQt6.QtCore import QPointF
from PyQt6.QtSvgWidgets import QGraphicsSvgItem

class Fitting():
    SIZE = 1
    TARGET_PAPER_MM = 6.0   # desired fitting symbol size in paper mm
    SYMBOLS = {
        "no fitting": {
            "path": r"graphics/fitting_symbols/no_fitting.svg"
        },
        "cap": {
            "path": r"graphics/fitting_symbols/cap.svg",
            "through": QPointF(0, 1)  # entry/exit
        },
        "45elbow": {
            "path": r"graphics/fitting_symbols/45_elbow.svg",
            "through": (QPointF(1,0), QPointF(-(math.sqrt(2) / 2), -(math.sqrt(2) / 2)))
        },
        "90elbow": {
            "path": r"graphics/fitting_symbols/90_elbow.svg",
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "tee": {
            "path": r"graphics/fitting_symbols/tee.svg",
            "through": (QPointF(1, 0), QPointF(0, -1))
        },
        "wye": {
            "path": r"graphics/fitting_symbols/wye.svg",
            "through": (QPointF(1, 0), QPointF(-(math.sqrt(2) / 2), -(math.sqrt(2) / 2)))
        },
        "cross": {
            "path": r"graphics/fitting_symbols/double_tee.svg",
            "through": QPointF(0, -1)
        }
    }

    def __init__(self, node):
        self.node = node       # back-reference to owning Node
        self.symbol = None
        self.symbol_scale = 0.5
        self.type = "no fitting"

    def update(self,visibility=True):
        pipes = self.node.pipes
        self.type = self.determine_type(pipes)
        print(self.node)
        print(f"fitting type: {self.type}")
        self.update_symbol()
        self.align_fitting()
        if self.node.has_sprinkler():
            visibility = False
        self.symbol.setVisible(visibility)

    def determine_type(self, pipes) -> str:
        """Decide fitting type based on connected pipes."""
        count = len(pipes)
        if count == 0:
            return "no fitting"
        elif count == 1:
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
            # same tee vs wye logic
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
            return "cross"
        else:
            return "no fitting"


    def update_symbol(self):

        # Kill old symbol by just dropping the reference (Qt handles deletion via parent)
        if self.symbol is not None:
            self.symbol.setParentItem(None)
            self.symbol = None

        # Build new symbol as child of node
        path = self.SYMBOLS[self.type]["path"]
        self.symbol = QGraphicsSvgItem(path, self.node)

        # Rotation origin at the center of its bounding box
        self.symbol.setTransformOriginPoint(self.symbol.boundingRect().center())



    def align_fitting(self):
        pipes = self.node.pipes
        node = self.node
        pipe_vectors = []
        for pipe in pipes:
            p1 = node.scenePos()
            if pipe.node1 is node:
                p2 = pipe.node2.scenePos()
            elif pipe.node2 is node:
                p2 = pipe.node1.scenePos()
            pipe_vectors.append(CAD_Math.get_unit_vector(p1,p2))
            transform = None

        if self.type in ("no fitting"):
            transform = CAD_Math.rotate_unit_vector(QPointF(1,0), QPointF(1,0))

        if self.type in ("cap", "cross"):
            V1 = pipe_vectors[0]
            V2 = self.SYMBOLS[self.type].get("through")
            transform = CAD_Math.rotate_unit_vector(V2, V1) #aligns V2 with V1

        elif self.type in ("90elbow", "45elbow"):
            M1 = pipe_vectors
            M2 = self.SYMBOLS[self.type].get("through")
            transform = CAD_Math.make_qtransform_from_qpoints(M2, M1)

        elif self.type in ("tee", "wye"):

            M1 = pipe_vectors
            #find the pipe vectors angle that is 135 or 90 and assign these to M1
            if (math.isclose(CAD_Math.get_angle_between_vectors(M1[0],M1[1],signed=False), 180, rel_tol=1e-2) or 
                math.isclose(CAD_Math.get_angle_between_vectors(M1[0],M1[1],signed=False), 0, rel_tol=1e-2)):
                if self.type == "tee":
                    M2 = [M1[0],M1[2]]
                elif self.type == "wye":
                    print(f"angle b/w M1[0] and M1[2]: {CAD_Math.get_angle_between_vectors(M1[0],M1[2],signed=False)}")
                    print(f"angle b/w M1[1] and M1[2]: {CAD_Math.get_angle_between_vectors(M1[1],M1[2],signed=False)}")
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
                    print(f"angle b/w M1[0] and M1[1]: {CAD_Math.get_angle_between_vectors(M1[0],M1[1],signed=False)}")
                    print(f"angle b/w M1[2] and M1[1]: {CAD_Math.get_angle_between_vectors(M1[2],M1[1],signed=False)}")
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
                    print(f"angle b/w M1[1] and M1[0]: {CAD_Math.get_angle_between_vectors(M1[1],M1[0],signed=False)}")
                    print(f"angle b/w M1[2] and M1[0]: {CAD_Math.get_angle_between_vectors(M1[2],M1[0],signed=False)}")
                    angle = CAD_Math.get_angle_between_vectors(M1[1],M1[0],signed=False)
                    if math.isclose(angle, 135,rel_tol=1e-2):
                        M2 = [M1[1],M1[0]]
                    else:
                        M2 = [M1[2],M1[0]]
            M3 = self.SYMBOLS[self.type].get("through")
            try:
                transform = CAD_Math.make_qtransform_from_qpoints(M3, M2)
            except Exception as e:
                print(f"Something broke: {e}")
            
        bounds = self.symbol.boundingRect()
        center = bounds.center()
        self.symbol.setTransformOriginPoint(center)
        transform.scale(self.symbol_scale, self.symbol_scale)
        self.symbol.setTransform(transform)
        # After transform, move the item so its **center aligns with node position**
        # Use the transformed bounding rect
        transformed_bounds = self.symbol.mapRectToParent(bounds)
        self.symbol.setPos(-transformed_bounds.center())

    def rescale(self, sm) -> None:
        """Re-apply symbol_scale using ScaleManager, then redraw (called after calibration)."""
        if self.symbol is None:
            return
        svg_natural = max(self.symbol.boundingRect().width(),
                          self.symbol.boundingRect().height())
        if svg_natural > 0 and sm and sm.is_calibrated:
            self.symbol_scale = sm.paper_to_scene(self.TARGET_PAPER_MM) / svg_natural
        # else: keep existing symbol_scale
        self.update()