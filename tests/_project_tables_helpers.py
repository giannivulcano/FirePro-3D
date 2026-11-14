"""Shared helpers for the project-tables characterisation (design DD6)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from firepro3d import weight_refs as wr

FIXDIR = Path(__file__).parent / "fixtures"
PT_DIR = FIXDIR / "project_tables"
GOLDEN = PT_DIR / "golden"

_CYCLE = ["Thinnest", "Thin", "Thinner", "Thick", "Light", "Thickest"]


def inject_by_name_weights(payload: dict) -> int:
    """Give every stroke style in the file's block definitions a legacy weight
    name (cycled over MW names, one a name the table lacks) so the sweep has
    holders; returns how many were set."""
    n = 0

    def walk(o):
        nonlocal n
        if isinstance(o, dict):
            st = o.get("style")
            if isinstance(st, dict) and "weight" in st:
                st["weight"] = _CYCLE[n % len(_CYCLE)]
                n += 1
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(payload.get("block_definitions"))
    return n


def holders(ms) -> list[tuple[str, str]]:
    """(kind, weight name) for every by-name weight holder in *ms*."""
    return [(kind, name) for name, (kind, _r) in wr.iter_weight_refs(ms)]


def prepared_copy(src: Path, dst_dir: Path, name: str | None = None) -> Path:
    """Copy *src* into *dst_dir* with by-name holders injected."""
    payload = json.loads(src.read_text(encoding="utf-8"))
    inject_by_name_weights(payload)
    dst = dst_dir / (name or src.name)
    dst.write_text(json.dumps(payload), encoding="utf-8")
    return dst


def resave_text(scene, tmp_path: Path) -> str:
    """Save *scene* to a tmp file and return its text with the tmp dir
    normalised to ``<TMP>`` (both slash forms and the JSON-escaped form)."""
    out = tmp_path / "resave.fpd"
    scene.save_to_file(str(out), backup=False)
    text = out.read_bytes().decode("utf-8")
    for form in (str(tmp_path).replace("\\", "\\\\"), str(tmp_path), tmp_path.as_posix()):
        text = text.replace(form, "<TMP>")
    return text


def add_extra_tables(path: Path) -> None:
    """Append one extra phase and one extra fill type to the file at *path* so
    its tables differ from the seed (a New project must then visibly reset them)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["phases"].append({
        "id": "pt-extra-phase", "name": "PT extra phase", "builtin": False,
        "graphics": {"colour": None, "fill": None, "weight": None,
                     "linetype": None, "opacity": None},
        "include_in_calc": True,
    })
    fill = json.loads(json.dumps(payload["fill_types"][0]))
    fill["id"] = "0123456789abcdef0123456789abcdef"
    fill["name"] = "PT extra fill"
    payload["fill_types"].append(fill)
    path.write_text(json.dumps(payload), encoding="utf-8")


def normalise_ids(text: str) -> str:
    """Replace every 32-hex id token with ``<ID{n}>`` (n = order of first
    appearance; the same token always gets the same n). Seeded fill-type and
    material ids are fresh uuid4 values per seeding."""
    seen: dict[str, str] = {}

    def sub(m):
        return seen.setdefault(m.group(0), f"<ID{len(seen)}>")
    return re.sub(r"\b[0-9a-f]{32}\b", sub, text)


def snapshot(scene, tmp_path: Path) -> tuple[dict, str]:
    """The characterisation snapshot (design DD6) and the normalised re-save."""
    from firepro3d import fill_types, materials, phase_registry
    from firepro3d import paper_display as pd
    from firepro3d.display_manager import get_display_settings_for_save
    text = resave_text(scene, tmp_path)
    snap = {
        "weights": [d.to_dict() for d in pd.project_line_weights()],
        "aliases": pd.weight_aliases(),
        "model_blocks_weight": pd.model_blocks_weight(),
        "fill_types": fill_types.project_table().to_payload(),
        "materials": materials.project_table().to_payload(),
        "phases": phase_registry.to_list(),
        "dm_rows": get_display_settings_for_save(),
        "paper_categories": pd.load_paper_categories(),
        "holders": sorted(holders(scene)),
    }
    return json.loads(json.dumps(snap)), text


def open_main_window(monkeypatch, tmp_path: Path):
    """A real MainWindow with the template-push offer off and the autosave
    path under *tmp_path*. Caller disposes it with
    ``tests._mainwindow_helpers.dispose_main_window``."""
    import main as _m
    from firepro3d.view_3d import View3D
    _m.View3D = View3D
    monkeypatch.setattr(_m.MainWindow, "_maybe_offer_template_push", lambda self: None)
    autosave = tmp_path / "autosave" / "recovery.FPD"
    monkeypatch.setattr(_m.MainWindow, "_autosave_path", staticmethod(lambda: str(autosave)))
    return _m.MainWindow()


def capture_sessions(monkeypatch) -> list:
    """Spy on ``project_tables.begin_load``; returns the list each new
    ``LoadSession`` is appended to (DD7 rewrites read payloads from it)."""
    from firepro3d import project_tables
    seen: list = []
    real = project_tables.begin_load

    def spy(payload):
        s = real(payload)
        seen.append(s)
        return s
    monkeypatch.setattr(project_tables, "begin_load", spy)
    return seen
