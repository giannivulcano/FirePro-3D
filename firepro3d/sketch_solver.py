"""Pure numpy sketch solver — parametric-constraint-system.md §7 (B1).

Weighted minimum-change projection (constraints hard, goals soft) with damped
Gauss-Newton steps, equality substitution (aliases + fixes) BEFORE solving,
union-find component partitioning, and SVD diagnostics. No Qt.
"""
from __future__ import annotations

import contextlib
import ctypes
import glob
import os
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
DEP_TOL = 1e-8          # ordered Gram-Schmidt: a row is dependent below this relative norm (CS2 §7.4)
NULL_TOL = 1e-8         # a variable "moves" in a null-space direction above this
# D18 (ruling 2026-10-03): a component whose Gram matrix J Jᵀ has
# λ_min ≥ max(CERT_RATIO·λ_max, 1e-12) is certified full row rank
# (cond(J) ≤ 1e3, σ_min ≥ 1e-6 -- far above the SVD rank cut-off), and its
# row-space basis Q = Λ^-½ Vᵀ J is orthonormal to ~2e-10 (≪ NULL_TOL); any
# other component takes the economy SVD + ordered Gram-Schmidt path.
CERT_RATIO = 1e-6

# D18 (2026-10-03 P4): OpenBLAS defaults to one thread per core; on the
# solver's ~300-sized dense LAPACK calls that oversubscription costs 3-13x
# (16-thread host: SVD 138 ms vs 49 ms single-threaded). Solves and
# diagnostics drop to one BLAS thread for their duration (global OpenBLAS
# setting, restored on exit; a numpy build without the API is a no-op).
_BLAS = None            # (get, set) ctypes functions; False = unavailable
_blas_depth = 0


def _blas_api():
    """The bundled OpenBLAS ``(get_num_threads, set_num_threads)``, or False."""
    global _BLAS
    if _BLAS is None:
        _BLAS = False
        base = os.path.dirname(np.__file__)
        dirs = (os.path.join(base, os.pardir, "numpy.libs"), os.path.join(base, ".dylibs"))
        try:
            for d in dirs:
                for path in glob.glob(os.path.join(d, "*openblas*")):
                    lib = ctypes.CDLL(path)
                    for pre in ("scipy_openblas", "openblas"):
                        for suf in ("64_", ""):
                            get = getattr(lib, f"{pre}_get_num_threads{suf}", None)
                            put = getattr(lib, f"{pre}_set_num_threads{suf}", None)
                            if get is not None and put is not None:
                                get.restype, get.argtypes = ctypes.c_int, []
                                put.restype, put.argtypes = None, [ctypes.c_int]
                                _BLAS = (get, put)
                                return _BLAS
        except OSError:
            _BLAS = False
    return _BLAS


@contextlib.contextmanager
def one_blas_thread():
    """Run the body with OpenBLAS at one thread; re-entrant; restores on exit."""
    global _blas_depth
    api = _blas_api() if _blas_depth == 0 else None
    prev = api[0]() if api else 1
    if prev != 1:
        api[1](1)
    _blas_depth += 1
    try:
        yield
    finally:
        _blas_depth -= 1
        if prev != 1:
            api[1](prev)


@dataclass(frozen=True)
class PointExpr:
    """A handle point as a function of the variable vector (§5.1).

    Exactly one form: ``const`` (a ground), ``raw`` (the point IS two variables
    — substitutable), or ``idx`` + ``fn`` (derived;
    ``fn(x[list(idx)]) -> (p[2], dp[2, len(idx)])``). A derived point may
    also carry ``fam`` = ``(name, params)``, naming a registered batched point
    family (:func:`register_point_family`) that computes the same point for
    many rows at once (D18); ``fn`` stays the per-point reference.
    """
    idx: tuple = ()
    fn: Callable | None = None
    raw: tuple | None = None
    const: tuple | None = None
    fam: tuple | None = None      # (family name, params): batched form of ``fn`` (D18)

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


POINT_FAMILIES: dict = {}


def register_point_family(name: str, fn: Callable) -> None:
    """Register a batched point family: ``fn(V (k, m), P (k, p)) ->
    (pts (k, 2), dp (k, 2, m))`` -- row i equals the matching
    ``PointExpr.fn(V[i])`` (parity-tested)."""
    POINT_FAMILIES[name] = fn


def _raw_batch(V, _P):
    return V, np.broadcast_to(np.eye(2), (len(V), 2, 2))


@dataclass
class Row:
    """One residual: ``fn(x) -> (r, grad)``; ``grad`` follows ``deps``."""
    cid: str
    deps: tuple
    fn: Callable
    spec: tuple | None = None     # ("axis", axis, a, b): batchable form (D18)


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
    cid_rank: dict = field(default_factory=dict)  # cid -> admission order (§7.4 attribution)
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
    redundant: list = field(default_factory=list)   # cids implied by earlier ones (§7.4, amber)
    _st: object = field(default=None, repr=False, compare=False)
    _rowb: dict = field(default_factory=dict, repr=False, compare=False)
    _fast: set = field(default_factory=set, repr=False, compare=False)  # certified comps (D18)

    def dof_of(self, idx) -> int:
        """DOF left among full-space variables *idx* (§7.4 per-entity); see
        :meth:`dof_of_many`."""
        return self.dof_of_many([idx])[0]

    def dof_of_many(self, groups) -> list:
        """Per-entity DOF for each index group, batched (D18).

        A fixed variable contributes 0. Per component, with ``Q`` the
        orthonormal row-space basis of J (economy SVD or the certified eigh
        basis -- 2026-10-02 P4 ruling: never the full null-space basis), the
        DOF of columns S is ``rank(I - Q_S^T Q_S)``, the null-space projection
        restricted to S. A rowless component's columns are each free (1).
        Blocks of equal size share one stacked ``eigvalsh`` call.
        """
        st = self._st
        out = [0] * len(groups)
        if st is None:
            return out
        blocks: dict[int, list] = {}            # block size -> [(group k, Q_S)]
        for k, idx in enumerate(groups):
            by_comp: dict[int, set] = {}
            for i in idx:
                i = int(i)
                if st.var_col[i] < 0:
                    continue
                by_comp.setdefault(int(st.var_comp[i]), set()).add(int(st.var_lcol[i]))
            for ci, lcs in by_comp.items():
                Q = self._rowb.get(ci)
                cols = sorted(lcs)
                if Q is None:
                    out[k] += len(cols)
                else:
                    blocks.setdefault(len(cols), []).append((k, Q[:, cols]))
        for m, items in blocks.items():
            M = np.stack([np.eye(m) - q.T @ q for _k, q in items])
            ev = np.linalg.eigvalsh(M)
            for (k, _q), cnt in zip(items, (ev > NULL_TOL).sum(axis=1)):
                out[k] += int(cnt)
        return out


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
                 "ja", "jc", "pe", "pf", "pidx", "pc", "batch")

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
        self.batch = None       # _RowBatch, built on first eval (lives with the cached structure)


class _RowBatch:
    """Vectorised residuals + gradient values of one component's rows (D18).

    Axis rows (``Row.spec == ("axis", axis, a, b)``) whose ends are raw,
    const or a registered point family are evaluated one numpy call per
    family; every other row falls back to its own ``fn``. The output order
    equals the per-row concatenation (``_eval_vals`` contract).
    """
    __slots__ = ("nr", "total", "F0", "groups", "generic")

    def __init__(self, rows):
        nr = len(rows)
        lens = np.array([len(r.deps) for r in rows], dtype=np.intp)
        offs = np.concatenate(([0], np.cumsum(lens)))
        self.nr, self.total = nr, int(offs[-1])
        self.F0 = np.zeros(nr)
        self.generic = []
        acc: dict = {}
        for a, row in enumerate(rows):
            ends = _batch_ends(row)
            if ends is None:
                self.generic.append((a, row, int(offs[a])))
                continue
            axis, pa, pb = ends
            pos = {d: k for k, d in enumerate(row.deps)}
            for sign, p in ((-1.0, pa), (1.0, pb)):
                if p.const is not None:
                    self.F0[a] += sign * p.const[axis]
                    continue
                name, par = ("raw", ()) if p.raw is not None else p.fam
                g = acc.setdefault((name, len(p.deps)), ([], [], [], [], [], []))
                g[0].append(p.deps)
                g[1].append(par)
                g[2].append(a)
                g[3].append(sign)
                g[4].append(axis)
                g[5].append([int(offs[a]) + pos[d] for d in p.deps])
        self.groups = []
        for (name, _m), (idx, par, ra, sg, ax, tg) in acc.items():
            fn = _raw_batch if name == "raw" else POINT_FAMILIES[name]
            k = len(idx)
            self.groups.append((fn, np.array(idx, dtype=np.intp),
                                np.array(par, dtype=float).reshape(k, -1),
                                np.array(ra, dtype=np.intp), np.array(sg),
                                np.array(ax, dtype=np.intp), np.array(tg, dtype=np.intp),
                                np.arange(k)))

    def eval(self, x):
        """``(F, v)``: residuals and the unmasked concatenated gradients."""
        nr, total = self.nr, self.total
        F = self.F0.copy()
        v = np.zeros(total)
        for fn, idx, par, ra, sg, ax, tg, k in self.groups:
            pts, dp = fn(x[idx], par)
            F += np.bincount(ra, weights=sg * pts[k, ax], minlength=nr)
            v += np.bincount(tg.ravel(), weights=(sg[:, None] * dp[k, ax, :]).ravel(),
                             minlength=total)
        for a, row, off in self.generic:
            r, g = row.fn(x)
            F[a] = r
            v[off:off + len(g)] = g
        return F, v


def _batch_ends(row):
    """``(axis, a, b)`` when *row* is a batchable axis row, else None."""
    spec = row.spec
    if not spec or spec[0] != "axis":
        return None
    _kind, axis, pa, pb = spec
    for p in (pa, pb):
        if p.const is None and p.raw is None and (
                p.fam is None or p.fam[0] not in POINT_FAMILIES):
            return None
    return axis, pa, pb


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
        self.var_lcol = np.full(n, -1, dtype=np.intp)   # full-space var -> local column
        for ci, comp in enumerate(self.comps):
            mv = free_vars[var_comp[free_vars] == ci]
            comp.vars = mv
            comp.var_lcol = col_local[var_col[mv]]
            self.var_lcol[mv] = comp.var_lcol
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
    """Residuals ``F`` and the sparse Jacobian values (parallel to ``ja``/``jc``),
    batched per point family (D18; generic rows use their own ``fn``)."""
    if comp.batch is None:
        comp.batch = _RowBatch(comp.rows)
    F, v = comp.batch.eval(x)
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


def _equality_redundancy(sys: System) -> dict:
    """``cid -> bool``: whether ALL of a cid's aliases / fixes were already
    implied when it arrived, in ``cid_rank`` order (§7.4, D38 attribution).
    A contradiction is not redundant (it is a conflict)."""
    order = sys.cid_rank or {}
    big = len(order)
    ev = [(order.get(c, big), 0, k, i, j, None, c) for k, (i, j, c) in enumerate(sys.aliases)]
    ev += [(order.get(c, big), 1, k, i, None, v, c) for k, (i, v, c) in enumerate(sys.fixes)]
    ev.sort(key=lambda e: e[:3])
    uf = _UF(len(sys.x))
    val: dict[int, float] = {}
    out: dict[str, bool] = {}
    for _o, kind, _k, i, j, v, cid in ev:
        if kind == 0:
            ri, rj = uf.find(i), uf.find(j)
            if ri == rj:
                red = True
            else:
                vi, vj = val.pop(ri, None), val.pop(rj, None)
                red = vi is not None and vj is not None and abs(vi - vj) <= LIN_TOL
                uf.union(ri, rj)
                keep = vi if vi is not None else vj
                if keep is not None:
                    val[uf.find(ri)] = keep
        else:
            r = uf.find(i)
            red = r in val and abs(val[r] - float(v)) <= LIN_TOL
            val.setdefault(r, float(v))
        out[cid] = out.get(cid, True) and red
    return out


def _dependent_rows(J: np.ndarray, ndep: int | None = None) -> np.ndarray:
    """Ordered modified Gram-Schmidt: ``dep[a]`` = row *a* lies in the span of
    the rows before it (relative ``DEP_TOL``); re-orthogonalised twice. Run
    only on a rank-deficient component (P4: ~45 ms on a 299 x 900 J).

    *ndep* (= rows - SVD rank) reconciles the two tolerances on a
    near-singular J (CS2 review m2): when the relative test flags a different
    count, the *ndep* rows with the smallest relative residual are dependent.
    """
    nr, nc = J.shape
    B = np.empty((nr, nc))
    k = 0
    dep = np.zeros(nr, dtype=bool)
    ratio = np.zeros(nr)
    for a in range(nr):
        v = J[a].astype(float).copy()
        n0 = float(np.linalg.norm(v))
        if n0 <= 1e-12:
            dep[a] = True
            continue
        if k:
            Bk = B[:k]
            v -= Bk.T @ (Bk @ v)
            v -= Bk.T @ (Bk @ v)
        r = float(np.linalg.norm(v))
        ratio[a] = r / n0
        if r <= DEP_TOL * n0:
            dep[a] = True
        else:
            B[k] = v / r
            k += 1
    if ndep is not None and int(dep.sum()) != ndep:
        dep = np.zeros(nr, dtype=bool)
        if ndep > 0:
            dep[np.argsort(ratio, kind="stable")[:ndep]] = True
    return dep


def _certified_row_basis(J: np.ndarray):
    """Orthonormal row-space basis of a certified full-row-rank *J*, else None
    (see ``CERT_RATIO``)."""
    nr, nc = J.shape
    if nr == 0 or nr > nc:
        return None
    lam, V = np.linalg.eigh(J @ J.T)
    if not (np.all(np.isfinite(lam)) and lam[0] >= max(CERT_RATIO * lam[-1], 1e-12)):
        return None
    return (V.T @ J) / np.sqrt(lam)[:, None]


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
        with one_blas_thread():
            return self._solve(sys, goals, weights, active)

    def _solve(self, sys: System, goals, weights, active) -> SolveResult:
        """Body of :meth:`solve` (run under :func:`one_blas_thread`)."""
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
        recheck: list = []            # components that stopped without the tight check
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
                recheck.append(comp)
        for comp in recheck:                 # step-tol / cap / divergence: re-check at x
            maxima.append(float(np.max(np.abs(_eval_vals(comp, x)[0]))))
        if checked:
            maxima.extend(abs(float(row.fn(x)[0])) for row in checked)
        worst = float(np.max(maxima)) if maxima else 0.0
        converged = bool(np.isfinite(worst)) and worst <= LIN_TOL
        return SolveResult(x, converged, worst)

    def diagnose(self, sys: System) -> Diagnostics:
        """DOF = free variables after substitution - sum of component ranks,
        plus redundancy attribution and row-space bases (§7.4).

        Fixes are applied before evaluating J. ``conflicts`` lists the cids of
        contradictory fixes. ``redundant`` lists, in ``sys.cid_rank`` order,
        every cid whose equalities were all already implied and whose rows
        are all dependent on earlier rows (and satisfied). Equalities are
        attributed before rows (they are substituted first).
        """
        with one_blas_thread():
            return self._diagnose(sys)

    def _diagnose(self, sys: System) -> Diagnostics:
        """Body of :meth:`diagnose` (run under :func:`one_blas_thread`)."""
        st = _structure(sys)
        x = np.array(sys.x, dtype=float)
        x[st.fixed_vars] = st.fixed_vals
        rank = 0
        rowb: dict[int, np.ndarray] = {}
        row_dep: dict[str, bool] = {}
        fast: set = set()
        for ci, comp in enumerate(st.comps):
            if not comp.rows:
                continue
            F, J = _eval_comp(comp, x)
            nr = len(comp.rows)
            Q = _certified_row_basis(J)
            if Q is not None:                                    # D18 full-rank path
                r, dep = nr, np.zeros(nr, dtype=bool)
                fast.add(ci)
            else:
                _u, s, vt = np.linalg.svd(J, full_matrices=False)   # economy (P4)
                tol = max(J.shape) * np.finfo(float).eps * (s[0] if s.size else 0.0)
                r = int((s > max(tol, 1e-9)).sum())
                Q = vt[:r]
                dep = (_dependent_rows(J, nr - r) if r < nr
                       else np.zeros(nr, dtype=bool))
            rank += r
            rowb[ci] = Q
            for k, row in enumerate(comp.rows):
                ok = bool(dep[k]) and abs(float(F[k])) <= LIN_TOL
                row_dep[row.cid] = row_dep.get(row.cid, True) and ok
        for row in st.orphans:                       # every dependency fixed
            ok = abs(float(row.fn(x)[0])) <= LIN_TOL
            row_dep[row.cid] = row_dep.get(row.cid, True) and ok
        eq = _equality_redundancy(sys)
        order = sys.cid_rank or {}
        red = sorted((c for c in set(eq) | set(row_dep)
                      if eq.get(c, True) and row_dep.get(c, True)),
                     key=lambda c: order.get(c, len(order)))
        return Diagnostics(st.ncols, rank, st.ncols - rank, list(st.conflicts),
                           red, st, rowb, _fast=fast)


# ── §7.3 residual catalogue — builders (one per IMPLEMENTED type) ─────────

def _axis_equal(axis: int, cid: str, ends, sys: System) -> None:
    """H (``axis`` 1, y) / V (``axis`` 0, x) on ``ends`` = (a, b) PointExprs.

    Raw/raw -> alias the axis variables; raw/const (origin) -> fix it;
    otherwise a row ``b[axis] - a[axis]``.
    """
    a, b = ends
    if a.raw is not None and b.raw is not None:
        sys.aliases.append((a.raw[axis], b.raw[axis], cid))
        return
    if a.const is not None and b.raw is not None:
        sys.fixes.append((b.raw[axis], float(a.const[axis]), cid))
        return
    if b.const is not None and a.raw is not None:
        sys.fixes.append((a.raw[axis], float(b.const[axis]), cid))
        return
    deps = tuple(dict.fromkeys(a.deps + b.deps))
    pos = {d: k for k, d in enumerate(deps)}

    def fn(x):
        pa, da = a.eval(x)
        pb, db = b.eval(x)
        g = np.zeros(len(deps))
        for c, d in enumerate(a.deps):
            g[pos[d]] -= da[axis, c]
        for c, d in enumerate(b.deps):
            g[pos[d]] += db[axis, c]
        return float(pb[axis] - pa[axis]), g

    sys.rows.append(Row(cid, deps, fn, spec=("axis", axis, a, b)))


def build_horizontal(cid: str, ends, sys: System) -> None:
    """Horizontal (pinned 2026-10-01): equal Y (``_axis_equal`` axis 1)."""
    _axis_equal(1, cid, ends, sys)


def build_vertical(cid: str, ends, sys: System) -> None:
    """Vertical (pinned 2026-10-02, CS2): equal X (``_axis_equal`` axis 0);
    with the origin the point lies on the Y axis (``x := 0``)."""
    _axis_equal(0, cid, ends, sys)


BUILDERS = {"horizontal": build_horizontal, "vertical": build_vertical}
