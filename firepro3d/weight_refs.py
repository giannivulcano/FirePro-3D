"""Scene-level line-weight reference sweep (linetypes.md LT1-5 / LT2-8, LW-DC).

Every by-name line-weight holder in a project is reachable from here: the
Model "Blocks" weight, paper categories, underlays, sheet / model / block-
definition texts and styled geometry, placed blocks and nested-record
overrides. The Display Manager's rename (LT2-8) and the Line Weights
delete-with-replace / open-time migration (LW-DC) all go through these
functions, so a holder kind added to the sweep is seen by all of them.
"""
from __future__ import annotations

import copy
from collections.abc import Iterator

# Weight-only Model-tab row key (linetypes.md LT2-6): the QSettings group
# ``display/<key>/line_weight`` that mirrors the Model "Blocks" weight.
MODEL_BLOCKS_KEY = "Blocks"


def iter_weight_refs(scene) -> Iterator[tuple[str, tuple[str, object]]]:
    """Yield ``(name, (kind, ref))`` for every live by-name weight ref:
    sheet annotations; model-plan texts; project definition text
    primitives and stroke ``style.weight``; open Block Editors' texts and
    styled raw items, and the project scene's styled geometry
    (linetypes.md LT1-5 / LT2-8); placed blocks' Weight overrides and
    definitions' nested-record Weight overrides (WM2).
    """
    from .stroke_style import is_named_weight
    for sheet in getattr(scene, "_sheets", []) or []:
        for ann in getattr(sheet, "annotations", []):
            yield ann.border_weight, ("ann", ann)
            if (getattr(ann, "leader", None) or {}).get("weight"):
                yield ann.leader["weight"], ("lead_ann", ann.leader)
    scenes = [scene]
    prov = getattr(scene, "_editor_scenes_provider", None)
    if callable(prov):
        scenes.extend(sc for sc in prov() if sc is not scene)
    for sc in scenes:
        for item in getattr(sc, "_texts", []) or []:
            yield item._data.border_weight, ("item", item)
            if (item._data.leader or {}).get("weight"):
                yield item._data.leader["weight"], ("lead_item", item)
        for item in sc.items():
            st = getattr(item, "style", None)
            if isinstance(st, dict) and is_named_weight(st.get("weight")):
                yield st["weight"], ("raw", item)
        for inst in getattr(sc, "_block_instances", []) or []:
            w = getattr(inst, "overrides", {}).get("weight")
            if is_named_weight(w):
                yield w, ("inst", inst)
            lw = ((getattr(inst, "note", None) or {}).get("leader") or {}).get("weight")
            if lw:
                yield lw, ("lead_inst", inst)      # a Note's leader weight
            bw = ((getattr(inst, "note", None) or {}).get("style") or {}).get("border_weight")
            if bw:
                yield bw, ("style_inst", inst)     # a Note's own border weight
    reg = getattr(scene, "block_registry", None)
    if reg is not None:
        for bid in reg.ids():
            defn = reg.get(bid)
            for prim in getattr(defn, "primitives", []) or []:
                if prim.get("type") == "text" and "border_weight" in prim:
                    yield prim["border_weight"], ("prim", (bid, prim))
                if (prim.get("type") == "text"
                        and (prim.get("leader") or {}).get("weight")):
                    yield prim["leader"]["weight"], ("lead_prim", (bid, prim["leader"]))
                st = prim.get("style")
                if isinstance(st, dict) and is_named_weight(st.get("weight")):
                    yield st["weight"], ("sprim", (bid, st))
                ov = prim.get("overrides")
                if isinstance(ov, dict) and is_named_weight(ov.get("weight")):
                    yield ov["weight"], ("nrec", (bid, ov))


def weight_ref_count(scene, settings, name: str) -> int:
    """Number of holders that reference *name* by name.

    Holder kinds: the Model "Blocks" weight (LT2-6 / LT2-8); paper
    categories; underlays (§16.6: the per-underlay default
    ``line_weight_name`` and each per-layer
    ``layer_overrides[layer]["line_weight"]``); every
    :func:`iter_weight_refs` kind. Holder names are compared canonically
    for the sweep kinds (an alias key counts as its target).
    """
    from .paper_display import (canonical_weight_name, load_paper_categories,
                                model_blocks_weight)
    n = 1 if model_blocks_weight() == name else 0
    cats = load_paper_categories(settings)
    n += sum(1 for v in cats.values() if v.get("line_weight") == name)
    for data, _item in getattr(scene, "underlays", []):
        if data.line_weight_name == name:
            n += 1
        n += sum(1 for ov in data.layer_overrides.values()
                 if ov.get("line_weight") == name)
    n += sum(1 for cur, _ref in iter_weight_refs(scene)
             if canonical_weight_name(cur) == name)
    return n


def is_weight_in_use(scene, settings, name: str) -> bool:
    """True if *name* is referenced anywhere by name (see
    :func:`weight_ref_count` for the holder kinds)."""
    return weight_ref_count(scene, settings, name) > 0


def _apply_ref(kind: str, ref, new, canonical_blocks: bool, touched: set):
    """Write *new* into one :func:`iter_weight_refs` holder (the per-kind
    write of the original Display Manager rename), recording touched block
    definition ids."""
    if kind == "lead_ann":
        ref["weight"] = new         # a sheet text's leader record
    elif kind == "lead_item":
        ref._data.leader["weight"] = new
        ref.update()
    elif kind == "lead_inst":
        ref.note["leader"]["weight"] = new
        ref.note_changed()
    elif kind == "style_inst":
        ref.note["style"]["border_weight"] = new
        ref.note_changed()
    elif kind == "lead_prim":
        bid, rec = ref
        rec["weight"] = new
        touched.add(bid)
    elif kind == "ann":
        ref.border_weight = new     # live paper TextItems alias this data
    elif kind == "item":
        ref._data.border_weight = new
        ref.update()
    elif kind == "raw":
        ref.style["weight"] = new
        ref.update()
    elif kind == "sprim":
        bid, st = ref
        st["weight"] = new
        touched.add(bid)
    elif kind == "inst":
        # Raw (canonical_blocks=False), like the Blocks weight: the Cancel
        # replay writes a pre-rename (alias-key) name before the aliases are
        # restored.
        ref.set_overrides({**ref.overrides, "weight": new},
                          canonical=canonical_blocks)
    elif kind == "nrec":
        bid, ov = ref
        ov["weight"] = new
        touched.add(bid)
    else:
        bid, prim = ref
        prim["border_weight"] = new
        touched.add(bid)


def retarget_weight_refs(scene, settings, mapping: dict[str, str], *,
                         canonical_blocks: bool = False,
                         underlays: bool = True) -> list[tuple]:
    """Re-point every by-name weight holder per *mapping* (``old -> new``).

    The mapping applies simultaneously and single-hop: every iter-sweep
    holder is read before any is written, so ``{"A": "B", "B": "A"}`` swaps.
    Holders: the Model "Blocks" weight (and its QSettings key), paper
    categories, underlays (default + layer overrides) and every
    :func:`iter_weight_refs` kind, with the registry invalidated for each
    touched block definition.

    Args:
        scene: The project scene.
        settings: The QSettings holding the paper categories.
        mapping: Old weight name to new weight name.
        canonical_blocks: Passed as ``canonical`` to placed blocks'
            ``set_overrides``; False (default) stores raw, which the Display
            Manager Cancel replay needs (see ``set_overrides``).
        underlays: False skips the underlay records (the project loader
            migrates their payloads before they are built).

    Returns:
        A journal of ``(kind, ref, key-path, old_value)`` for
        :func:`restore_weight_refs`.
    """
    from . import paper_display as pd
    journal: list[tuple] = []
    blocks_key = f"display/{MODEL_BLOCKS_KEY}/line_weight"
    cur_blocks = pd.model_blocks_weight()
    if cur_blocks in mapping and mapping[cur_blocks] != cur_blocks:
        journal.append(("blocks", None, blocks_key,
                        (pd._MODEL_BLOCKS_WEIGHT, settings.value(blocks_key))))
        # Raw: the Cancel replay writes a pre-rename (alias-key) name
        # before the table + aliases are restored.
        pd.set_model_blocks_weight(mapping[cur_blocks], canonical=False)
        settings.setValue(blocks_key, mapping[cur_blocks])
    cats = pd.load_paper_categories(settings)
    before = copy.deepcopy(cats)
    for cat_vals in cats.values():
        cur = cat_vals.get("line_weight")
        if cur in mapping:
            cat_vals["line_weight"] = mapping[cur]
    pd.save_paper_categories(cats, settings)
    if cats != before:
        journal.append(("cats", None, "paper/categories", before))
    for data, _item in (getattr(scene, "underlays", []) if underlays else []):
        cur = data.line_weight_name
        if cur in mapping and mapping[cur] != cur:
            journal.append(("underlay", data, "line_weight_name", cur))
            data.line_weight_name = mapping[cur]
        for ov in data.layer_overrides.values():
            cur = ov.get("line_weight")
            if cur in mapping and mapping[cur] != cur:
                journal.append(("underlay_layer", ov, "line_weight", cur))
                ov["line_weight"] = mapping[cur]
    touched: set = set()
    for cur, (kind, ref) in list(iter_weight_refs(scene)):
        if cur not in mapping or mapping[cur] == cur:
            continue
        if kind == "inst":
            journal.append((kind, ref, "overrides", dict(ref.overrides)))
        else:
            journal.append((kind, ref, "weight", cur))
        _apply_ref(kind, ref, mapping[cur], canonical_blocks, touched)
    reg = getattr(scene, "block_registry", None)
    for bid in touched:
        reg.invalidate(bid)
    return journal


def retarget_definition_refs(defs, mapping: dict[str, str]) -> int:
    """Re-point the weight names inside block *defs* per *mapping* (``old ->
    new``), simultaneously and single-hop (each value is read once).

    Covers the ``prim`` / ``lead_prim`` / ``sprim`` / ``nrec`` holder kinds
    of :func:`iter_weight_refs` -- a text primitive's ``border_weight`` and
    leader weight, a stroke's ``style.weight`` and a nested record's
    ``overrides.weight`` -- at any nesting depth of the primitive records
    (filled-region loops included). Used on a library file's definitions
    BEFORE they join the project (``Model_Space._merge_bundled_weights``),
    so no registry invalidation is needed.

    Args:
        defs: ``BlockDefinition`` objects (their ``primitives`` are edited).
        mapping: Old weight name to new weight name.

    Returns:
        The number of names rewritten.
    """
    from .stroke_style import is_named_weight
    n = 0

    def put(d: dict, key: str) -> None:
        nonlocal n
        cur = d.get(key)
        if isinstance(cur, str) and cur in mapping and mapping[cur] != cur:
            d[key] = mapping[cur]
            n += 1

    def walk(o) -> None:
        if isinstance(o, dict):
            if o.get("type") == "text":
                if "border_weight" in o:
                    put(o, "border_weight")
                if isinstance(o.get("leader"), dict) and o["leader"].get("weight"):
                    put(o["leader"], "weight")
            for key in ("style", "overrides"):
                rec = o.get(key)
                if isinstance(rec, dict) and is_named_weight(rec.get("weight")):
                    put(rec, "weight")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    if not mapping:
        return 0
    for defn in defs:
        walk(getattr(defn, "primitives", None) or [])
    return n


def restore_weight_refs(scene, settings, journal) -> None:
    """Undo a :func:`retarget_weight_refs` call exactly, newest write first.

    Every value goes back raw (placed blocks via ``set_overrides`` with
    ``canonical=False``, the Blocks weight via the raw setter), so a
    pre-retarget alias-key name is not canonicalised straight back.
    """
    from . import paper_display as pd
    touched: set = set()
    for kind, ref, path, old in reversed(journal):
        if kind == "blocks":
            raw, stored = old
            pd.set_model_blocks_weight(raw, canonical=False)
            if stored is None:
                settings.remove(path)
            else:
                settings.setValue(path, stored)
        elif kind == "cats":
            pd.save_paper_categories(old, settings)
        elif kind == "underlay":
            ref.line_weight_name = old
        elif kind == "underlay_layer":
            ref["line_weight"] = old
        elif kind == "inst":
            ref.set_overrides(dict(old), canonical=False)
        else:
            _apply_ref(kind, ref, old, False, touched)
    reg = getattr(scene, "block_registry", None)
    for bid in touched:
        reg.invalidate(bid)
