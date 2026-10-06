"""Block Editor capability frames (hatch D-A32 tile, linetypes LT4 repeat)."""
from __future__ import annotations


def frame_for(scene, kind: str):
    """The frame item for *kind* (``"tile"`` / ``"repeat"``)."""
    from .tile_frame import TileFrameItem
    return TileFrameItem(scene)
