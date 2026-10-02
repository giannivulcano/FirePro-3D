"""Pure numpy sketch solver — parametric-constraint-system.md §7 (B1).

Weighted minimum-change projection (constraints hard, goals soft) with damped
Gauss-Newton steps, equality substitution (aliases + fixes) BEFORE solving,
union-find component partitioning, and SVD diagnostics. No Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

LIN_TOL = 1e-6          # D18 linear residual bar (mm)
ANG_SCALE = 1000.0      # angular rows are multiplied by this (§7.2)
MAX_ITERS = 25
DAMPING = 1e-12
W_PIN = 1e6             # a drag's pinned handle
W_EDIT = 1e3            # the item a typed edit / transform changed
STEP_TOL = 1e-10


@dataclass(frozen=True)
class PointExpr:
    """A handle point as a function of the variable vector (§5.1).

    Exactly one form: ``const`` (a ground), ``raw`` (the point IS two variables
    — substitutable), or ``idx`` + ``fn`` (derived;
    ``fn(x[list(idx)]) -> (p[2], dp[2, len(idx)])``).
    """
    idx: tuple = ()
    fn: Callable | None = None
    raw: tuple | None = None
    const: tuple | None = None

    @property
    def deps(self) -> tuple:
        if self.const is not None:
            return ()
        return tuple(self.raw) if self.raw is not None else tuple(self.idx)

    def eval(self, x: np.ndarray):
        """``(p, dp)``; ``dp`` columns follow :attr:`deps`."""
        if self.const is not None:
            return np.array(self.const, dtype=float), np.zeros((2, 0))
        if self.raw is not None:
            return np.array([x[self.raw[0]], x[self.raw[1]]], dtype=float), np.eye(2)
        return self.fn(x[list(self.idx)])


def raw_point(ix: int, iy: int) -> PointExpr:
    return PointExpr(raw=(ix, iy))


def const_point(px: float, py: float) -> PointExpr:
    return PointExpr(const=(float(px), float(py)))


@dataclass
class Row:
    """One residual: ``fn(x) -> (r, grad)``; ``grad`` follows ``deps``."""
    cid: str
    deps: tuple
    fn: Callable


@dataclass
class System:
    x: np.ndarray
    aliases: list = field(default_factory=list)   # (i, j, cid): x_i == x_j
    fixes: list = field(default_factory=list)     # (i, value, cid)
    rows: list = field(default_factory=list)      # Row


@dataclass
class SolveResult:
    x: np.ndarray
    converged: bool
    max_residual: float


@dataclass
class Diagnostics:
    nvars: int
    rank: int
    dof: int


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, a: int) -> int:
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


class _Reduced:
    """The variable space after equality substitution (§7.2)."""

    def __init__(self, sys: System):
        n = len(sys.x)
        uf = _UF(n)
        for i, j, _cid in sys.aliases:
            uf.union(i, j)
        self.rep = [uf.find(i) for i in range(n)]
        self.fixed: dict[int, float] = {}
        self.conflicts: list[str] = []
        for i, v, cid in sys.fixes:
            r = self.rep[i]
            if r in self.fixed and abs(self.fixed[r] - v) > LIN_TOL:
                self.conflicts.append(cid)
            self.fixed.setdefault(r, float(v))
        reps = sorted({r for r in self.rep if r not in self.fixed})
        self.col = {r: k for k, r in enumerate(reps)}
        self.n = len(reps)
        self.members: list[list[int]] = [[] for _ in range(self.n)]
        # rep -> full-space members of a fixed (eliminated) group
        self.fixed_groups: dict[int, list[int]] = {r: [] for r in self.fixed}
        for i in range(n):
            r = self.rep[i]
            if r in self.fixed:
                self.fixed_groups[r].append(i)
            else:
                self.members[self.col[r]].append(i)

    def col_of(self, i: int):
        return self.col.get(self.rep[i])

    def reduce(self, vec: np.ndarray, w: np.ndarray):
        z = np.empty(self.n)
        wz = np.empty(self.n)
        for k, mem in enumerate(self.members):
            ws = w[mem]
            s = float(ws.sum())
            z[k] = float((ws * vec[mem]).sum()) / s
            wz[k] = s
        return z, wz

    def write_fixed(self, x: np.ndarray, active: set | None) -> None:
        """Write fixed groups into *x* (only groups touching *active*, if given)."""
        for r, mem in self.fixed_groups.items():
            if active is None or active.intersection(mem):
                x[mem] = self.fixed[r]

    def write(self, x: np.ndarray, z: np.ndarray, cols) -> None:
        """Write reduced columns *cols* of *z* back to their full-space members."""
        for k in cols:
            x[self.members[k]] = z[k]


def _eval_rows(rows, red: _Reduced, x: np.ndarray, cols: list[int]):
    pos = {c: j for j, c in enumerate(cols)}
    F = np.empty(len(rows))
    J = np.zeros((len(rows), len(cols)))
    for a, row in enumerate(rows):
        r, g = row.fn(x)
        F[a] = r
        for d, gv in zip(row.deps, g):
            k = red.col_of(d)
            if k is not None and k in pos:
                J[a, pos[k]] += gv
    return F, J


class NumpySolver:
    """The v1 ``SketchSolver`` (spec §7.1)."""

    def _components(self, rows, red: _Reduced):
        uf = _UF(red.n)
        row_cols = []
        for row in rows:
            cs = [k for k in (red.col_of(d) for d in row.deps) if k is not None]
            row_cols.append(cs)
            for k in cs[1:]:
                uf.union(cs[0], k)
        comps: dict[int, tuple[list, list]] = {}
        for k in range(red.n):
            comps.setdefault(uf.find(k), ([], []))[0].append(k)
        orphans = []          # rows whose every dep is fixed: nothing can move
        for row, cs in zip(rows, row_cols):
            if cs:
                comps[uf.find(cs[0])][1].append(row)
            else:
                orphans.append(row)
        return list(comps.values()), orphans

    def solve(self, sys: System, goals, weights, active=None) -> SolveResult:
        """Weighted min-change projection of *goals* onto ``F(x) = 0``.

        Args:
            sys: The system (current values in ``sys.x``).
            goals: Per-variable goal values (full space).
            weights: Per-variable goal weights (full space, > 0).
            active: Full-space variable indices whose components are solved;
                ``None`` = all. Other components (and fixed groups not touching
                *active*) keep their current values bit-for-bit.

        Returns:
            ``SolveResult``; ``converged`` is judged over the solved components'
            rows (plus all-fixed rows touching *active*) against ``LIN_TOL``.
            Aliases and fixes hold exactly by construction. On failure the
            caller must not write back (D10 hold-last-good).
        """
        red = _Reduced(sys)
        x0 = np.asarray(sys.x, dtype=float)
        if red.conflicts:
            return SolveResult(x0.copy(), False, float("inf"))
        zg, w = red.reduce(np.asarray(goals, dtype=float),
                           np.asarray(weights, dtype=float))
        act_full = None if active is None else set(active)
        act = (None if act_full is None
               else {red.col_of(i) for i in act_full} - {None})
        # Untouched components keep x0 bit-for-bit; solved ones are written.
        x = x0.copy()
        red.write_fixed(x, act_full)
        z = zg.copy()
        comps, orphans = self._components(sys.rows, red)
        checked = [r for r in orphans
                   if act_full is None or act_full.intersection(r.deps)]
        for cols, rows in comps:
            if act is not None and not act.intersection(cols):
                continue
            red.write(x, z, cols)          # start from the goals
            if not rows:
                continue                   # rowless: exactly the weighted-mean goal
            checked.extend(rows)
            # Rows may read eliminated (fixed) vars: make them hold their value.
            red.write_fixed(x, {d for row in rows for d in row.deps})
            winv = 1.0 / w[cols]
            for _ in range(MAX_ITERS):
                F, J = _eval_rows(rows, red, x, cols)
                g = zg[cols] - z[cols]
                A = (J * winv) @ J.T + DAMPING * np.eye(len(rows))
                rhs = -F - J @ g
                try:
                    lam = np.linalg.solve(A, rhs)
                except np.linalg.LinAlgError:
                    lam = np.linalg.lstsq(A, rhs, rcond=None)[0]
                dz = g + winv * (J.T @ lam)
                if not np.all(np.isfinite(dz)):
                    break                  # diverged: final check reports failure
                z[cols] += dz
                red.write(x, z, cols)
                scale = max(1.0, float(np.max(np.abs(z[cols]))))
                if float(np.max(np.abs(dz))) < STEP_TOL * scale:
                    break
        worst = 0.0
        if checked:
            worst = float(np.max(np.abs([row.fn(x)[0] for row in checked])))
        converged = bool(np.isfinite(worst)) and worst <= LIN_TOL
        return SolveResult(x, converged, worst)

    def diagnose(self, sys: System) -> Diagnostics:
        """DOF = free variables after substitution − rank(J) (§7.4)."""
        red = _Reduced(sys)
        if not sys.rows or red.n == 0:
            return Diagnostics(red.n, 0, red.n)
        F, J = _eval_rows(sys.rows, red, np.asarray(sys.x, float), list(range(red.n)))
        s = np.linalg.svd(J, compute_uv=False)
        tol = max(J.shape) * np.finfo(float).eps * (s[0] if s.size else 0.0)
        rank = int((s > max(tol, 1e-9)).sum())
        return Diagnostics(red.n, rank, red.n - rank)


# ── §7.3 residual catalogue — builders (one per IMPLEMENTED type) ─────────

def build_horizontal(cid: str, ends, sys: System) -> None:
    """Horizontal (pinned 2026-10-01): ``ends`` = (a, b) PointExprs.

    Raw/raw -> alias the Y variables; raw/const (origin) -> fix Y; otherwise a
    row ``y_b - y_a``.
    """
    a, b = ends
    if a.raw is not None and b.raw is not None:
        sys.aliases.append((a.raw[1], b.raw[1], cid))
        return
    if a.const is not None and b.raw is not None:
        sys.fixes.append((b.raw[1], float(a.const[1]), cid))
        return
    if b.const is not None and a.raw is not None:
        sys.fixes.append((a.raw[1], float(b.const[1]), cid))
        return
    deps = tuple(dict.fromkeys(a.deps + b.deps))
    pos = {d: k for k, d in enumerate(deps)}

    def fn(x):
        pa, da = a.eval(x)
        pb, db = b.eval(x)
        g = np.zeros(len(deps))
        for c, d in enumerate(a.deps):
            g[pos[d]] -= da[1, c]
        for c, d in enumerate(b.deps):
            g[pos[d]] += db[1, c]
        return float(pb[1] - pa[1]), g

    sys.rows.append(Row(cid, deps, fn))


BUILDERS = {"horizontal": build_horizontal}
