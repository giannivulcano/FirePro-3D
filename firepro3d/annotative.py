"""Annotative block sizing (SB1c design D1-D10).

One factor k -- scene units per authored (printed) mm -- decided per paint
or bounds read from the ET1 gates (``linetype_render.screen_fixed_here``,
``end_render.screen_factor``); no new rule. See
docs/superpowers/specs/2026-10-23-sb1c-annotative-sizing-design.md.
"""
from __future__ import annotations

from . import end_render as _er
from .end_render import SCREEN_FIXED, SCREEN_SCALE
from . import linetype_render as _lr

SCALE_MODE_ANNOTATIVE = "annotative"
_PLAN_ROLE = "plan"


def is_annotative(defn) -> bool:
    """True when *defn* (a BlockDefinition or None) is Scale mode Annotative."""
    return defn is not None and getattr(defn, "scale_mode", None) == SCALE_MODE_ANNOTATIVE


def screen_mode(defn) -> str:
    """The definition's On screen mode: ``SCREEN_FIXED`` or ``SCREEN_SCALE``
    (missing / unknown -> Scale with zoom, D2)."""
    return SCREEN_FIXED if getattr(defn, "annotative_screen", None) == SCREEN_FIXED else SCREEN_SCALE


def paper_scene_size(mm: float, paper_scale: float) -> float:
    """Scene units that plot as *mm* printed mm at *paper_scale* (paper mm
    per model mm) -- the one paper conversion (D10)."""
    return float(mm) / max(float(paper_scale), 1e-9)


def frame_scaled(item) -> bool:
    """True when *item* sizes by a frame (painter) scale instead of the
    variant: an annotative Fixed-size block on a plan canvas (D4)."""
    if not is_annotative(item.definition()) or item._paper_scale:
        return False
    sc = item.scene()
    role = getattr(sc, "scene_role", None) if sc is not None else None
    return (role == _PLAN_ROLE and screen_mode(item.definition()) == SCREEN_FIXED
            and _lr.screen_fixed_here(paper_scale=None, role=role))


def _is_section_canvas(sc) -> bool:
    """True when *sc* is a section / elevation scene (``SectionScene``).

    Recognised by type, not by a ``scene_role``: other readers branch on the
    role (linetype / end sizing, block drop), and a new value there would
    change them. The import is local (section_scene imports block_instance).
    """
    if sc is None:
        return False
    from .section_scene import SectionScene
    return isinstance(sc, SectionScene)


def _drawing_scale(sc) -> float:
    """The project drawing scale read off *sc*'s ScaleManager; 1 when absent.

    A section scene reads its model space's live ``scale_manager``, not its own
    ``_sm``: a project load replaces the model's ScaleManager while the
    SectionManager keeps the one it was built with."""
    ms = getattr(sc, "_ms", None) if _is_section_canvas(sc) else None
    sm = getattr(ms if ms is not None else sc, "scale_manager", None) \
        or getattr(sc, "_sm", None)
    ds = getattr(sm, "drawing_scale", None)
    return float(ds) if ds else 1.0


def annotative_factor(item, painter=None) -> float:
    """Scene units per authored mm for BlockInstance *item* (design table).

    Real size, no scene, or any non-plan, non-section scene (the Block
    Editor, whose nested instances follow D5, and any other scene role)
    -> 1. A paper pass (``item._paper_scale`` = S) -> 1 / S. A section / elevation canvas (scene in mm) -> the project drawing
    scale for Scale with zoom and for Fixed size alike (VC9 I1 ruling: Fixed
    stays plan-only; its frame machinery is not extended there). Fixed size on
    a plan canvas -> ``FIXED_END_PX_PER_MM`` device px per mm: / the painter's
    device scale when *painter* is given (paint), else / the scene's
    visible-view zoom (bounds; the zoom hook re-prepares). Otherwise (Scale
    with zoom) -> the project drawing scale.
    """
    d = item.definition()
    if not is_annotative(d):
        return 1.0
    if item._paper_scale:
        return 1.0 / item._paper_scale
    sc = item.scene()
    if _is_section_canvas(sc):
        return _drawing_scale(sc)
    if sc is None or getattr(sc, "scene_role", None) != _PLAN_ROLE:
        return 1.0
    if frame_scaled(item):
        if painter is not None:
            from .hatch_render import _device_scale
            dev = _device_scale(painter)
        else:
            from .view_scale import scene_view_scale
            dev = scene_view_scale(sc)
        return _er.screen_factor(paper_scale=None, role=_PLAN_ROLE, device_scale=dev)
    # Not linetype_render.printed_factor: it returns drawing_scale for the
    # block_editor role, but D5 needs k = 1 there (handled above).
    return _drawing_scale(sc)


def reprepare_annotative(scene) -> None:
    """Re-prepare every annotative instance of *scene* (a drawing-scale
    change resizes them, D7); a section scene's hosted copies included."""
    insts = list(getattr(scene, "_block_instances", ()))
    insts += list(getattr(scene, "_hosted_copies", {}).values())
    for inst in insts:
        if is_annotative(inst.definition()):
            inst.prepareGeometryChange()
            inst.update()


def model_factor(item) -> float:
    """Explode / model-pose scale factor of *item* (ruling 2026-10-23: explode
    bakes the size you see): an annotative block on a plan or section canvas
    -> the drawing scale (Fixed size too, its screen size is zoom-dependent);
    otherwise 1."""
    if not is_annotative(item.definition()):
        return 1.0
    sc = item.scene()
    if _is_section_canvas(sc):
        return _drawing_scale(sc)
    if sc is None or getattr(sc, "scene_role", None) != _PLAN_ROLE:
        return 1.0
    return _drawing_scale(sc)
