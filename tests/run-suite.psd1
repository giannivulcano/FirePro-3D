# Suite config for the /todo plugin's shared/run-suite.ps1 (the VC6 full-suite gate).
# Owns the chunk layout and the isolate list (docs/specs/test-harness.md Invariant 8 links here).
@{
    # Absolute: worktrees have no venv, and `venv/Scripts/activate` resolves to a foreign venv.
    Python     = 'D:/Custom Code/FirePro3D/venv/Scripts/python.exe'
    # One process per chunk; a single process is memory-killed.
    Chunks     = @(
        'tests/test_[a-d]*.py'
        'tests/test_[e-l]*.py'
        'tests/test_[m-r]*.py'
        'tests/test_[s-t]*.py'
        'tests/test_u*.py'
        'tests/test_[v-z]*.py'
    )
    # Known native-crash loci (todo_open "Full-suite native crashes split the chunked VC6 run"),
    # each run in its own process until root-caused.
    Isolate    = @(
        'tests/test_block_drag_drop.py'
        'tests/test_block_editor_ribbon_tab.py'
        'tests/test_block_open_dialog.py'
        'tests/test_dynamic_input_parity.py'
        'tests/test_manip_griphandle_note_parity.py'
        'tests/test_opening_ribbon.py'
        'tests/test_sb1c_mainwindow.py'
        'tests/test_sb3_mainwindow.py'
        'tests/test_scene_tools.py'
    )
    Markers    = 'not perf'
    PerfMarker = 'perf'
    # C: is near-full on the dev machine: pytest temp files and runner scratch live on D:.
    Env        = @{ TMP = 'D:/Custom Code/FPD/pytest-tmp'; TEMP = 'D:/Custom Code/FPD/pytest-tmp' }
    Scratch    = 'D:/Custom Code/FPD/run-suite'
    TimeoutSec = 1800
}
