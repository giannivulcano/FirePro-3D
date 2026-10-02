"""D18 perf bars against the REAL solver (spec §9) — run standalone: -m perf."""
import math
import time

import numpy as np
import pytest

from firepro3d import sketch_solver as ss

pytestmark = pytest.mark.perf


def _dist_row(cid, ia, ib, length):
    def fn(x):
        dx, dy = x[ib] - x[ia], x[ib + 1] - x[ia + 1]
        L = math.hypot(dx, dy) or 1e-12
        return L - length, np.array([-dx / L, -dy / L, dx / L, dy / L])
    return ss.Row(cid, (ia, ia + 1, ib, ib + 1), fn)


def _bench(n_lines=200, chain=200):
    """200 lines / 300 constraints: Horizontal on every 4th line, Coincident
    p2_i == p1_{i+1} inside each chain (aliases on raw vars), lengths on the
    rest. ``chain=200`` = one worst-case component; ``chain=5`` = realistic."""
    rng = np.random.default_rng(7)
    pts = []
    for i in range(n_lines):
        if i % chain == 0:
            p = np.array([i * 20.0, 0.0])
        pts.append(p.copy())
        ang = 0.0 if i % 4 == 0 else rng.uniform(-1.0, 1.0)
        p = p + 30.0 * np.array([math.cos(ang), -math.sin(ang)])
        pts.append(p.copy())
    x = np.array(pts).reshape(-1)
    s = ss.System(x=x)
    n_con = 0
    for i in range(n_lines):
        a, b = 4 * i, 4 * i + 2
        if i % 4 == 0:
            ss.build_horizontal(f"h{i}", (ss.raw_point(a, a + 1), ss.raw_point(b, b + 1)), s)
            n_con += 1
        if (i + 1) % chain and i + 1 < n_lines:
            s.aliases += [(b, 4 * (i + 1), f"c{i}"), (b + 1, 4 * (i + 1) + 1, f"c{i}")]
            n_con += 1
    i = 0
    while n_con < 300:
        if i % 4:
            a, b = 4 * i, 4 * i + 2
            s.rows.append(_dist_row(f"d{i}", a, b, float(np.hypot(*(x[b:b + 2] - x[a:a + 2])))))
            n_con += 1
        i += 1
    return s


def _median_ms(fn, n=15):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1e3)
    return sorted(ts)[len(ts) // 2]


@pytest.mark.parametrize("chain", [200, 5], ids=["worst_one_component", "realistic"])
def test_d18_bars(chain):
    s = _bench(chain=chain)
    solver = ss.NumpySolver()
    # Drag a free variable of the LARGEST row-bearing component (VC2: the
    # bench's trailing lines carry no rows, so ``len(x) - 1`` would be trivial).
    st = ss._structure(s)
    big = max(st.comps, key=lambda c: len(c.rows))
    last = int(big.vars[0])
    goals = s.x.copy(); goals[last] += 5.0
    w = np.ones_like(goals); w[last] = ss.W_PIN
    drag = _median_ms(lambda: solver.solve(s, goals, w, active=[last]))
    commit = _median_ms(lambda: (solver.solve(s, goals, w), solver.diagnose(s)))
    open_ = _median_ms(lambda: (_bench(chain=chain), solver.solve(s, s.x.copy(), np.ones_like(s.x)),
                                solver.diagnose(s)), n=5)
    print(f"[chain={chain}] drag={drag:.2f} ms commit={commit:.2f} ms open={open_:.2f} ms")
    assert solver.solve(s, goals, w).converged
    assert solver.solve(s, s.x.copy(), np.ones_like(s.x)).max_residual <= 1e-6, "bench must start satisfied"
    assert drag <= 8.0, f"drag {drag:.2f} ms"
    assert commit <= 50.0, f"commit {commit:.2f} ms"
    assert open_ <= 200.0, f"open {open_:.2f} ms"
