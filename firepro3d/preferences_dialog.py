"""Back-compat shim — real home is ``firepro3d.settings.panes``.

All pane classes and constants have moved to ``firepro3d.settings.panes``.
This module re-exports everything so existing importers keep working without
any changes.  ``PreferencesDialog`` has been removed (replaced by the new
Settings dialog; see ``docs/specs/settings-dialog.md``).
"""
# ruff: noqa: F401
from PyQt6.QtCore import QSettings  # re-exported so monkeypatchers can still patch this module

from firepro3d.settings.panes import (  # noqa: F401
    SettingsPane,
    UXPane,
    SnappingPane,
    UnitsPane,
    ImportPane,
    GeneralPane,
    UIPane,
    ProjectInfoPane,
    _QSETTINGS_ORG,
    _QSETTINGS_APP,
    _SNAP_TYPES,
    _FACTORY_DEFAULTS,
    _UNIT_OPTIONS,
    _DOCK_ITEMS,
    _DATA_ROOT_KEY,
)
