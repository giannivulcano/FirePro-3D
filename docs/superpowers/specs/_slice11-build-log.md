# Slice 11 build log (branch-local; delete before merge)

- **C1** `59f886281fc8b0375066b7027a74053ac9e18d36` — created feature_placement_controller.py + __init__ wiring.
  Moved: `_find_wall_at`, `_offset_along_wall` (transitional shells, go bare in C2),
  `_press_opening`, `_press_door`, `_press_window` (scene shells). Targeted set: 51 passed, 0 failed.
- **C2** `90bf98f2453e62499921331ebee599ade31d7572` — moved `_move_opening`, `_move_door_window`,
  `_refresh_opening_ghost` (scene shells), `_clear_opening_ghost` (transitional shell → bare in C3),
  `_cycle_opening_alignment`, `_sync_opening_state_to_template` (scene shells). `_find_wall_at`/
  `_offset_along_wall` shells dropped (bare). Targeted set: 51 passed, 0 failed; import smoke clean.
- **C3** `ed54d5886b0266c558d59c6c2c73a7234bc10ac5` — added `enter(template)` + `clear(new_mode)`;
  set_mode surgery (block → enter/clear); `_clear_opening_ghost` bare; new
  tests/test_feature_placement_slice_parity.py. Targeted set (6 files + wall sibling): 59 passed,
  0 failed. clear() RED-demo verified RED (1 failed) then green after restore. hasattr-trap grep:
  none in production code. Dispatch tables untouched.
