"""Centralized asset path resolution for graphics and other resources."""

import os

# Directory containing this file (firepro3d/)
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

# Root of the graphics assets
ASSETS_DIR = os.path.join(_PACKAGE_DIR, "graphics")


def asset_path(*parts: str) -> str:
    """Build an absolute path under firepro3d/graphics/.

    Args:
        *parts: Path components relative to graphics/.
            e.g. asset_path("fitting_symbols", "tee.svg")

    Returns:
        Absolute path to the asset file.
    """
    return os.path.join(ASSETS_DIR, *parts)
