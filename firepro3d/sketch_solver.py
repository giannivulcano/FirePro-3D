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
DAMPING_REL = 1e-12     # Tikhonov term, relative to max diag(J W^-1 J^T)
W_PIN = 1e6             # a drag's pinned handle
W_EDIT = 1e3            # the item a typed edit / transform changed
STEP_TOL = 1e-10
RES_STOP = 1e-3 * LIN_TOL   # stop once every row is this tight (§7.2)


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
    """Variables + equalities + residual rows for one sketch.

    The solver caches its structural analysis (substitution, components,
    Jacobian scatter indices) on the System, keyed on the content of
    ``aliases`` / ``fixes`` (tuples compared by value), the identity of each
    ``Row`` and ``len(x)``; any edit to those lists rebuilds it. A ``Row``
    object must not be mutated after a solve (replace it instead). The values
    in ``x`` may change freely between solves.
    """
    x: np.ndarray
    aliases: list = field(default_factory=list)   # (i, j, cid): x_i == x_j
    fixes: list = field(default_factory=list)     # (i, value, cid)
    rows: list = field(default_factory=list)      # Row
    _structure: object = field(default=None, init=False, repr=False,
                               compare=False)


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
    conflicts: list = field(default_factory=list)   # cids of contradictory fixes


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


class _Component:
    """One union-find component of the reduced space, with precomputed indices.

    The Jacobian is kept sparse as COO entries (``ja`` row, ``jc`` local column,
    values = the concatenated free row gradients). ``pe``/``pf`` enumerate every
    ordered pair of entries sharing a column, so ``J W^-1 J^T`` is one
    ``np.bincount`` over ``pidx`` (cost ~ sum of column-count squares, never more
    than the dense product).
    """
    __slots__ = ("vars", "var_lcol", "ncols", "rows", "jidx", "jmask", "fgroups",
                 "ja", "jc", "pe", "pf", "pidx", "pc")

    def __init__(self, ncols: int):
        self.ncols = ncols
        self.vars = None        # full-space member vars (array)
        self.var_lcol = None    # their local column (array, parallel to vars)
        self.rows = []
        self.jidx = None        # flat row*ncols + lcol scatter index (free deps)
        self.jmask = None       # which concatenated gradient entries are free
        self.fgroups = set()    # fixed groups its rows read
        self.ja = self.jc = None                   # COO entry row / local col
        self.pe = self.pf = self.pidx = self.pc = None   # same-column entry pairs


class _Structure:
    """Equality substitution (§7.2) + components, computed once per structure."""

    def __init__(self, sys: System):
        n = len(sys.x)
        self.key = _structure_key(sys)
        uf = _UF(n)
        for i, j, _cid in sys.aliases:
            uf.union(i, j)
        rep = [uf.find(i) for i in range(n)]
        fixed: dict[int, float] = {}
        self.conflicts: list[str] = []
        for i, v, cid in sys.fixes:
            r = rep[i]
            if r in fixed and abs(fixed[r] - v) > LIN_TOL:
                self.conflicts.append(cid)
            fixed.setdefault(r, float(v))
        fg_of_rep = {r: k for k, r in enumerate(fixed)}
        reps = sorted({r for r in rep if r not in fixed})
        col_of_rep = {r: k for k, r in enumerate(reps)}
        self.ncols = len(reps)
        var_col = np.full(n, -1, dtype=np.intp)
        var_fg = np.full(n, -1, dtype=np.intp)
        for i, r in enumerate(rep):
            if r in fixed:
                var_fg[i] = fg_of_rep[r]
            else:
                var_col[i] = col_of_rep[r]
        self.var_col, self.var_fg = var_col, var_fg
        self.fg_value = np.array(list(fixed.values()), dtype=float)
        self.fixed_vars = np.flatnonzero(var_fg >= 0)
        self.fixed_vals = self.fg_value[var_fg[self.fixed_vars]]
        self.fg_members = [self.fixed_vars[var_fg[self.fixed_vars] == k]
                           for k in range(len(fixed))]

        # components: union over the free columns each row touches
        uf2 = _UF(self.ncols)
        row_info = []
        for row in sys.rows:
            deps = np.asarray(row.deps, dtype=np.intp)
            cs = var_col[deps]
            free = cs[cs >= 0]
            for k in free[1:]:
                uf2.union(int(free[0]), int(k))
            row_info.append((deps, cs, free))
        root_comp: dict[int, int] = {}
        col_comp = np.empty(self.ncols, dtype=np.intp)
        col_local = np.empty(self.ncols, dtype=np.intp)
        counts: list[int] = []
        for c in range(self.ncols):
            ci = root_comp.setdefault(uf2.find(c), len(root_comp))
            if ci == len(counts):
                counts.append(0)
            col_comp[c] = ci
            col_local[c] = counts[ci]
            counts[ci] += 1
        self.comps = [_Component(k) for k in counts]
        free_vars = np.flatnonzero(var_col >= 0)
        var_comp = np.full(n, -1, dtype=np.intp)
        var_comp[free_vars] = col_comp[var_col[free_vars]]
        self.var_comp = var_comp
        for ci, comp in enumerate(self.comps):
            mv = free_vars[var_comp[free_vars] == ci]
            comp.vars = mv
            comp.var_lcol = col_local[var_col[mv]]
        self.orphans: list = []                   # rows with no free dependency
        self.fg_readers = [set() for _ in fixed]  # fixed group -> component ids
        self.fg_orphans = [[] for _ in fixed]     # fixed group -> orphan rows
        per_comp: dict[int, list] = {}
        for row, (deps, cs, free) in zip(sys.rows, row_info):
            fgs = {int(g) for g in var_fg[deps] if g >= 0}
            if free.size == 0:
                self.orphans.append(row)
                for g in fgs:
                    self.fg_orphans[g].append(row)
                continue
            ci = int(col_comp[free[0]])
            per_comp.setdefault(ci, []).append((row, cs))
            for g in fgs:
                self.fg_readers[g].add(ci)
            self.comps[ci].fgroups |= fgs
        for ci, items in per_comp.items():
            comp = self.comps[ci]
            comp.rows = [r for r, _ in items]
            idx, mask = [], []
            for a, (_row, cs) in enumerate(items):
                m = cs >= 0
                mask.append(m)
                idx.append(a * comp.ncols + col_local[cs[m]])
            comp.jidx = np.concatenate(idx)
            jmask = np.concatenate(mask)
            comp.jmask = None if jmask.all() else jmask
            nr = len(comp.rows)
            comp.ja, comp.jc = np.divmod(comp.jidx, comp.ncols)
            comp.pe, comp.pf = _same_column_pairs(comp.jc, comp.ncols)
            comp.pidx = comp.ja[comp.pe] * nr + comp.ja[comp.pf]
            comp.pc = comp.jc[comp.pe]


def _same_column_pairs(jc: np.ndarray, ncols: int):
    """All ordered pairs ``(e, f)`` of COO entries with ``jc[e] == jc[f]``."""
    order = np.argsort(jc, kind="stable")
    cs = jc[order]
    k = np.bincount(jc, minlength=ncols)
    start = np.cumsum(k) - k
    reps = k[cs]                                   # partners per sorted entry
    pe = np.repeat(order, reps)
    first = np.repeat(np.cumsum(reps) - reps, reps)
    offs = np.arange(int(reps.sum()), dtype=np.intp) - first
    pf = order[np.repeat(start[cs], reps) + offs]
    return pe, pf


def _structure_key(sys: System) -> tuple:
    """Content key: catches appends AND in-place edits of aliases/fixes/rows."""
    return (len(sys.x), tuple(sys.aliases), tuple(sys.fixes),
            tuple(map(id, sys.rows)))


def _structure(sys: System) -> _Structure:
    """The cached structural analysis of *sys* (rebuilt when its content changes)."""
    st = sys._structure
    key = _structure_key(sys)
    if st is None or st.key != key:
        st = _Structure(sys)
        sys._structure = st
    return st


def _eval_vals(comp: _Component, x: np.ndarray):
    """Residuals ``F`` and the sparse Jacobian values (parallel to ``ja``/``jc``)."""
    F = np.empty(len(comp.rows))
    gs = []
    for a, row in enumerate(comp.rows):
        r, g = row.fn(x)
        F[a] = r
        gs.append(g)
    v = np.concatenate(gs).astype(float, copy=False)
    if comp.jmask is not None:
        v = v[comp.jmask]
    return F, v


def _eval_comp(comp: _Component, x: np.ndarray):
    """Residuals ``F`` and dense reduced Jacobian ``J`` (diagnostics only)."""
    F, v = _eval_vals(comp, x)
    nr = len(comp.rows)
    J = np.bincount(comp.jidx, weights=v,
                    minlength=nr * comp.ncols).reshape(nr, comp.ncols)
    return F, J


class NumpySolver:
    """The v1 ``SketchSolver`` (spec §7.1)."""

    def solve(self, sys: System, goals, weights, active=None) -> SolveResult:
        """Weighted min-change projection of *goals* onto ``F(x) = 0``.

        Args:
            sys: The system (current values in ``sys.x``).
            goals: Per-variable goal values (full space).
            weights: Per-variable goal weights (full space, each > 0).
            active: Full-space variable indices whose components are solved;
                ``None`` = all. A fixed group touched by *active*, or whose
                current value differs from its fix, is activated too, and so is
                every component with a row reading an activated fixed group.
                Everything else keeps its current values bit-for-bit.

        Returns:
            ``SolveResult``; ``converged`` is judged against ``LIN_TOL`` over the
            rows of solved components plus all-fixed rows reading an activated
            fixed group. Aliases hold exactly within solved components; fixes
            hold exactly wherever they changed. On failure the caller must not
            write back (D10 hold-last-good).

        Raises:
            ValueError: A weight is not > 0.
        """
        w_full = np.asarray(weights, dtype=float)
        if not np.all(w_full > 0):
            raise ValueError("solver weights must all be > 0")
        st = _structure(sys)
        x0 = np.asarray(sys.x, dtype=float)
        if st.conflicts:
            return SolveResult(x0.copy(), False, float("inf"))
        goals = np.asarray(goals, dtype=float)
        x = x0.copy()

        # -- activation ------------------------------------------------------
        if active is None:
            comp_ids = range(len(st.comps))
            x[st.fixed_vars] = st.fixed_vals
            checked = list(st.orphans)
        else:
            act = np.asarray(list(active), dtype=np.intp)
            fgs = {int(g) for g in st.var_fg[act] if g >= 0}
            stale = x0[st.fixed_vars] != st.fixed_vals
            if stale.any():
                fgs.update(int(g) for g in st.var_fg[st.fixed_vars[stale]])
            comp_set = {int(c) for c in st.var_comp[act] if c >= 0}
            checked = []
            for g in fgs:
                comp_set |= st.fg_readers[g]
                checked.extend(st.fg_orphans[g])
            for g in fgs.union(*(st.comps[c].fgroups for c in comp_set)):
                x[st.fg_members[g]] = st.fg_value[g]
            comp_ids = sorted(comp_set)

        # -- per-component projection (§7.2) ---------------------------------
        maxima: list[float] = []      # reduced with np.max: NaN must propagate
        for ci in comp_ids:
            comp = st.comps[ci]
            mv, lc, nc = comp.vars, comp.var_lcol, comp.ncols
            wm = w_full[mv]
            w = np.bincount(lc, weights=wm, minlength=nc)
            zg = np.bincount(lc, weights=wm * goals[mv], minlength=nc) / w
            z = zg.copy()                  # start from the goals
            x[mv] = z[lc]
            if not comp.rows:
                continue                   # rowless: exactly the weighted-mean goal
            winv = 1.0 / w
            nr = len(comp.rows)
            ja, jc = comp.ja, comp.jc
            tight = False
            for _ in range(MAX_ITERS):
                F, v = _eval_vals(comp, x)
                fmax = float(np.max(np.abs(F)))
                if fmax <= RES_STOP:
                    # F is AT the final x (this component's rows read only its
                    # own vars + fixes), so it is also the convergence check.
                    maxima.append(fmax)
                    tight = True
                    break
                g = zg - z
                A = np.bincount(comp.pidx, weights=v[comp.pe] * v[comp.pf] * winv[comp.pc],
                                minlength=nr * nr).reshape(nr, nr)      # J W^-1 J^T
                # relative Tikhonov: A scales with 1/weight, so an absolute term
                # would bias a W_PIN solve off-manifold by ~1e-6 x the offset
                # (an all-zero A — rows with no free gradient — gets 1.0 so the
                # step stays finite: dz = W^-1 J^T lam = 0 there)
                dmax = float(np.max(np.diag(A)))
                A[np.diag_indices_from(A)] += DAMPING_REL * dmax if dmax > 0 else 1.0
                rhs = -F - np.bincount(ja, weights=v * g[jc], minlength=nr)   # J g
                try:
                    lam = np.linalg.solve(A, rhs)
                except np.linalg.LinAlgError:
                    lam = np.linalg.lstsq(A, rhs, rcond=None)[0]
                dz = g + winv * np.bincount(jc, weights=v * lam[ja], minlength=nc)  # J^T lam
                if not np.all(np.isfinite(dz)):
                    break                  # diverged: final check reports failure
                z += dz
                x[mv] = z[lc]
                scale = max(1.0, float(np.max(np.abs(z))))
                if float(np.max(np.abs(dz))) < STEP_TOL * scale:
                    break
            if not tight:
                checked.extend(comp.rows)       # step-tol / cap / divergence: re-check at x
        if checked:
            maxima.extend(abs(float(row.fn(x)[0])) for row in checked)
        worst = float(np.max(maxima)) if maxima else 0.0
        converged = bool(np.isfinite(worst)) and worst <= LIN_TOL
        return SolveResult(x, converged, worst)

    def diagnose(self, sys: System) -> Diagnostics:
        """DOF = free variables after substitution - sum of component ranks (§7.4).

        Fixes are applied before evaluating J. ``conflicts`` lists the cids of
        contradictory fixes (the system is then not solvable).
        """
        st = _structure(sys)
        x = np.array(sys.x, dtype=float)
        x[st.fixed_vars] = st.fixed_vals
        rank = 0
        for comp in st.comps:
            if not comp.rows:
                continue
            _F, J = _eval_comp(comp, x)
            s = np.linalg.svd(J, compute_uv=False)
            tol = max(J.shape) * np.finfo(float).eps * (s[0] if s.size else 0.0)
            rank += int((s > max(tol, 1e-9)).sum())
        return Diagnostics(st.ncols, rank, st.ncols - rank, list(st.conflicts))


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
