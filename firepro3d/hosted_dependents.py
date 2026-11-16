"""HostedDependents: the one host -> dependents hook (SB5 D5 / D6, concept F7).

A dependent is a placed ``BlockInstance`` that either sits on a gridline
(``host["gridline"]``, hosted-blocks D2) or binds an element by uid
(``_host_uid``, element-parameters D2 / D3). ``Model_Space`` keeps thin
forwarders (``_sync_hosted_blocks``). Wall -> opening, slab -> void and
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


def push(scene, host) -> None:
    """*host* changed: set its gridline-hosted blocks to their derived pose
    (the former ``Model_Space._sync_hosted_blocks`` body, D5) and re-shape its
    element-bound blocks' text.

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
            b.refresh_bound()


def refresh_all_bound(scene) -> None:
    """Re-shape every element-bound block (Q10: run at every committed step;
    undo / redo rebuilds every block, so restore needs no call). Quiet when nothing changed
    (``BlockInstance.refresh_bound`` compares the resolved strings)."""
    for b in _blocks(scene):
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
