"""HostedDependents: the one host -> dependents hook (SB5 D5 / D6, concept F7).

A dependent is a placed ``BlockInstance`` that either sits on a gridline
(``host["gridline"]``, hosted-blocks D2) or binds an element by uid
(``_host_uid``, element-parameters D2 / D3), or is a placed tag (``_host_uid``
+ a ``tag`` record, SB6 D1) whose pose is derived from its host.
``Model_Space`` keeps thin forwarders (``_sync_hosted_blocks``). Wall -> opening, slab -> void and
node -> pipe / fitting keep their object-ref mechanisms (design Q7; their
migration is a filed follow-up).
"""
from __future__ import annotations


def _blocks(scene) -> list:
    return list(getattr(scene, "_block_instances", None) or ())


def _hosted_on(block, uid: str) -> bool:
    return bool(block.host) and block.host.get("gridline") == uid


def dependents_of(scene, host) -> list:
    """The blocks hosted on *host*: gridline-hosted (``host["gridline"]``) and
    element-bound (``_host_uid``) ones, in placement order.

    Args:
        scene: The plan scene.
        host: An element carrying ``_uid``.

    Returns:
        The dependent ``BlockInstance`` list ([] for a host without a uid).
    """
    uid = getattr(host, "_uid", None)
    if not uid:
        return []
    return [b for b in _blocks(scene) if _hosted_on(b, uid) or b._host_uid == uid]


def repose_tag(scene, block, host, ppm=None) -> None:
    """Re-resolve and re-pose placed tag *block* on *host* (SB6 D3 / D6).

    The swapped block while it is still an eligible tag of *host*'s category,
    else the category default (a stale swap is dropped, R8); the pose from the
    host-anchor offset (D2 / D5). A tag with a leader is re-shaped too: its
    tip (host frame, D9) moves with the host even when the tag itself does
    not -- but only when the leader's geometry key (host anchor + angle, tip,
    pose) changed, so a committed step that moved nothing repaints nothing.

    Args:
        scene: The plan scene.
        block: A ``BlockInstance`` with a ``tag`` record.
        host: Its live element host.
        ppm: Pixels per mm (None: read from *scene*).
    """
    from . import hosted_tag
    from .hosted_blocks import ppm_of
    bid = hosted_tag.resolve(block.tag, host, scene)
    if bid is not None and bid != block.block_id:
        block.set_block_id(bid)
    p = hosted_tag.pose(block.tag, host, ppm_of(scene) if ppm is None else ppm)
    if p is not None:
        block.set_tag_pose(*p)
    if block.tag.get("leader"):
        a = hosted_tag.anchor(host)
        tip = hosted_tag.tip_scene(block.tag, host, ppm_of(scene) if ppm is None else ppm)
        key = (None if a is None else (a[0].x(), a[0].y(), a[1]),
               None if tip is None else (tip.x(), tip.y()),
               block._pose_x, block._pose_y, block._pose_rot)
        if key != block._leader_geo:
            block._leader_geo = key
            block.tag_changed()


def push(scene, host) -> None:
    """*host* changed: set its gridline-hosted blocks to their derived pose
    (the former ``Model_Space._sync_hosted_blocks`` body, D5), re-pose its
    placed tags (SB6 D3) and re-shape its element-bound blocks' text.

    Args:
        scene: The plan scene.
        host: The changed element.
    """
    uid = getattr(host, "_uid", None)
    if not uid:
        return
    ppm = None
    for b in _blocks(scene):
        if _hosted_on(b, uid):
            from .hosted_blocks import ppm_of, scene_pos
            if ppm is None:
                ppm = ppm_of(scene)
            b.set_block_pos(*scene_pos(host, b.host, ppm))
        if b._host_uid == uid:
            if b.tag is not None:
                repose_tag(scene, b, host, ppm)
            b.refresh_bound()


def refresh_all_bound(scene) -> None:
    """Re-pose every placed tag on its live host (SB6 D3) and re-shape every
    element-bound block (Q10: run at every committed step -- ``push_undo_state``,
    before the snapshot -- so undo / redo rebuild re-posed tags and restore
    needs no call). Quiet when nothing changed (``set_tag_pose`` and
    ``BlockInstance.refresh_bound`` compare). A dangling tag keeps its pose."""
    for b in _blocks(scene):
        if b.tag is not None and b._host_uid is not None:
            host = b.element_host
            if host is not None:
                repose_tag(scene, b, host)
        if b._host_uid is not None or b._element_host is not None:
            b.refresh_bound()


def cascade(scene, removed) -> list:
    """The dependents of every host in *removed* that are not themselves in
    *removed* (D6), and drop each removed sprinkler from every design area's
    membership (Q14a). Callers remove the returned blocks inside their own
    undo step; nothing here reads scene membership (a removed host may still
    be in the scene when this runs).

    Args:
        scene: The plan scene.
        removed: Every element leaving the model in this step (hosts and
            any blocks already selected).

    Returns:
        The hosted / bound ``BlockInstance`` list to remove with them.
    """
    removed = list(removed)
    gone = set(removed)
    uids = {u for u in (getattr(it, "_uid", None) for it in removed)
            if isinstance(u, str) and u}
    out = [b for b in _blocks(scene) if b not in gone
           and ((b.host and b.host.get("gridline") in uids) or b._host_uid in uids)]
    from .sprinkler import Sprinkler
    for it in removed:
        if isinstance(it, Sprinkler):
            for da in list(getattr(scene, "design_areas", None) or ()):
                da.remove_sprinkler(it)
    return out


def cascade_status(verb: str, n_items: int, names: list, n_hosted: int) -> str:
    """Delete / Cut status text (Q13).

    Args:
        verb: ``"Deleted"`` or ``"Cut"``.
        n_items: The selection count.
        names: Labels of the gridlines whose hosted blocks went; empty when an
            element-bound dependent went too (``Model_Space._bulk_delete``).
        n_hosted: The cascaded block count.

    Returns:
        Today's gridline wording for a gridline-only cascade, else the generic
        "N item(s) and M hosted item(s)" suffix, else "N item(s)".
    """
    if n_hosted and names:
        if verb == "Deleted":
            return f"Deleted gridline {', '.join(names)} and {n_hosted} hosted block(s)"
        return f"{verb} {n_items} item(s) and {n_hosted} hosted block(s)"
    if n_hosted:
        return f"{verb} {n_items} item(s) and {n_hosted} hosted item(s)"
    return f"{verb} {n_items} item(s)"
