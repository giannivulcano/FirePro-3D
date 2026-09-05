"""Throwaway harness: generate an interactive HTML gallery of Blocks-group ribbon
icon candidates (Make / Insert / Manager) for the S5 mockup gate.

Each candidate SVG is authored in the two-token contract (#1A1A1A primary /
#004CFF accent) and rendered here token-substituted for both themes at the two
ribbon render sizes (54 px large, 27 px small) on the matching theme swatch.

Browser SVG rendering is close enough for the *pick*; the chosen icons get a
final Qt-loader render-through pass before merge (the fidelity gate).

Run:  venv/Scripts/python.exe tools/mockup_block_icons.py
Then: python -m http.server 8000 --directory tools   ->  open /block_icons.html
"""
import os

# Two-token display values per spec icon-style-guide.md §4.2.
LIGHT = {"bg": "#f0f0f0", "primary": "#1A1A1A", "accent": "#2f9e63"}
DARK = {"bg": "#2b2b2b", "primary": "#F0F0F0", "accent": "#63BE8B"}

SVG_OPEN = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" '
            'fill="none" stroke="{primary}" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" '
            'width="{sz}" height="{sz}">')


# --- Candidate glyph bodies (authored with the #1A1A1A / #004CFF sentinels) ----
# A shared "block" motif = a rounded square frame; each button varies the accent
# affordance. Authored at the 48-unit canvas, >=2 units from every edge.

CANDIDATES = {
    "Make Block": {
        "M1 plus": '''
  <rect x="10" y="10" width="28" height="28" rx="3"/>
  <path stroke="#004CFF" d="M24 17 V31"/>
  <path stroke="#004CFF" d="M17 24 H31"/>''',
        "M2 gather": '''
  <path d="M16 20 L23 27"/>
  <circle cx="30" cy="19" r="3"/>
  <path d="M17 31 H27"/>
  <path stroke="#004CFF" d="M10 16 V11 H15"/>
  <path stroke="#004CFF" d="M33 11 H38 V16"/>
  <path stroke="#004CFF" d="M38 32 V37 H33"/>
  <path stroke="#004CFF" d="M15 37 H10 V32"/>''',
        "M3 corner-badge": '''
  <rect x="9" y="13" width="25" height="25" rx="3"/>
  <path d="M15 21 H23"/>
  <path d="M15 27 H28"/>
  <path d="M15 33 H24"/>
  <circle stroke="#004CFF" cx="37" cy="13" r="6"/>
  <path stroke="#004CFF" d="M37 10 V16"/>
  <path stroke="#004CFF" d="M34 13 H40"/>''',
    },
    "Insert Block": {
        "I1 arrow-in": '''
  <rect x="10" y="20" width="28" height="20" rx="3"/>
  <path stroke="#004CFF" d="M24 6 V17"/>
  <path stroke="#004CFF" d="M19 12 L24 17 L29 12"/>''',
        "I2 base-node": '''
  <rect x="10" y="10" width="28" height="28" rx="3"/>
  <circle stroke="#004CFF" cx="24" cy="24" r="3.5"/>
  <path stroke="#004CFF" d="M24 14 V19"/>
  <path stroke="#004CFF" d="M24 29 V34"/>
  <path stroke="#004CFF" d="M14 24 H19"/>
  <path stroke="#004CFF" d="M29 24 H34"/>''',
        "I3 drop-to-node": '''
  <rect x="11" y="18" width="26" height="22" rx="3"/>
  <path d="M17 25 H31"/>
  <path d="M17 31 H27"/>
  <path stroke="#004CFF" d="M24 4 V13"/>
  <path stroke="#004CFF" d="M20 9 L24 13 L28 9"/>''',
    },
    "Block Manager": {
        "G1 grid": '''
  <rect x="9" y="9" width="13" height="13" rx="2"/>
  <rect x="26" y="9" width="13" height="13" rx="2"/>
  <rect x="9" y="26" width="13" height="13" rx="2"/>
  <rect stroke="#004CFF" x="26" y="26" width="13" height="13" rx="2"/>''',
        "G2 list": '''
  <rect x="8" y="12" width="17" height="24" rx="3"/>
  <path d="M12 19 H21"/>
  <path d="M12 29 H21"/>
  <path stroke="#004CFF" d="M31 17 H42"/>
  <path stroke="#004CFF" d="M31 24 H42"/>
  <path stroke="#004CFF" d="M31 31 H42"/>''',
        "G3 gear": '''
  <rect x="8" y="10" width="24" height="24" rx="3"/>
  <path d="M13 18 H27"/>
  <path d="M13 24 H23"/>
  <circle stroke="#004CFF" cx="35" cy="35" r="4"/>
  <path stroke="#004CFF" d="M35 28 V31"/>
  <path stroke="#004CFF" d="M35 39 V42"/>
  <path stroke="#004CFF" d="M28 35 H31"/>
  <path stroke="#004CFF" d="M39 35 H42"/>''',
    },
}


def _svg(body: str, theme: dict, sz: int) -> str:
    s = SVG_OPEN.format(primary=theme["primary"], sz=sz) + body + "\n</svg>"
    # token substitution: authoring sentinels -> per-theme display values
    return (s.replace("#004CFF", theme["accent"])
             .replace("#1A1A1A", theme["primary"]))


def _cell(body: str, theme: dict) -> str:
    big = _svg(body, theme, 54)
    small = _svg(body, theme, 27)
    return (f'<div class="swatch" style="background:{theme["bg"]}">'
            f'<div class="pair">{big}{small}</div></div>')


def main():
    rows = []
    for button, cands in CANDIDATES.items():
        cells = []
        for label, body in cands.items():
            cells.append(
                f'<div class="cand"><div class="lbl">{label}</div>'
                f'<div class="themes">{_cell(body, LIGHT)}{_cell(body, DARK)}</div>'
                f'</div>')
        rows.append(f'<section><h2>{button}</h2>'
                    f'<div class="row">{"".join(cells)}</div></section>')

    html = f'''<!doctype html><html><head><meta charset="utf-8">
<title>Blocks-group ribbon icon candidates (S5)</title>
<style>
  body {{ font-family: "Segoe UI", system-ui, sans-serif; background:#565656;
         color:#e8e8e8; margin:0; padding:24px 32px; }}
  h1 {{ font-size:18px; font-weight:600; margin:0 0 4px; }}
  .sub {{ color:#b8b8b8; font-size:12px; margin:0 0 24px; }}
  section {{ margin:0 0 28px; }}
  h2 {{ font-size:14px; font-weight:600; color:#63BE8B; margin:0 0 10px;
        border-bottom:1px solid #6e6e6e; padding-bottom:6px; }}
  .row {{ display:flex; gap:22px; flex-wrap:wrap; }}
  .cand {{ background:#4a4a4a; border-radius:8px; padding:12px 14px; }}
  .lbl {{ font-size:12px; color:#d8d8d8; margin-bottom:8px; text-align:center;
          font-variant:all-small-caps; letter-spacing:.5px; }}
  .themes {{ display:flex; gap:10px; }}
  .swatch {{ border-radius:6px; padding:10px 12px; display:flex;
             align-items:center; justify-content:center; }}
  .pair {{ display:flex; align-items:center; gap:12px; }}
</style></head><body>
<h1>Blocks-group ribbon icons — candidates (S5 mockup gate)</h1>
<p class="sub">Each candidate at 54&nbsp;px (large button) + 27&nbsp;px (small button),
light and dark theme swatches. Two-token authored (#1A1A1A / #004CFF), substituted
to the per-theme display accent. Pick one per button.</p>
{"".join(rows)}
</body></html>'''

    out = os.path.join(os.path.dirname(__file__), "block_icons.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(out)


if __name__ == "__main__":
    main()
