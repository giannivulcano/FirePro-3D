"""Live-scene linetype authoring (linetypes.md LT4, H4-c / H4-d / H4-f).

Rows ⇄ the editor's axis Lines, the Weight row, the Repeat field edits, the
toggle-on setup and the ``push_undo_state`` pre-capture hook (Continuous
lock + grow-to-fit). The pure half is ``linetype_pattern``.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from . import linetype_pattern as lp

_TOL = lp._TOL


def _plain_lines(scene):
    """Editor Lines that can be pattern marks (never reference lines)."""
    from .geometry_2d import LineItem
    return [l for l in scene._draw_lines if type(l) is LineItem]


def axis_items(scene):
    """``[(line, role), ...]`` for the Lines the LT3-3 reading counts.

    Args:
        scene: The Block Editor ``Model_Space`` (origin at (0, 0), D4).

    Returns:
        Each counted Line with its ``linetype_render.axis_role``; empty when
        the scene is not a linetype.
    """
    from .linetype_render import axis_role
    rep = scene.block_repeat
    if rep is None:
        return []
    out = []
    for l in _plain_lines(scene):
        p1, p2 = l._pt1, l._pt2
        role = axis_role((p1.x(), p1.y()), (p2.x(), p2.y()), rep["length"])
        if role is not None:
            out.append((l, role))
    return out


def current_rows(scene):
    """The Pattern list for the live content, or None (unrepresentable)."""
    rep = scene.block_repeat
    if rep is None:
        return None
    dashes, dots = [], []
    for _, role in axis_items(scene):
        if role[0] == "dot":
            dots.append(role[1])
        else:
            dashes.append((role[1], role[2]))
    return lp.rows_from_reading(sorted(dashes), sorted(dots), rep["length"])


def _axis_end(lines) -> float:
    """``linetype_pattern.axis_end`` over live Lines (no per-Line dict)."""
    return lp.axis_end(((l._pt1.x(), l._pt1.y()), (l._pt2.x(), l._pt2.y()))
                       for l in lines)


def _set_line(line, a: float, b: float) -> None:
    """Move / resize an axis Line in place (same item, uid and style)."""
    line.prepareGeometryChange()
    line._pt1, line._pt2 = QPointF(a, 0.0), QPointF(b, 0.0)
    line.setLine(a, 0.0, b, 0.0)


def pattern_weight(scene):
    """The dashes' shared weight, or None when mixed / no dash (LT4-3)."""
    ws = {l.style["weight"] for l, r in axis_items(scene) if r[0] == "dash"}
    return ws.pop() if len(ws) == 1 else None


def _new_mark(scene, a: float, b: float, weight):
    """Create an axis mark through the editor's add path (Continuous)."""
    from . import stroke_style as ss
    from .geometry_2d import LineItem
    it = LineItem(QPointF(a, 0.0), QPointF(b, 0.0))
    it.style["linetype"] = ss.CONTINUOUS
    if weight:
        it.style["weight"] = weight
    it._sync_stroke_pen()
    scene._tile_editor._add_primitive(it)
    return it


def apply_pattern_rows(scene, rows, *, push_undo: bool = True) -> bool:
    """Rewrite the axis Lines to *rows* (LT4-2 ripple, LT4-8 in place).

    Matches existing marks to the new spans in x order per kind, moves /
    resizes matches in place (uid, style, constraints kept), deletes extras
    with their constraints, creates the rest (Continuous, the dash weight)
    and sets Length = period. One undo step.

    Args:
        scene: The linetype Block Editor scene.
        rows: ``[(kind, mm), ...]`` (Dash / Gap / Dot).
        push_undo: Push the one step (False inside a composite edit whose
            caller pushes, e.g. :func:`begin_linetype`).

    Returns:
        False (nothing changed, no undo step) when *rows* fail
        ``validate_rows``, equal the live ``current_rows``, the scene is not
        a linetype, or a new mark is needed but the scene has no owning Block
        Editor to add it through; True otherwise.
    """
    rows = [(str(k), float(n)) for k, n in rows]
    if scene.block_repeat is None or not lp.validate_rows(rows):
        return False
    cur = current_rows(scene)
    if (cur is not None and len(cur) == len(rows)
            and all(a[0] == b[0] and abs(a[1] - b[1]) <= _TOL
                    for a, b in zip(cur, rows))):
        return False                             # re-committed rows: no step
    weight = pattern_weight(scene)
    sp, period = lp.spans(rows)
    have = {"dash": [], "dot": []}
    for line, role in sorted(axis_items(scene),
                             key=lambda lr: min(lr[0]._pt1.x(), lr[0]._pt2.x())):
        have[role[0]].append(line)
    want = {"dash": [s for s in sp if s[0] == "dash"],
            "dot": [s for s in sp if s[0] == "dot"]}
    if (getattr(scene, "_tile_editor", None) is None
            and any(len(want[k]) > len(have[k]) for k in want)):
        return False                             # checked before any mutation
    removed, moved = [], []
    for kind in ("dash", "dot"):
        lines, targets = have[kind], want[kind]
        for line, (_, a, b) in zip(lines, targets):
            _set_line(line, a, b)
            moved.append(line)
        for line in lines[len(targets):]:
            scene._remove_item_from_lists(line)
            removed.append(line)
        for _, a, b in targets[len(lines):]:
            _new_mark(scene, a, b, weight)
    ctl = scene.constraint_ctl
    if removed:
        ctl.on_items_removed(removed)
    # LT4-8: a constraint the ripple violates shows red live, exactly as an
    # undo / redo restore would derive it (D38).
    touched = {c.id: c for line in moved for c in ctl.constraints_on(line)}
    if touched:
        ctl.mark_unsatisfied_red(list(touched.values()))
    rep = scene.block_repeat
    rep["length"] = period
    scene.set_block_capability(("repeat", rep), push_undo=False)
    if push_undo:
        scene.push_undo_state()
        scene.notify_geometry_edited()
    return True


def set_pattern_weight(scene, weight: str) -> None:
    """LT4-3: stamp *weight* on every axis dash (one undo step; none if no-op)."""
    changed = False
    for line, role in axis_items(scene):
        if role[0] == "dash" and line.style["weight"] != weight:
            line.style["weight"] = weight
            line._sync_stroke_pen()
            line.update()
            changed = True
    if changed:
        scene.push_undo_state()


def set_repeat_field(scene, key: str, value) -> None:
    """Length (≥ content end, else reverts -- LT4-9) / Size edits; one step."""
    rep = scene.block_repeat
    if rep is None:
        return
    if key == "Length":
        mm = float(value)
        end = _axis_end(_plain_lines(scene))
        if not mm > 0 or mm < end - _TOL or abs(mm - rep["length"]) <= _TOL:
            return                               # panel refresh shows the old value
        rep["length"] = mm
    elif key == "Size":
        size = "model" if str(value) == "Model" else "drafting"
        if size == rep["size"]:
            return
        rep["size"] = size
    else:
        return
    scene.set_block_capability(("repeat", rep))


def _non_continuous(scene):
    """Styled primitives whose linetype is not Continuous (LT4-4)."""
    from . import stroke_style as ss
    tools = getattr(scene, "_tools", None)
    items = tools._all_geometry_items() if tools is not None else []
    return [it for it in items
            if isinstance(getattr(it, "style", None), dict)
            and it.style.get("linetype") != ss.CONTINUOUS]


def _force_continuous(items) -> None:
    from . import stroke_style as ss
    for it in items:
        it.prepareGeometryChange()               # a missing badge may vanish
        it.style["linetype"] = ss.CONTINUOUS
        it._sync_stroke_pen()
        it.update()


def begin_linetype(scene, seed_length: float) -> int:
    """Toggle-on body (LT4-4 / LT4-6) -- the caller pushes the one step.

    Converts non-Continuous primitives, sets the repeat capability (Length =
    *seed_length*, Size Drafting) and seeds Dash 6 / Gap 3 into an empty unit.

    Returns:
        The number of primitives converted to Continuous.
    """
    bad = _non_continuous(scene)
    _force_continuous(bad)
    scene.set_block_capability(
        ("repeat", {"length": max(seed_length, 0.1), "size": "drafting"}),
        push_undo=False)
    if not axis_items(scene):
        apply_pattern_rows(scene, list(lp.SEED_ROWS), push_undo=False)
    return len(bad)


def pre_capture(scene) -> None:
    """``push_undo_state`` hook for a linetype editor (H4-a / H4-d).

    Forces Continuous on every styled primitive and grows Length to the
    content end, so the commit and both effects are one snapshot. Never
    pushes (``set_block_capability(..., push_undo=False)``), so it cannot
    recurse.
    """
    rep = scene.block_repeat
    if rep is None:
        return
    _force_continuous(_non_continuous(scene))
    end = _axis_end(_plain_lines(scene))
    if end > rep["length"] + _TOL:
        rep["length"] = end
        scene.set_block_capability(("repeat", rep), push_undo=False)


def preview_painter(scene):
    """Build the panel swatch painter (LT4-7): a straight sample and an L
    polyline through the real renderer (preview ≡ render).

    Args:
        scene: The linetype Block Editor ``Model_Space``; its capability
            frame's scratch definition is read at paint time.

    Returns:
        ``paint(painter, rect)`` -- draws inside *rect* (QRectF, widget px);
        draws nothing when the scene has no readable linetype.
    """
    def paint(painter, rect):
        from PyQt6.QtGui import QColor, QPen
        from . import theme as th
        from . import stroke_style as ss
        from .constants import PATTERN_PREVIEW_PERIODS
        from .linetype_render import LinetypeDef, draw_expansion, expand
        from .path_walk import Seg
        f = scene.capability_frame_item()
        d = f.scratch_definition() if f is not None else None
        lt = LinetypeDef.from_block(d) if d is not None else None
        if lt is None:
            return
        m = 8.0
        x0, x1 = rect.left() + m, rect.right() - m
        y0, y1 = rect.top() + m, rect.bottom() - m
        s = (x1 - x0) / (PATTERN_PREVIEW_PERIODS * lt.period)     # px per mm
        pieces = (Seg(x0, y0, x1, y0), Seg(x0, y0 + 10.0, x0, y1),
                  Seg(x0, y1, x1, y1))
        dash, dot = expand(pieces, lt, s, (rect.left(), rect.top()))
        # By Linetype draws the dash weight, else the Model Blocks weight --
        # stroke_style.canvas_px owns name -> mm -> px (LT1-7, Thin Lines).
        pen = QPen(QColor(th.detect().ink),
                   ss.canvas_px(lt.dash_weight or ss.BY_LINETYPE))
        pen.setCosmetic(True)
        painter.save()
        try:
            draw_expansion(painter, dash, dot, pen)
        finally:
            painter.restore()
    return paint
