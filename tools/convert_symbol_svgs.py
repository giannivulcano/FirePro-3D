"""One-off: convert the five plan-symbol SVGs into System symbol blocks (SB4g R1 / D9).

Not shipped (lives in tools/, outside the firepro3d package). Reproduces the scene
geometry the SVG items draw today exactly:

    scene = (v - 10) * K      (v = viewBox units after the SVG's own transforms)

The viewBox is 0 0 20 20 for all five, and today's item maps that box onto
[-TARGET/2, TARGET/2] (probe 2026-11-12: QGraphicsSvgItem.boundingRect 70x70 ->
sceneBoundingRect (-304.8, -304.8, 609.6, 609.6) for the heads and the water supply,
(-75, -75, 150, 150) for the riser). Both the SVG and block-local space are Qt Y-down,
so no Y flip. Strokes become By Linetype centre lines (SB4g R14): the SVG's
stroke-width is not carried, so the outer edge sits half the old stroke inside.

Usage (repo root):
    python tools/convert_symbol_svgs.py            # write firepro3d/system_blocks/Symbols/*.fpdb
    python tools/convert_symbol_svgs.py --out DIR  # write raw records to DIR instead (dry run)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GRAPHICS = os.path.join(ROOT, "firepro3d", "graphics")
HEAD_MM = 24.0 * 25.4          # sprinkler.py / water_supply.py TARGET_MM (609.6)
RISER_MM = 150.0               # constants.RISER_SYMBOL_SIZE_MM
VIEWBOX = 20.0                 # every source SVG: viewBox="0 0 20 20"

# (file under graphics/, block name, id, symbol_for, target size in mm)
SOURCES = [
    ("sprinkler_graphics/sprinkler0.svg", "Sprinkler0", "system-symbols-sprinkler0", "Sprinkler", HEAD_MM),
    ("sprinkler_graphics/sprinkler1.svg", "Sprinkler1", "system-symbols-sprinkler1", "Sprinkler", HEAD_MM),
    ("sprinkler_graphics/sprinkler2.svg", "Sprinkler2", "system-symbols-sprinkler2", "Sprinkler", HEAD_MM),
    ("sprinkler_graphics/water_supply.svg", "Water Supply", "system-symbols-watersupply", "Water Supply", HEAD_MM),
    ("fitting_symbols/riser_passthrough.svg", "Riser", "system-symbols-riser", "Riser", RISER_MM),
]

_SVG = "{http://www.w3.org/2000/svg}"
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_TOKEN = re.compile(rf"[MmLlHhVvCcZz]|{_NUM}")

# -- affine helpers: (a, b, c, d, e, f) maps (x, y) -> (a x + c y + e, b x + d y + f)
IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(p, q):
    """p after q (apply q first)."""
    a1, b1, c1, d1, e1, f1 = p
    a2, b2, c2, d2, e2, f2 = q
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _parse_transform(text):
    m = IDENT
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in re.findall(_NUM, args)]
        if name == "translate":
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "matrix":
            t = tuple(v)
        elif name == "scale":
            t = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        else:
            raise ValueError(f"unsupported transform {name}")
        m = _mul(m, t)
    return m


def _style(el, inherited):
    st = dict(inherited)
    for k in ("fill", "stroke", "stroke-width", "fill-opacity"):
        if el.get(k) is not None:
            st[k] = el.get(k)
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            st[k.strip()] = v.strip()
    return st


def _colour(v):
    v = (v or "none").strip().lower()
    return None if v in ("none", "") else v


# -- path data -> subpaths of segments ("L", p0, p1) / ("C", p0, c1, c2, p3)
def parse_path(d):
    toks = _TOKEN.findall(d or "")
    i, cmd = 0, None
    cur = start = (0.0, 0.0)
    subs, segs, closed = [], [], False

    def flush():
        nonlocal segs, closed
        if segs:
            subs.append({"segs": segs, "closed": closed})
        segs, closed = [], False

    def num():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    while i < len(toks):
        if re.fullmatch(r"[A-Za-z]", toks[i]):
            cmd = toks[i]; i += 1
        rel = cmd.islower()
        c = cmd.upper()
        if c == "Z":
            if math.dist(cur, start) > 1e-9:
                segs.append(("L", cur, start))
            closed = True
            cur = start
            flush()
            continue
        if c == "M":
            x, y = num(), num()
            p = (cur[0] + x, cur[1] + y) if rel else (x, y)
            flush()
            cur = start = p
            cmd = "l" if rel else "L"          # implicit lineto after moveto
        elif c == "L":
            x, y = num(), num()
            p = (cur[0] + x, cur[1] + y) if rel else (x, y)
            if math.dist(cur, p) > 1e-9:
                segs.append(("L", cur, p))
            cur = p
        elif c in "HV":
            v = num()
            if c == "H":
                p = (cur[0] + v if rel else v, cur[1])
            else:
                p = (cur[0], cur[1] + v if rel else v)
            if math.dist(cur, p) > 1e-9:
                segs.append(("L", cur, p))
            cur = p
        elif c == "C":
            pts = [(num(), num()) for _ in range(3)]
            if rel:
                pts = [(cur[0] + x, cur[1] + y) for x, y in pts]
            segs.append(("C", cur, *pts))
            cur = pts[2]
        else:
            raise ValueError(f"unsupported path command {cmd}")
    flush()
    return subs


def _area(segs):
    """Shoelace area of a subpath's control polygon: 0 for a run of collinear
    lines (sprinkler0's X), which the SVG fills with nothing."""
    pts = [segs[0][1]]
    for s in segs:
        pts += list(s[2:])          # L: end point; C: c1, c2, end point
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2.0


class Converter:
    def __init__(self, block_id, k):
        self.block_id, self.k = block_id, k
        self.prims = []

    def uid(self, tag):
        # Deterministic: a re-run rewrites byte-identical files.
        return uuid.uuid5(uuid.NAMESPACE_URL, f"firepro3d:{self.block_id}:{tag}").hex

    def pt(self, m, p):
        a, b, c, d, e, f = m
        x, y = a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f
        return [round((x - VIEWBOX / 2) * self.k, 6), round((y - VIEWBOX / 2) * self.k, 6)]

    @staticmethod
    def stroke_style(colour):
        # SB4g R14: the existing weight system, like every other block primitive --
        # By Linetype (stroke_style.default_style; follows the DM "Blocks" weight).
        # The SVG's stroke-width is dropped: a thick stroke becomes its centre line.
        return {"linetype": "continuous", "weight": "by_linetype",
                "start": {"end": "by_linetype", "visible": True},
                "finish": {"end": "by_linetype", "visible": True},
                "colour": colour}

    def _common(self, rec, st, m):
        rec["uid"] = self.uid(len(self.prims))
        rec["draw_z"] = len(self.prims) / 1000.0        # keep SVG document paint order
        stroke = _colour(st.get("stroke"))
        if stroke is not None:
            rec["style"] = self.stroke_style(stroke)
        fill = _colour(st.get("fill"))
        if fill is not None:
            rec["fill"] = {"background": {"color": fill,
                                          "opacity": float(st.get("fill-opacity", 1.0))}}
        self.prims.append(rec)

    def _pieces(self, m, segs, tag, one_per_cubic):
        out, run = [], []

        def spline(run_segs, j):
            # A clamped cubic Bezier chain (geometry_2d._is_bezier_chain): Qt
            # draws each span natively with cubicTo -- exact, not flattened.
            cps = [self.pt(m, run_segs[0][1])]
            for s in run_segs:
                cps += [self.pt(m, s[2]), self.pt(m, s[3]), self.pt(m, s[4])]
            n = len(run_segs)
            knots = [0.0] * 4 + [float(v) for v in range(1, n) for _ in range(3)] + [float(n)] * 4
            return {"type": "draw_spline", "control_points": cps, "degree": 3,
                    "knots": knots, "weights": None, "uid": self.uid(f"{tag}-s{j}")}

        for j, s in enumerate(segs):
            if s[0] == "C":
                run.append(s)
                if one_per_cubic:
                    out.append(spline(run, j)); run = []
                continue
            if run:
                out.append(spline(run, j)); run = []
            out.append({"type": "draw_line", "pt1": self.pt(m, s[1]), "pt2": self.pt(m, s[2]),
                        "uid": self.uid(f"{tag}-l{j}")})
        if run:
            out.append(spline(run, len(segs)))
        return out

    def circle(self, el, st, m):
        cx, cy = self.pt(m, (float(el.get("cx")), float(el.get("cy"))))
        r = round(float(el.get("r")) * math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) * self.k, 6)
        self._common({"type": "draw_circle", "cx": cx, "cy": cy, "radius": r}, st, m)

    def path(self, el, st, m):
        for si, sub in enumerate(parse_path(el.get("d"))):     # d="" -> no subpaths: dropped
            tag = f"{len(self.prims)}-{si}"
            if sub["closed"] or (_colour(st.get("fill")) is not None
                                 and _area(sub["segs"]) > 1e-9):
                # A closed / filled subpath -> Filled Region: one piece per cubic so
                # curve_chain.loop_path joins every corner (closeSubpath) like "z".
                rec = {"type": "draw_filled_region",
                       "loops": [self._pieces(m, sub["segs"], tag, True)],
                       "outline": _colour(st.get("stroke")) is not None}
                self._common(rec, st, m)
            else:
                for piece in self._pieces(m, sub["segs"], tag, False):
                    self._common(piece, {**st, "fill": "none"}, m)

    def walk(self, el, st, m):
        st = _style(el, st)
        m = _mul(m, _parse_transform(el.get("transform")))
        tag = el.tag.replace(_SVG, "")
        if tag == "circle":
            self.circle(el, st, m)
        elif tag == "path":
            self.path(el, st, m)
        elif tag in ("g", "svg"):
            for ch in el:
                self.walk(ch, st, m)


def convert(rel, name, block_id, symbol_for, target_mm):
    root = ET.parse(os.path.join(GRAPHICS, rel)).getroot()
    vb = [float(v) for v in root.get("viewBox").split()]
    assert vb == [0.0, 0.0, VIEWBOX, VIEWBOX], (rel, vb)
    conv = Converter(block_id, target_mm / VIEWBOX)
    conv.walk(root, {}, IDENT)
    return {
        "schema": 1, "id": block_id, "version": 1, "name": name,
        "library": "System", "series": "Symbols", "scale_mode": "real_size",
        "origin": [0.0, 0.0], "attributes": [], "host_category": "",
        "symbol_for": symbol_for,
        "primitives": conv.prims, "render_mode": "default", "constraints": [],
        "tile": None, "repeat": None, "base_version": 1, "colour_tokens": 1,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="dry run: write raw records here")
    args = ap.parse_args(argv)
    recs = [convert(*src) for src in SOURCES]
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        for rec in recs:
            with open(os.path.join(args.out, rec["name"] + ".fpdb"), "w", encoding="utf-8") as fh:
                json.dump(rec, fh, indent=2)
        return 0
    from firepro3d import block_library
    from firepro3d.assets import system_blocks_path
    from firepro3d.block_definition import BlockDefinition
    folder = os.path.join(system_blocks_path(), "Symbols")
    os.makedirs(folder, exist_ok=True)
    for rec in recs:
        # Round-trip through the model so the file has the writer's canonical shape
        # (the promote record: to_dict + base_version + colour_tokens, system_promote.promote).
        out = BlockDefinition.from_dict(rec).to_dict()
        out.update(base_version=1, colour_tokens=1)
        block_library.write_shipped(os.path.join(folder, rec["name"] + ".fpdb"), out)
        print("wrote", rec["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
