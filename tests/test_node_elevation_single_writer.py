"""Node elevation single writer (D1): only firepro3d/node.py assigns a node's
ceiling_level / ceiling_offset / z_pos or touches its Ceiling panel rows."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"ceiling_level", "ceiling_offset", "z_pos"}
ROWS = {"Ceiling Level", "Ceiling Offset"}
# A node-less template sprinkler's own rows are its storage (Q3 / Q8).
ROW_EXEMPT = {("firepro3d/sprinkler.py", "self"),
              ("firepro3d/sprinkler_workflow_controller.py", "temp_spr")}


def _sources():
    yield ROOT / "main.py"
    yield from sorted((ROOT / "firepro3d").rglob("*.py"))


def _violations(path: Path, rel: str):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
    out = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for t in targets:
            for el in (t.elts if isinstance(t, ast.Tuple) else [t]):
                if isinstance(el, ast.Attribute) and el.attr in FIELDS:
                    out.append(f"{rel}:{el.lineno} assigns .{el.attr}")
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "setattr" and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant) and node.args[1].value in FIELDS):
            out.append(f"{rel}:{node.lineno} setattr {node.args[1].value}")
        if (isinstance(node, ast.Attribute) and node.attr == "_recompute_z_pos"):
            out.append(f"{rel}:{node.lineno} calls _recompute_z_pos")
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                and node.value.attr == "_properties"
                and isinstance(node.slice, ast.Constant) and node.slice.value in ROWS):
            owner = node.value.value
            name = owner.id if isinstance(owner, ast.Name) else ast.unparse(owner)
            if (rel, name) not in ROW_EXEMPT:
                out.append(f"{rel}:{node.lineno} touches {name}._properties[{node.slice.value!r}]")
    return out


def test_only_node_writes_node_elevation():
    bad = []
    for path in _sources():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "firepro3d/node.py":
            continue
        bad += _violations(path, rel)
    assert bad == [], "node elevation written outside Node:\n" + "\n".join(bad)


def test_the_scan_catches_a_write():
    src = "n.ceiling_offset = 3\nsetattr(n, 'z_pos', 1)\nn._properties['Ceiling Level']['value'] = 'x'\n"
    p = ROOT / "tests" / "_scan_probe_tmp.py"
    p.write_text(src, encoding="utf-8")
    try:
        assert len(_violations(p, "probe.py")) == 3
    finally:
        p.unlink()


def test_a_node_ceiling_is_not_a_level_offsets_entry():
    """Delete / rename re-host a Node through Node (rehost_keep_z / host); the
    generic offset rebase must never also carry node ceiling_level."""
    from firepro3d.level_manager import _LEVEL_OFFSETS, _SLAB_LEVEL_OFFSETS
    assert "ceiling_level" not in _LEVEL_OFFSETS
    assert "ceiling_level" not in _SLAB_LEVEL_OFFSETS
