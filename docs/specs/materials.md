---
status: approved design, build pending
last-verified: 2026-11-06  # forged by the Materials run; code probed at 5a9e8c4c
verified-commit: 5a9e8c4c
applies-to:
  - firepro3d/materials.py        # new: the project table, cut resolver, starters, load conversion
  - firepro3d/materials_tab.py    # new: Display Manager Materials tab
---

# Materials — Governing Spec

Owns the project **Materials table**, the wall / floor material field, and how a cut resolves
its look. Rule A: the Fill Type model is owned by `hatch-and-fill.md`, section geometry by
`section-view-subsystem.md`, wall and slab fields by `wall-room-floor-system.md`.

## Goal

Each wall and floor has its own material, and each material names the hatch shown wherever that
element is cut. Two walls in one section can show different hatches.

## Motivation

Section looks were per category, so every wall shared one hatch. A section could not tell
concrete from brick.

## Architecture & Constraints

- **One module, one table.** `materials.py` mirrors `fill_types.py`: a project-wide store outside
  undo (HF5 R9), replaced on load. No second bus: a change calls `fill_types.notify_changed()`.
- **Material row:** `id`, `name`, `fill_type` (a Fill Type id, or `None` = draws nothing).
- **Table extras:** `defaults` = `{"Wall": material id, "Floor": material id}`.
- **`None` material:** a fixed id (`MATERIAL_NONE_ID`, `constants.py`), always present, cannot be
  renamed or deleted, `fill_type` defaults to `None` and can be repointed like any other.
- **Element field:** `WallSegment` and `FloorSlab` hold a material id. `to_dict` writes it, which
  also covers undo (one serializer; `push_undo_state` snapshots through `to_dict`). A missing key
  or an id the table lacks reads as the None material.
- **One cut resolver:** `materials.fill_type_of(item)` returns the Fill Type id or `None`. Every
  cut paint calls it per paint: wall, slab and the section `_ElevCutRect`. Nothing is cached on
  the element, so a table edit reaches the next paint with no refresh pass.
- **`draw_section_type`:** `type_id=None` draws nothing (the built-in diagonal fallback retires).
  Empty layers also draw nothing, before any paper body.
- **Placement default:** `apply_category_defaults` stamps the category default on a new wall or
  slab. It is not on the load path, so a saved id is never overwritten.
- **Roofs and pipes:** out of scope. A pipe's `Material` (hydraulics text) is unrelated.

## Design Decisions

| # | Decision | Ratified by |
|---|---|---|
| M1 | Per-element material, plus a per-category default for new elements | Phase 2 FP1 |
| M2 | A material picks one Fill Type; D-A17's one hatch vocabulary holds | Phase 2 FP1 |
| M3 | The hatch shows on every cut: section views, plan cuts, paper | Phase 2 FP1 |
| M4 | Walls and Floors only this run | Phase 2 FP1 |
| M5 | Model tab Section column retired; defaults live on the Materials tab | Phase 2 FP1 |
| M6 | Per-element material is set in Properties only, not on Display Manager instance rows | Phase 2 FP1 |
| M7 | Instance section overrides retire and convert to a material on load | Phase 2 FP1 |
| M8 | Old projects open as None; old category looks stop drawing, their Fill Types stay | Phase 2 FP1 |
| M9 | None is permanent; default look no hatch and no fill; can be set to solid or hatch | Phase 2 FP1 |
| M10 | Starters: None, Concrete, Brick, Wood Framed (Cross Hatch), Steel Framed (Diagonal) | Phase 2 FP1 |
| M11 | New elements default to None until changed on the Materials tab | Phase 2 FP1 |
| M12 | Deleting an in-use material is refused with "used by N" | Phase 2 FP1 |
| M13 | Own table resolved at paint, not a Fill Type flag or an element cache | Phase 3 approval |
| M14 | The Properties row is **Building Material**: rows key on their label and `Material` is a pipe row, so a shared key would write across item types | Phase 3 approval |
| M15 | On a non-Full-Color paper pass the paper Section colour applies only when the material's Fill Type has a background; a hatch-only material prints line-colour hatch with no body | Phase 3 approval |
| M16 | Materials tab = list + editor like Fill Types, with Default for Wall / Floor pickers above | Phase 3 approval |

## Materials tab

Sits after Fill Types. Edits a working copy; OK installs it, Cancel restores it (the Fill Types
tab's rule, including `dirty` and the snapshot). Reset All and Set as Default are disabled on it,
because the table is per project. The Section selector lists the Fill Types tab's working table
plus **No hatch**, so a type added in the same dialog session can be picked.

## Input / Output

Project file key `materials`, loaded right after `fill_types`, with no `SAVE_VERSION` bump (the
key is additive):

```json
{"rows": [{"id": "...", "name": "Concrete", "fill_type": "..."}],
 "defaults": {"Wall": "...", "Floor": "..."}}
```

Element key `material` (a material id), omitted when it is the None material.

## Edge Cases & Error Handling

- **File with no `materials` key:** the starters load, adding their Fill Types by name
  (`ensure_named`, project wins on a name clash).
- **Legacy override:** `from_dict` first converts old `section` keys
  (`convert_item_section_override`), then turns `section_type` into a material named after the
  Fill Type, created if absent, and drops the override. Re-running on a snapshot is a no-op.
- **Fill Type delete:** a material's reference counts in `type_users`, so it is refused.
- **Fill Mode Section:** a wall with that mode shows its material's look in plan as it shows the
  category look today; on None it shows nothing.
- **Unknown material id** (a paste from another project): reads as None; the id stays stored.

## Acceptance Criteria

1. Two cut walls with different materials draw different looks in a real section.
2. The same walls show their own material's look in a plan cut and a paper viewport.
3. A Fill Type restyle or a material re-point reaches cut elements at the next repaint.
4. Assignments and the table survive save and reload; undo restores a changed material.
5. An old file opens with None on untouched elements; an instance override becomes an assigned
   material with the same look.
6. Deleting an in-use material, or None, is refused with the reason shown.
7. A new wall or floor takes the category default.
8. In a mixed wall and pipe selection, setting Building Material leaves the pipe's `Material` alone.
9. A hatch-only material prints hatch without a black body on B&W paper; None prints nothing.

## Verification Checklist

- [ ] Each criterion has a guard driving the real path, shown RED with its rule reverted.
- [ ] No `section_type` category read remains in `section_scene.py`.
- [ ] Model tab has no Section column; the Paper Space tab keeps its Section colour.
- [ ] `hatch-and-fill.md` D-A17, `section-view-subsystem.md` s5, `wall-room-floor-system.md` and
      `display-system.md` link here at Account.
