"""Block drag payload decoding + refusal resolution, shared by the plan
view (Model_View) and the section view (SectionView)."""

from __future__ import annotations


def block_payload(event):
    """The decoded ``MIME_BLOCK`` payload ``{"id", "path"}``, or None."""
    from .mime_types import MIME_BLOCK
    md = event.mimeData()
    if not md.hasFormat(MIME_BLOCK):
        return None
    import json
    try:
        payload = json.loads(bytes(md.data(MIME_BLOCK)).decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        return None
    return payload


def resolve_block_drag(sc, payload):
    """Resolve *payload* for a drag over *sc*.

    A library-only leaf is parsed into a temporary, unregistered
    definition (nothing is loaded on hover).

    Returns:
        ``(definition | None, pool, refusal reason | None)`` — *pool* is
        ``{id: definition}`` of the temporary file's definitions ({} when
        the block is already in the project).
    """
    from . import block_library
    reg = sc.block_registry
    defn = reg.get(payload["id"])
    pool: dict = {}
    merged = None
    if defn is None and payload.get("path"):
        loaded = block_library.load_block_file_with_bundle(payload["path"])
        tmp, bundled = loaded if loaded else (None, [])
        pool = {d.id: d for d in [tmp, *bundled] if d is not None}
        defn = tmp
        if tmp is not None:
            # The load's own merge rule: project copy wins for bundled
            # deps, the file's definition for its id (D11).
            merged = reg.merged_with_file(bundled, tmp)
    if defn is None:
        return None, pool, "This block can't be read"
    host = getattr(sc, "_editing_block_id", None)
    if reg.would_cycle(host, defn.id, merged):
        host_name = getattr(reg.get(host), "name", None) or "this block"
        if defn.id == host:
            return defn, pool, block_library.LOOP_REASON.replace(
                "a block", host_name, 1)
        return defn, pool, (f"{defn.name} contains {host_name} — "
                            f"{block_library.LOOP_REASON}")
    # hatch D-A34 / LT3-2 / LT5 Q12 / schematics D-S3: never a symbol.
    from .capabilities import place_refusal
    return defn, pool, place_refusal(defn)
