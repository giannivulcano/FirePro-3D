"""Harness guard (SB1b D5): a MODULE-scoped fixture -- built before any
function-scoped isolation fixture -- must not resolve the real block library,
since MainWindow startup runs ``system_library.migrate_user_library()``."""
import os

import pytest


@pytest.fixture(scope="module")
def _library_seen_by_module_fixture():
    from firepro3d import app_data
    return app_data.block_library_dir()


def test_module_scoped_fixture_sees_an_isolated_block_library(
        _library_seen_by_module_fixture):
    from firepro3d import app_data
    real = os.path.normcase(os.path.abspath(app_data.default_root()))
    seen = os.path.normcase(os.path.abspath(_library_seen_by_module_fixture))
    assert not (seen == real or seen.startswith(real + os.sep)), seen
