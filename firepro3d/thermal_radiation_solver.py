"""
Thermal Radiation Analysis Solver.

Evaluates radiative heat transfer between building surfaces using
a surface-to-surface Stefan-Boltzmann model with geometric view factors.

Architecture supports future radiation models (SFPE, NFPA) via the
abstract ``RadiationModel`` base class.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fire_curves import can_ulc_s101, constant_temperature, iso_834


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RadiationResult:
    """Container for thermal radiation analysis results."""

    # Per-receiver data (keyed by the entity object)
    per_receiver_mesh: dict = field(default_factory=dict)
    """entity -> {"vertices": ndarray (Nx3), "faces": ndarray (Mx3)}"""

    per_receiver_flux: dict = field(default_factory=dict)
    """entity -> ndarray of heat flux per face (kW/m^2)"""

    per_receiver_centroid: dict = field(default_factory=dict)
    """entity -> ndarray (Mx3) centroids of each face in mm"""

    per_emitter_contribution: dict = field(default_factory=dict)
    """entity -> float total contribution to all receivers (kW/m^2)"""

    max_radiation: float = 0.0
    """Peak heat flux on any receiver cell (kW/m^2)"""

    max_location: np.ndarray = field(default_factory=lambda: np.zeros(3))
    """3-D coordinates of peak flux location (mm)"""

    area_exceeding: float = 0.0
    """Total receiver area exceeding the threshold (m^2)"""

    total_receiver_area: float = 0.0
    """Total receiver surface area (m^2)"""

    threshold: float = 12.5
    """Performance criterion (kW/m^2)"""

    passed: bool = True
    """True if max_radiation < threshold"""

    messages: list[str] = field(default_factory=list)

    parameters: dict = field(default_factory=dict)
    """Copy of input parameters for reporting / serialization."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_surface_mesh(entity, level_manager, scale_manager) -> dict | None:
    """Call ``entity.get_3d_mesh()`` and return the raw mesh dict.

    Works for WallSegment, RoofItem, FloorSlab – anything that implements
    ``get_3d_mesh(level_manager=...)``.
    """
    try:
        return entity.get_3d_mesh(level_manager=level_manager)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class RadiationModel(ABC):
    """Abstract interface for radiation calculation models."""

    @abstractmethod
    def compute(
        self,
        emitter_meshes: list[tuple[Any, dict]],
        receiver_meshes: list[tuple[Any, dict]],
        params: dict,
    ) -> RadiationResult:
        """Run the radiation analysis and return results.

        Parameters
        ----------
        emitter_meshes : list of (entity, mesh_dict) pairs
        receiver_meshes : list of (entity, mesh_dict) pairs
        params : dict of analysis parameters from the dialog
        """
        ...


# ---------------------------------------------------------------------------
# Standard surface-to-surface model
# ---------------------------------------------------------------------------

class StandardSurfaceRadiationModel(RadiationModel):
    """View-factor based Stefan-Boltzmann radiation model."""

    STEFAN_BOLTZMANN = 5.67e-8  # W / (m^2 K^4)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        emitter_meshes: list[tuple[Any, dict]],
        receiver_meshes: list[tuple[Any, dict]],
        params: dict,
    ) -> RadiationResult:
        result = RadiationResult(parameters=dict(params), threshold=params.get("threshold", 12.5))

        # --- resolve emitter surface temperature (Kelvin) ---
        T_emit_K = self._resolve_temperature(params)
        T_amb_K = constant_temperature(params.get("ambient_c", 20.0))
        emissivity = params.get("emissivity", 1.0)
        resolution_mm = params.get("resolution_mm", 500.0)
        cutoff_mm = params.get("cutoff_mm", 50000.0)
        check_los = params.get("check_los", True)

        # --- pre-process emitter cells ---
        all_emit_centroids = []
        all_emit_normals = []
        all_emit_areas = []  # m^2
        emit_entity_slices: list[tuple[Any, int, int]] = []

        for entity, mesh in emitter_meshes:
            if mesh is None:
                result.messages.append(f"Skipped emitter (no mesh): {getattr(entity, '_name', '?')}")
                continue
            c, n, a = self._mesh_to_cells(mesh, resolution_mm)
            if len(c) == 0:
                continue
            start = len(all_emit_centroids)
            all_emit_centroids.append(c)
            all_emit_normals.append(n)
            all_emit_areas.append(a)
            emit_entity_slices.append((entity, start, start + len(c)))

        if not all_emit_centroids:
            result.messages.append("No valid emitter surfaces.")
            return result

        emit_c = np.vstack(all_emit_centroids)   # (Ne, 3) mm

        result.messages.append(
            f"Emitter: {len(emit_c)} cells, T={T_emit_K:.0f} K, "
            f"E={emissivity * self.STEFAN_BOLTZMANN * (T_emit_K**4 - T_amb_K**4) / 1000:.1f} kW/m\u00b2"
        )
        emit_n = np.vstack(all_emit_normals)      # (Ne, 3)
        emit_a = np.concatenate(all_emit_areas)   # (Ne,) m^2

        # --- collect blocking geometry for LOS checks ---
        # IMPORTANT: Exclude emitter and receiver surfaces from blockers.
        # Only OTHER geometry (third-party walls, roofs, etc.) should block.
        # Including emitter/receiver surfaces would cause self-occlusion
        # since rays originate from and terminate on those surfaces.
        emitter_receiver_entities = set()
        for entity, _mesh in emitter_meshes + receiver_meshes:
            emitter_receiver_entities.add(id(entity))

        all_block_verts = []
        all_block_faces = []
        offset = 0
        # Collect blocking geometry from all_scene_meshes if provided
        for blocker_mesh in params.get("blocking_meshes", []):
            if blocker_mesh is None:
                continue
            v = np.asarray(blocker_mesh["vertices"], dtype=np.float64)
            f = np.asarray(blocker_mesh["faces"], dtype=np.int32)
            all_block_faces.append(f + offset)
            all_block_verts.append(v)
            offset += len(v)
        if all_block_verts:
            block_verts = np.vstack(all_block_verts)
            block_faces = np.vstack(all_block_faces)
        else:
            block_verts = np.empty((0, 3))
            block_faces = np.empty((0, 3), dtype=np.int32)

        # --- Emissive power (constant for all emitter cells) ---
        # E = ε σ (T_e^4 - T_a^4)  in W/m^2
        E = emissivity * self.STEFAN_BOLTZMANN * (T_emit_K ** 4 - T_amb_K ** 4)
        E_kw = E / 1000.0  # kW/m^2

        # --- per-receiver computation ---
        global_max_flux = 0.0
        global_max_loc = np.zeros(3)
        total_exceed_area = 0.0
        total_recv_area = 0.0

        # Per-emitter contribution accumulator
        emitter_contrib = {}
        for entity, _s, _e in emit_entity_slices:
            emitter_contrib[entity] = 0.0

        for entity, mesh in receiver_meshes:
            if mesh is None:
                result.messages.append(f"Skipped receiver (no mesh): {getattr(entity, '_name', '?')}")
                continue

            # Subdivide receiver mesh
            recv_c, recv_n, recv_a = self._mesh_to_cells(mesh, resolution_mm)
            if len(recv_c) == 0:
                continue

            # Also build the subdivided mesh for visualization
            sub_mesh = self._subdivide_mesh(mesh, resolution_mm)
            result.per_receiver_mesh[entity] = sub_mesh

            Nr = len(recv_c)
            Ne = len(emit_c)

            # --- View factors (Nr x Ne) ---
            # Displacement vectors: recv -> emit
            # d[j, i, :] = emit_c[i] - recv_c[j]   (mm)
            d = emit_c[np.newaxis, :, :] - recv_c[:, np.newaxis, :]  # (Nr, Ne, 3)
            dist = np.linalg.norm(d, axis=2)  # (Nr, Ne) mm
            dist_m = dist / 1000.0  # metres

            # Avoid division by zero
            safe_dist = np.where(dist_m > 1e-6, dist_m, 1e-6)

            # Unit direction vectors
            d_hat = d / np.where(dist[:, :, np.newaxis] > 1e-6,
                                 dist[:, :, np.newaxis], 1.0)

            # cos(theta_i) = dot(emit_normal, -d_hat)  (emitter normal toward receiver)
            cos_i = np.einsum("ik,jik->ji", emit_n, -d_hat)  # (Nr, Ne)
            # cos(theta_j) = dot(recv_normal, d_hat)    (receiver normal toward emitter)
            cos_j = np.einsum("jk,jik->ji", recv_n, d_hat)   # (Nr, Ne)

            # Back-face culling + distance cutoff
            valid = (cos_i > 0) & (cos_j > 0) & (dist < cutoff_mm)

            n_valid = int(np.sum(valid))
            result.messages.append(
                f"  Receiver '{getattr(entity, '_name', '?')}': "
                f"{Nr} cells, {n_valid}/{Nr*Ne} valid pairs, "
                f"dist range {float(np.min(dist)):.0f}-{float(np.max(dist)):.0f} mm"
            )

            # View factor: F_ij = cos_i * cos_j / (pi * r^2) * A_emitter
            # emit_a is in m^2
            vf = np.zeros((Nr, Ne), dtype=np.float64)
            vf[valid] = (
                cos_i[valid] * cos_j[valid]
                / (math.pi * safe_dist[valid] ** 2)
                * emit_a[np.newaxis, :].repeat(Nr, axis=0)[valid]
            )

            # --- Line-of-sight check (optional, expensive) ---
            if check_los and len(block_faces) > 0:
                los_mask = self._check_line_of_sight(
                    recv_c, emit_c, valid, block_verts, block_faces
                )
                vf *= los_mask

            # --- Heat flux per receiver cell ---
            # q_j = sum_i ( E_kw * F_ij )   kW/m^2
            flux = E_kw * np.sum(vf, axis=1)  # (Nr,)

            result.per_receiver_flux[entity] = flux
            result.per_receiver_centroid[entity] = recv_c

            # Accumulate per-emitter contributions
            for em_entity, s, e in emit_entity_slices:
                contrib = E_kw * np.sum(vf[:, s:e])
                emitter_contrib[em_entity] += contrib

            # --- Statistics ---
            recv_area_m2 = np.sum(recv_a)
            total_recv_area += recv_area_m2

            max_idx = np.argmax(flux)
            if flux[max_idx] > global_max_flux:
                global_max_flux = flux[max_idx]
                global_max_loc = recv_c[max_idx].copy()

            exceed_mask = flux >= result.threshold
            total_exceed_area += np.sum(recv_a[exceed_mask])

        result.per_emitter_contribution = emitter_contrib
        result.max_radiation = global_max_flux
        result.max_location = global_max_loc
        result.area_exceeding = total_exceed_area
        result.total_receiver_area = total_recv_area
        result.passed = global_max_flux < result.threshold

        if not result.passed:
            result.messages.append(
                f"EXCEEDANCE: Max radiation {global_max_flux:.2f} kW/m\u00b2 "
                f"exceeds threshold {result.threshold:.1f} kW/m\u00b2"
            )
        else:
            result.messages.append(
                f"PASS: Max radiation {global_max_flux:.2f} kW/m\u00b2 "
                f"is below threshold {result.threshold:.1f} kW/m\u00b2"
            )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_temperature(self, params: dict) -> float:
        """Return emitter surface temperature in Kelvin."""
        curve = params.get("fire_curve", "Constant")
        if curve == "CAN/ULC-S101":
            time_min = params.get("fire_duration_min", 60.0)
            ambient_c = params.get("ambient_c", 20.0)
            return can_ulc_s101(time_min, ambient_c)
        elif curve == "ISO 834":
            time_min = params.get("fire_duration_min", 60.0)
            ambient_c = params.get("ambient_c", 20.0)
            return iso_834(time_min, ambient_c)
        else:
            return constant_temperature(params.get("emitter_temp_c", 800.0))

    # ------------------------------------------------------------------
    def _mesh_to_cells(
        self, mesh_data: dict, resolution_mm: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Convert a triangulated mesh into analysis cells.

        Returns
        -------
        centroids : (N, 3) float64, positions in mm
        normals   : (N, 3) float64, unit normals
        areas     : (N,) float64, areas in **m^2**
        """
        verts = np.asarray(mesh_data["vertices"], dtype=np.float64)
        faces = np.asarray(mesh_data["faces"], dtype=np.int32)

        if len(faces) == 0:
            return np.empty((0, 3)), np.empty((0, 3)), np.empty(0)

        # Triangle vertices
        v0 = verts[faces[:, 0]]  # (M, 3)
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]

        # Cross product for normal and area
        edge1 = v1 - v0
        edge2 = v2 - v0
        cross = np.cross(edge1, edge2)  # (M, 3)
        area_2x = np.linalg.norm(cross, axis=1)  # twice triangle area in mm^2

        # Filter degenerate triangles
        valid = area_2x > 1e-6
        if not np.any(valid):
            return np.empty((0, 3)), np.empty((0, 3)), np.empty(0)

        v0 = v0[valid]
        v1 = v1[valid]
        v2 = v2[valid]
        cross = cross[valid]
        area_2x = area_2x[valid]

        # Check if triangles need subdivision
        areas_mm2 = area_2x / 2.0
        target_area = resolution_mm ** 2

        all_centroids = []
        all_normals = []
        all_areas = []

        for i in range(len(v0)):
            tri_area = areas_mm2[i]
            normal = cross[i] / area_2x[i]  # unit normal

            if tri_area <= target_area * 2.0:
                # Small enough — single cell
                centroid = (v0[i] + v1[i] + v2[i]) / 3.0
                all_centroids.append(centroid)
                all_normals.append(normal)
                all_areas.append(tri_area / 1e6)  # m^2
            else:
                # Subdivide via barycentric grid
                n_subdiv = max(2, int(math.ceil(math.sqrt(tri_area / target_area))))
                sub_c, sub_a = self._subdivide_triangle(
                    v0[i], v1[i], v2[i], n_subdiv
                )
                all_centroids.extend(sub_c)
                all_normals.extend([normal] * len(sub_c))
                all_areas.extend([a / 1e6 for a in sub_a])  # m^2

        if not all_centroids:
            return np.empty((0, 3)), np.empty((0, 3)), np.empty(0)

        return (
            np.array(all_centroids, dtype=np.float64),
            np.array(all_normals, dtype=np.float64),
            np.array(all_areas, dtype=np.float64),
        )

    @staticmethod
    def _subdivide_triangle(
        p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, n: int
    ) -> tuple[list[np.ndarray], list[float]]:
        """Subdivide a triangle into n^2 sub-triangles using barycentric grid.

        Returns lists of (centroid, area_mm2) for each sub-triangle.
        """
        centroids: list[np.ndarray] = []
        areas: list[float] = []

        for i in range(n):
            for j in range(n - i):
                # Two sub-triangles per grid cell (except last row)
                # First triangle
                a0 = i / n
                a1 = j / n
                b0 = (i + 1) / n
                b1 = j / n
                c0 = i / n
                c1 = (j + 1) / n

                t0 = p0 + a0 * (p1 - p0) + a1 * (p2 - p0)
                t1 = p0 + b0 * (p1 - p0) + b1 * (p2 - p0)
                t2 = p0 + c0 * (p1 - p0) + c1 * (p2 - p0)

                cent = (t0 + t1 + t2) / 3.0
                area = np.linalg.norm(np.cross(t1 - t0, t2 - t0)) / 2.0
                if area > 1e-6:
                    centroids.append(cent)
                    areas.append(area)

                # Second triangle (the "upper" one in the grid cell)
                if i + j + 2 <= n:
                    d0 = (i + 1) / n
                    d1 = (j + 1) / n
                    t3 = p0 + d0 * (p1 - p0) + d1 * (p2 - p0)

                    cent2 = (t1 + t2 + t3) / 3.0
                    area2 = np.linalg.norm(np.cross(t2 - t1, t3 - t1)) / 2.0
                    if area2 > 1e-6:
                        centroids.append(cent2)
                        areas.append(area2)

        return centroids, areas

    # ------------------------------------------------------------------
    def _subdivide_mesh(self, mesh_data: dict, resolution_mm: float) -> dict:
        """Subdivide a mesh for visualization, returning refined verts + faces.

        Each original triangle is subdivided if its area exceeds the
        target resolution. Returns a new mesh dict with the same format.
        """
        verts = np.asarray(mesh_data["vertices"], dtype=np.float64)
        faces = np.asarray(mesh_data["faces"], dtype=np.int32)

        if len(faces) == 0:
            return {"vertices": verts, "faces": faces}

        target_area = resolution_mm ** 2
        new_verts_list: list[np.ndarray] = []
        new_faces_list: list[np.ndarray] = []
        vert_offset = 0

        for fi in range(len(faces)):
            p0 = verts[faces[fi, 0]]
            p1 = verts[faces[fi, 1]]
            p2 = verts[faces[fi, 2]]

            edge1 = p1 - p0
            edge2 = p2 - p0
            tri_area = np.linalg.norm(np.cross(edge1, edge2)) / 2.0

            if tri_area <= target_area * 2.0:
                # Keep original triangle
                new_verts_list.append(np.array([p0, p1, p2]))
                new_faces_list.append(np.array([[vert_offset, vert_offset + 1, vert_offset + 2]]))
                vert_offset += 3
            else:
                n = max(2, int(math.ceil(math.sqrt(tri_area / target_area))))
                sv, sf = self._subdivide_triangle_mesh(p0, p1, p2, n)
                new_verts_list.append(sv)
                new_faces_list.append(sf + vert_offset)
                vert_offset += len(sv)

        if not new_verts_list:
            return {"vertices": np.empty((0, 3)), "faces": np.empty((0, 3), dtype=np.int32)}

        return {
            "vertices": np.vstack(new_verts_list),
            "faces": np.vstack(new_faces_list),
        }

    @staticmethod
    def _subdivide_triangle_mesh(
        p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, n: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Subdivide one triangle into n^2 sub-triangles.

        Returns (vertices, faces) arrays for the subdivided mesh.
        """
        # Build grid of vertices using barycentric coordinates
        vert_map: dict[tuple[int, int], int] = {}
        verts: list[np.ndarray] = []

        def get_vert(i: int, j: int) -> int:
            key = (i, j)
            if key not in vert_map:
                u = i / n
                v = j / n
                pt = p0 + u * (p1 - p0) + v * (p2 - p0)
                vert_map[key] = len(verts)
                verts.append(pt)
            return vert_map[key]

        faces: list[list[int]] = []
        for i in range(n):
            for j in range(n - i):
                # Lower triangle
                a = get_vert(i, j)
                b = get_vert(i + 1, j)
                c = get_vert(i, j + 1)
                faces.append([a, b, c])

                # Upper triangle
                if i + j + 2 <= n:
                    d = get_vert(i + 1, j + 1)
                    faces.append([b, d, c])

        return np.array(verts, dtype=np.float64), np.array(faces, dtype=np.int32)

    # ------------------------------------------------------------------
    def _check_line_of_sight(
        self,
        recv_c: np.ndarray,   # (Nr, 3) mm
        emit_c: np.ndarray,   # (Ne, 3) mm
        valid: np.ndarray,    # (Nr, Ne) bool — only check these pairs
        block_verts: np.ndarray,  # (V, 3) mm
        block_faces: np.ndarray,  # (F, 3) int
    ) -> np.ndarray:
        """Check line-of-sight between receiver-emitter pairs.

        Returns (Nr, Ne) float mask: 1.0 = visible, 0.0 = blocked.
        Uses Moller-Trumbore ray-triangle intersection.
        """
        Nr, Ne = valid.shape
        los = np.ones((Nr, Ne), dtype=np.float64)

        # Get indices of valid pairs
        rj, ei = np.where(valid)
        if len(rj) == 0:
            return los

        # Triangle vertices for blocking geometry
        t0 = block_verts[block_faces[:, 0]]  # (Nf, 3)
        t1 = block_verts[block_faces[:, 1]]
        t2 = block_verts[block_faces[:, 2]]
        e1_tri = t1 - t0  # (Nf, 3)
        e2_tri = t2 - t0  # (Nf, 3)

        # Process in batches to limit memory
        BATCH = 5000
        for b_start in range(0, len(rj), BATCH):
            b_end = min(b_start + BATCH, len(rj))
            b_rj = rj[b_start:b_end]
            b_ei = ei[b_start:b_end]

            origins = recv_c[b_rj]           # (B, 3)
            targets = emit_c[b_ei]           # (B, 3)
            ray_dir = targets - origins      # (B, 3)
            ray_len = np.linalg.norm(ray_dir, axis=1, keepdims=True)
            ray_dir = ray_dir / np.where(ray_len > 1e-6, ray_len, 1.0)

            # Moller-Trumbore for each ray against all triangles
            # We check if any triangle blocks each ray
            Nf = len(block_faces)
            B = len(origins)

            blocked = np.zeros(B, dtype=bool)

            # Process triangles in chunks to limit memory
            TRI_BATCH = 2000
            for t_start in range(0, Nf, TRI_BATCH):
                t_end = min(t_start + TRI_BATCH, Nf)
                e1_b = e1_tri[t_start:t_end]  # (Tf, 3)
                e2_b = e2_tri[t_start:t_end]
                t0_b = t0[t_start:t_end]

                # h = cross(ray_dir, e2)  -> (B, Tf, 3)
                rd = ray_dir[:, np.newaxis, :]  # (B, 1, 3)
                e2_exp = e2_b[np.newaxis, :, :]  # (1, Tf, 3)
                h = np.cross(rd, e2_exp)  # (B, Tf, 3)

                e1_exp = e1_b[np.newaxis, :, :]
                a_det = np.einsum("btk,btk->bt", h, e1_exp)  # (B, Tf)

                # Skip near-parallel rays
                valid_det = np.abs(a_det) > 1e-8
                inv_a = np.where(valid_det, 1.0 / np.where(valid_det, a_det, 1.0), 0.0)

                s = origins[:, np.newaxis, :] - t0_b[np.newaxis, :, :]  # (B, Tf, 3)
                u_param = inv_a * np.einsum("btk,btk->bt", s, h)

                q = np.cross(s, e1_exp)  # (B, Tf, 3)
                v_param = inv_a * np.einsum("btk,btk->bt", rd, q)

                t_param = inv_a * np.einsum("btk,btk->bt", e2_exp, q)

                # Valid intersection: u in [0,1], v in [0,1], u+v <= 1,
                # t > small_eps and t < ray_len (hit is between origin and target)
                eps = 1.0  # 1mm offset to avoid self-intersection
                hit = (
                    valid_det
                    & (u_param >= 0) & (u_param <= 1)
                    & (v_param >= 0) & (u_param + v_param <= 1)
                    & (t_param > eps)
                    & (t_param < ray_len.flatten()[:, np.newaxis] - eps)
                )

                # If any triangle blocks the ray
                blocked |= np.any(hit, axis=1)

            # Write blocked results
            for idx in range(B):
                if blocked[idx]:
                    los[b_rj[idx], b_ei[idx]] = 0.0

        return los
