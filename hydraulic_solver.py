"""
HydraulicSolver
===============
Hazen-Williams sequential pipe-by-pipe hydraulic analysis for tree-topology
fire-suppression networks (NFPA 13).

Algorithm (valid for tree / radial networks only — no loops)
-------------------------------------------------------------
Phase 1  POST-ORDER  (leaves → supply)
  Each design sprinkler is assigned its minimum flow:  Q = K × √P_min
  Each pipe's flow = sum of all downstream sprinkler flows.

Phase 2  POST-ORDER  (leaves → supply)
  Working backward from each leaf, compute the pressure required at every
  junction so that every downstream sprinkler receives at least P_min.
  At multi-branch junctions the most-demanding branch governs.

Phase 3  Supply check
  Compare required pressure at the supply node against the pressure
  available from the supply curve at the computed total demand.

Phase 4  PRE-ORDER  (supply → leaves)
  Propagate the actual (available) supply pressure forward to get real
  working pressures at every node.

Key formulas  (NFPA 13 §22.4.2)
  Friction loss  hf [psi]  = 4.52 × Q^1.852 / (C^1.852 × d^4.87) × L
  Elevation      h_e [psi] = 0.433 × Δz     (Δz in ft, positive = upward flow)
  Sprinkler flow Q  [gpm]  = K × √P          (K-factor and P in psi)
  Velocity       v  [fps]  = Q × 0.4085 / d² (Q in gpm, d in inches)
"""

import math
from collections import deque
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HydraulicResult:
    """All outputs from a hydraulic solver run."""
    node_pressures:     dict   # Node  → float (psi)
    pipe_flows:         dict   # Pipe  → float (gpm)
    pipe_velocity:      dict   # Pipe  → float (fps)
    pipe_friction_loss: dict   # Pipe  → float (psi, total for the pipe)
    total_demand:       float  # gpm at supply connection
    required_pressure:  float  # psi required at supply node
    supply_pressure:    float  # psi available from supply curve at total_demand
    passed:             bool
    messages:           list   # list[str]  warnings / errors / summary


# ─────────────────────────────────────────────────────────────────────────────
# Solver
# ─────────────────────────────────────────────────────────────────────────────

class HydraulicSolver:
    """
    Runs a Hazen-Williams pipe-network analysis.

    Parameters
    ----------
    sprinkler_system : SprinklerSystem
        The scene's network model.  Must have ``supply_node`` set.
    scale_manager : ScaleManager
        Used to convert scene-pixel lengths to real-world feet.
    """

    # NFPA 13 velocity warning threshold (fps)
    VELOCITY_LIMIT_FPS = 20.0

    def __init__(self, sprinkler_system, scale_manager):
        self.system = sprinkler_system
        self.sm = scale_manager

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point

    def solve(self, design_sprinklers=None) -> HydraulicResult:
        """
        Run the full hydraulic analysis.

        Parameters
        ----------
        design_sprinklers : list[Sprinkler] or None
            Sprinklers in the design area.  None → all sprinklers.

        Returns
        -------
        HydraulicResult
        """
        messages: list[str] = []
        supply_ws = self.system.supply_node       # WaterSupply item (may be None)

        # ── Guards ────────────────────────────────────────────────────────────
        if supply_ws is None:
            return self._fail("No water supply node placed on the drawing.")

        if design_sprinklers is None:
            design_sprinklers = list(self.system.sprinklers)

        if not design_sprinklers:
            return self._fail("No sprinklers in the design area.")

        if not self.system.nodes:
            return self._fail("No pipe network nodes found.")

        # ── Find the network node closest to the WaterSupply item ─────────────
        supply_node = self._find_supply_network_node(supply_ws, messages)
        if supply_node is None:
            return self._fail("Water supply node is not connected to the pipe network.",
                              messages)

        # ── Build BFS tree from supply ─────────────────────────────────────────
        adjacency                             = self._build_adjacency()
        parent_node, parent_pipe, children, bfs_order = self._bfs_tree(
            supply_node, adjacency
        )

        # Filter design sprinklers to those reachable from supply
        reachable = set(bfs_order)
        active_sprinklers = [s for s in design_sprinklers if s.node in reachable]
        if not active_sprinklers:
            return self._fail(
                "None of the design sprinklers are connected to the supply node.",
                messages
            )

        # ─────────────────────────────────────────────────────────────────────
        # Phase 1: Assign minimum flows at demand nodes
        # ─────────────────────────────────────────────────────────────────────
        node_min_demand: dict = {}      # flow demanded AT this node (gpm)
        for spr in active_sprinklers:
            k     = self._safe_float(spr._properties["K-Factor"]["value"],  5.6)
            p_min = self._safe_float(spr._properties["Min Pressure"]["value"], 7.0)
            q     = k * math.sqrt(max(p_min, 0.0))
            node_min_demand[spr.node] = q

        # Phase 1 continued: propagate flows from leaves → supply
        pipe_flow: dict = {}
        for node in reversed(bfs_order):
            if node is supply_node:
                continue
            pipe = parent_pipe[node]
            own_q  = node_min_demand.get(node, 0.0)
            child_q = sum(
                pipe_flow[parent_pipe[c]]
                for c in children.get(node, [])
                if parent_pipe.get(c) in pipe_flow
            )
            pipe_flow[pipe] = own_q + child_q

        total_demand = sum(
            pipe_flow.get(parent_pipe[c], 0.0)
            for c in children.get(supply_node, [])
        )

        # ─────────────────────────────────────────────────────────────────────
        # Phase 2: Required pressures, working backward (leaves → supply)
        # ─────────────────────────────────────────────────────────────────────
        required_node_pressure: dict = {}      # minimum pressure needed at node

        # Initialise leaf sprinkler nodes with their minimum pressure
        for spr in active_sprinklers:
            n     = spr.node
            p_min = self._safe_float(spr._properties["Min Pressure"]["value"], 7.0)
            # If already set, keep the higher value (multi-sprinkler node)
            if n not in required_node_pressure:
                required_node_pressure[n] = p_min
            else:
                required_node_pressure[n] = max(required_node_pressure[n], p_min)

        # Work backward from leaves toward supply
        for node in reversed(bfs_order):
            if node is supply_node:
                continue
            pipe = parent_pipe[node]
            par  = parent_node[node]
            q    = pipe_flow.get(pipe, 0.0)
            hf   = self._friction_loss_psi(pipe, q)
            dz   = node.z_pos - par.z_pos   # ft; +ve = child higher
            h_e  = 0.433 * dz               # psi; +ve = pressure lost going up

            p_at_node = required_node_pressure.get(node, 0.0)
            p_required_at_parent = p_at_node + hf + h_e

            # Parent needs enough pressure for THIS branch AND any already set
            if par not in required_node_pressure:
                required_node_pressure[par] = p_required_at_parent
            else:
                required_node_pressure[par] = max(
                    required_node_pressure[par], p_required_at_parent
                )

        required_pressure = required_node_pressure.get(supply_node, 0.0)
        # Adjust for supply node elevation (gauge pressure at supply gauge)
        supply_elev_correction = 0.433 * supply_ws.elevation
        required_pressure += supply_elev_correction

        # ─────────────────────────────────────────────────────────────────────
        # Phase 3: Check supply availability
        # ─────────────────────────────────────────────────────────────────────
        avail_pressure = self._supply_available_pressure(supply_ws, total_demand)
        passed         = avail_pressure >= required_pressure

        if not passed:
            messages.append(
                f"❌ Supply insufficient — need {required_pressure:.1f} psi "
                f"@ {total_demand:.1f} gpm; "
                f"supply provides {avail_pressure:.1f} psi."
            )
        else:
            messages.append(
                f"✅ System OK — Demand: {total_demand:.1f} gpm, "
                f"Required: {required_pressure:.1f} psi, "
                f"Available: {avail_pressure:.1f} psi."
            )

        # ─────────────────────────────────────────────────────────────────────
        # Phase 4: Actual working pressures propagated from supply forward
        # ─────────────────────────────────────────────────────────────────────
        actual_supply_pressure = avail_pressure - supply_elev_correction
        node_pressure: dict = {supply_node: actual_supply_pressure}

        pipe_velocity:      dict = {}
        pipe_friction_loss: dict = {}

        for node in bfs_order:
            if node is supply_node:
                continue
            pipe = parent_pipe[node]
            par  = parent_node[node]
            q    = pipe_flow.get(pipe, 0.0)
            hf   = self._friction_loss_psi(pipe, q)
            dz   = node.z_pos - par.z_pos
            h_e  = 0.433 * dz

            node_pressure[node]      = node_pressure.get(par, 0.0) - hf - h_e
            pipe_friction_loss[pipe] = hf

            # Velocity
            d = pipe.get_inner_diameter()   # inches
            v = (q * 0.4085 / (d * d)) if d > 0 else 0.0
            pipe_velocity[pipe] = v

            if v > self.VELOCITY_LIMIT_FPS:
                messages.append(
                    f"⚠️ Velocity {v:.1f} fps > {self.VELOCITY_LIMIT_FPS} fps in "
                    f"{pipe._properties['Diameter']['value']} "
                    f"{pipe._properties['Schedule']['value']} pipe."
                )

        # Check each design sprinkler meets minimum pressure
        for spr in active_sprinklers:
            n     = spr.node
            p_act = node_pressure.get(n, 0.0)
            p_min = self._safe_float(spr._properties["Min Pressure"]["value"], 7.0)
            if p_act < p_min - 0.05:   # 0.05 psi tolerance
                messages.append(
                    f"⚠️ Sprinkler pressure {p_act:.1f} psi < min {p_min:.1f} psi "
                    f"(node at {n.scenePos().x():.0f}, {n.scenePos().y():.0f})."
                )
                passed = False

        return HydraulicResult(
            node_pressures     = node_pressure,
            pipe_flows         = pipe_flow,
            pipe_velocity      = pipe_velocity,
            pipe_friction_loss = pipe_friction_loss,
            total_demand       = total_demand,
            required_pressure  = required_pressure,
            supply_pressure    = avail_pressure,
            passed             = passed,
            messages           = messages,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _fail(msg: str, extra_messages: list | None = None) -> HydraulicResult:
        msgs = list(extra_messages or [])
        msgs.append(f"❌ {msg}")
        return HydraulicResult({}, {}, {}, {}, 0.0, 0.0, 0.0, False, msgs)

    @staticmethod
    def _safe_float(value, default: float) -> float:
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _find_supply_network_node(self, supply_ws, messages: list):
        """
        Return the network Node closest to the WaterSupply item.
        Issues a warning if the nearest node is >50 px away.
        Returns None if the system has no nodes.
        """
        from node import Node
        nodes = self.system.nodes
        if not nodes:
            return None
        pos = supply_ws.scenePos()
        best = min(nodes, key=lambda n: (n.scenePos() - pos).manhattanLength())
        dist = (best.scenePos() - pos).manhattanLength()
        if dist > 50:
            messages.append(
                f"⚠️ Water supply is {dist:.0f} px from nearest node — "
                "connect it closer to a pipe junction."
            )
        return best

    def _build_adjacency(self) -> dict:
        """Return {node: [(pipe, neighbour_node), ...]} for all pipes."""
        adj: dict = {n: [] for n in self.system.nodes}
        for pipe in self.system.pipes:
            n1, n2 = pipe.node1, pipe.node2
            if n1 is None or n2 is None:
                continue
            if n1 in adj:
                adj[n1].append((pipe, n2))
            if n2 in adj:
                adj[n2].append((pipe, n1))
        return adj

    @staticmethod
    def _bfs_tree(root, adjacency: dict):
        """
        BFS from root.  Returns:
            parent_node  : {node: parent_node}
            parent_pipe  : {node: pipe_to_parent}
            children     : {node: [child_node, ...]}
            bfs_order    : list of nodes in BFS order (root first)
        """
        parent_node: dict = {}
        parent_pipe: dict = {}
        children:    dict = {root: []}
        bfs_order:   list = [root]
        visited = {root}
        queue   = deque([root])

        while queue:
            node = queue.popleft()
            for pipe, neighbour in adjacency.get(node, []):
                if neighbour not in visited:
                    visited.add(neighbour)
                    parent_node[neighbour] = node
                    parent_pipe[neighbour] = pipe
                    children.setdefault(neighbour, [])
                    children[node].append(neighbour)
                    bfs_order.append(neighbour)
                    queue.append(neighbour)

        return parent_node, parent_pipe, children, bfs_order

    def _friction_loss_psi(self, pipe, q_gpm: float) -> float:
        """
        Hazen-Williams friction loss for a single pipe.

        hf [psi] = 4.52 × Q^1.852 / (C^1.852 × d^4.87) × L_ft
        """
        if q_gpm <= 0.0:
            return 0.0
        c = self._safe_float(pipe._properties["C-Factor"]["value"], 120.0)
        d = pipe.get_inner_diameter()   # inches
        if d <= 0 or c <= 0:
            return 0.0
        L_ft = pipe.get_length_ft()
        hf = 4.52 * (q_gpm ** 1.852) / ((c ** 1.852) * (d ** 4.87)) * L_ft
        return hf

    def _scene_to_ft(self, scene_px: float) -> float:
        """Convert scene-pixel length to feet using the scale manager."""
        if self.sm and self.sm.is_calibrated:
            mm = scene_px / (self.sm.pixels_per_mm * self.sm.drawing_scale)
            return mm / 304.8          # mm → ft  (1 ft = 304.8 mm)
        # Fallback: assume 96 DPI screen, 1 px ≈ 1/96 inch
        return scene_px / 1152.0      # 96 dpi × 12 in/ft

    def _supply_available_pressure(self, supply_ws, q_demand: float) -> float:
        """
        Interpolate the available pressure from the supply test data.

        The supply curve is approximated with the NFPA 13 / Factory Mutual
        power law:
            P_avail = P_static × [1 - (1 - P_residual/P_static) × (Q/Q_test)^1.85]

        If Q_demand ≤ 0 or Q_test ≤ 0, return static pressure.
        """
        p_s  = supply_ws.static_pressure
        p_r  = supply_ws.residual_pressure
        q_t  = supply_ws.test_flow

        if p_s <= 0:
            return 0.0
        if q_t <= 0 or q_demand <= 0:
            return p_s

        ratio = (q_demand / q_t) ** 1.85
        p_avail = p_s - (p_s - p_r) * ratio
        return max(p_avail, 0.0)
