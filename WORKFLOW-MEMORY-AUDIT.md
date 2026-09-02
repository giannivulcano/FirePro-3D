# WORKFLOW-MEMORY-AUDIT — /todo skill vs project memory (DRAFT for review)

Audited: `~/.claude/skills/todo/SKILL.md` + `CLAUDE.md` against all 46 `feedback_*.md`
memories (and process-bearing `project_*` notes referenced by them). Goal: bake recurring,
generalizable *process* lessons into the skill; leave project-specific technical facts in memory.

The skill already encodes a lot (Ground/Forge/Reuse/Account hooks, tiered phases,
smoke-test-gates-mark-done, reuse-sweep buckets, verify-agent-verdicts-vs-session,
wrap-up follow-ups + lessons routing). The additions below are the genuine gaps.

---

## Proposed additions (ranked by leverage)

### 1. Verify subagent ground-truth after every final report  [source: feedback_verify_subagent_branch_state, feedback_subagent_report_numbers_stale, feedback_verify_subagent_api_shapes, feedback_subagent_incremental_findings]
- Gap: Phase 5 chains `subagent-driven-development` / `executing-plans` but never says "distrust the subagent's DONE report." Four independent memories document the same class of failure: reports that are premature/uncommitted, quote stale numbers, or assert phantom APIs — and 0-byte transcripts when an agent dies. None of this is in the skill.
- Target: Phase 5 (Implement), new bullet under **During implementation**; plus one line in the Large-tier subagent brief guidance.
- Proposed wording:
  > **Trust subagent reports only after verifying ground truth.** A final "DONE" report is a point-in-time snapshot, not proof. After any substantial subagent task: run `git log --oneline -1` + `git status` (did the commit actually land?), re-run the acceptance/gate tests yourself, and if numbers in the report look off, re-derive them from the committed code rather than believing the report. In long review/analysis briefs, instruct the agent to **write findings incrementally** (final message = verdict only) — a died agent's transcript can be 0 bytes and unrecoverable. When briefing an implementer with specific field/method names, **grep them in the real module first** — a wrong API shape yields a getattr-tolerant impl whose tests pass against a phantom shape.
- Why it generalizes: subagent-report-vs-reality drift is orchestrator-universal, independent of FirePro3D.

### 2. Holistic cross-task seam review before handing to smoke test  [source: feedback_holistic_review_after_subagent_builds]
- Gap: Phase 5 Large runs per-task subagents; Phase 6 step 1 runs `verification-before-completion`. Nothing dispatches a *whole-branch, seams-only* review. The memory has two data points (~3 real cross-task blockers per multi-subagent build) that per-task reviews structurally cannot see.
- Target: Phase 5 (Implement), Large tier — new final step before advancing to Phase 6.
- Proposed wording:
  > **Large / multi-subagent builds:** after all tasks land, dispatch one final whole-branch reviewer prompted **"cross-task integration seams only"** (shared constants/keys synced across modules, every output path exercises the new feature, spec acceptance-criteria sweep) — explicitly told to skip per-task re-review. Budget a fix round after it. Kill any background full-suite run before applying its fixes.
- Why it generalizes: contract mismatches live in the composition, not any single diff — true of any parallelized implementation.

### 3. Live smoke test / running app is the real gate — headless green ≠ done  [source: feedback_trust_live_app_over_code_reasoning, feedback_parallel_system_arbitration_smell, feedback_test_real_entry_point, feedback_grep_repo_after_symbol_rename, feedback_full_suite_before_done]
- Gap: Phase 6 has a smoke-test step, but the skill never states *why headless is insufficient* or the recurring blind spots (focus/dispatch/render bugs, startup-only import breakage, cross-test resource crashes, live-only interaction-seam bugs). Five memories converge here. It also never says "when the app contradicts your code reading, instrument the app and trust it."
- Target: Phase 6 step 2 (Smoke test) — expand; plus one line in Phase 5.
- Proposed wording (append to Phase 6 step 2):
  > Headless-green is not done. Whole classes of bug are invisible to the suite: focus/event-dispatch/render behavior (test via the **real entry point** — a shown view + posted events, not by calling handlers), startup-only import breakage (**grep the whole repo for any renamed/removed symbol, then launch-smoke `python main.py`** — the suite never runs the launch path), cross-test resource crashes (**run the full suite once, not just feature tests**), and live-only bugs at any new-system-vs-legacy arbitration seam (budget heavy live smoke there). **When the running app contradicts your code reading, trust the app** — add a temporary live readout at the decision point and read ground truth off the user's screen; a file edit does not reload a running process (have them fully restart).
- Why it generalizes: "the running program is the source of truth over static reasoning" is a universal debugging/verification discipline.

### 4. Guard tests must exercise behavior and assert ground truth — not source text or the impl's own output  [source: feedback_functional_over_source_inspection_tests, feedback_assert_ground_truth_not_impl_output, feedback_no_observable_discriminates_refactor, feedback_synthetic_item_render_test_blindspot]
- Gap: Phase 2 captures "testing expectations" and Phase 6 step 1 verifies tests pass, but the skill is silent on *test quality*. Four memories document false-green tests: source-inspection guards, tests asserting `rotation()==angle` (the wrong internal value), tautological refactor tests where no observable discriminates old/new, and synthetic-stand-in render tests.
- Target: Phase 2 (testing expectations) and/or a short **Testing discipline** note usable by Phases 2/5/6.
- Proposed wording:
  > **Test quality (not just test presence):** a guard test must construct the scenario, drive the behavior, and assert **observable ground truth** — never assert source text (`inspect.getsource`), never assert the implementation's own internal value for convention-critical behavior (angle sign, handedness — assert "a +90° turn swings this corner up"), and use **real domain objects** in render/paint tests, not synthetic stand-ins. Prove each guard goes RED with the fix reverted. If a refactor has **no observable that discriminates old vs new**, say so and verify via a genuinely divergent path rather than keeping a tautological test.
- Why it generalizes: false-green test patterns are language/framework-agnostic verification traps.

### 5. Stop-and-clarify when smoke-fixes cascade (whack-a-mole)  [source: feedback_smoke_fix_whack_a_mole]
- Gap: Phase 6 step 2 says route smoke-test issues to `systematic-debugging`, but never says *when to stop patching*. The memory: cascading fixes on one sub-feature (fix A→bug B→bug C) usually mean the intent is wrong or the piece needs a design pass.
- Target: Phase 6 step 2 — new sentence.
- Proposed wording:
  > If fixes on one sub-feature cascade (~2–3 non-converging patches, each spawning the next bug), **stop live-patching.** Re-clarify the actual intent (a quick question often surfaces a wrong-feature fork), then ship the solid core and file the fragile piece as a follow-up / design pass. Don't duct-tape the hard corner in the live session.
- Why it generalizes: cascade-detection is a universal signal that the problem is mis-scoped, not that the next patch is close.

### 6. Settle cross-cutting conventions BEFORE fan-out, not at wrap-up  [source: feedback_units_convention_before_fanout]
- Gap: Phase 1b settles *spec-change tier* and reuse, but not "if this task introduces a new category of cross-cutting convention (unit, format, naming), pin it before parallel work." Seven subagents drifted formats in one session because there was no convention to review against.
- Target: Phase 1b (add to the Reuse/spec-change step) — new sub-bullet.
- Proposed wording:
  > **Convention gate (before any fan-out):** if the task introduces a new *category* of cross-cutting convention (a displayed unit/format, a naming pattern, a shared key schema), settle it in the governing spec now and cite it in every implementer prompt. Reviewers can't enforce a rule with no home; conventions drift within a single session once work fans out across agents.
- Why it generalizes: any parallelized build that shares a convention needs the convention frozen upstream.

### 7. Validation-instruction hygiene: exact `cd` + which repo/worktree  [source: feedback_validation_cd, feedback_suite_runs_popup_windows]
- Gap: Phase 6 presents a smoke-test checklist but never says to specify *where* to run it. On a multi-worktree session the user tested old code from the wrong directory, wasting a round-trip.
- Target: Phase 6 step 2 (Smoke test) — new sentence.
- Proposed wording:
  > Every manual-validation instruction must state main-repo-vs-worktree explicitly and give the exact `cd` command (and venv activation if relevant) — on branch/worktree sessions the user will otherwise smoke-test the wrong code. If the suite pops real app windows, warn the user they'll look frozen and will self-close.
- Why it generalizes: any branch/worktree workflow risks the wrong-directory validation round-trip.

### 8. Performance criterion in reviews + refute perf theories with a minimal bench  [source: feedback_review_perf_criterion, feedback_performance_priority, feedback_perf_theory_needs_minimal_bench, feedback_user_observations_first_class_evidence]
- Gap: no phase mentions performance. Two memories: reviewers repeatedly missed O(n²)/unbounded-iteration freezes; and perf *fixes* built on unbenched theories wasted whole build cycles (three wrong theories died cheaply once benched).
- Target: Phase 5 review guidance / Phase 6 verification — one bullet.
- Proposed wording:
  > **Performance:** when a change iterates a large collection or does pairwise comparison, review for unbounded iteration / O(n²) at real-world scale (spatial/early filtering present?). Before building any perf *fix*, refute or confirm the mechanism with the smallest isolated A/B bench on real data — perf intuition is wrong more often than right, and an unbenched fix can regress. Treat the user's "where does the same thing behave fine?" observations as first-class differential evidence.
- Why it generalizes: O(n²)-at-scale and bench-before-perf-fix are general engineering disciplines. (The FirePro3D-specific `sceneBoundingRect`/`childItems` details stay in memory.)

### 9. Visual/print changes: mockup-first, house-style-first, plotted-artifact is the gate  [source: feedback_visual_grill_provisional, feedback_house_style_before_one_off_visual, feedback_plotted_pdf_is_visual_gate, feedback_serve_interactive_mockups]
- Gap: the skill has no handling for visual/style decisions. Four memories: grill answers about *looks* are provisional until real geometry is rendered; check for an existing house style before inventing one; and the plotted PDF (not the screen) is the acceptance gate. (Note: partially FirePro3D-flavored, but the *ordering* is generic.)
- Target: Phase 2/3 (visual decisions) — a short conditional note.
- Proposed wording:
  > **If the task involves a visual/style choice:** first check for an existing house style/theme and conform to it (don't invent a one-off); if none exists, present a rendered/interactive mockup on representative geometry before implementing — text/ASCII options under-specify and get reversed at first screenshot. For print/export-facing changes, the exported artifact at real scale (not the on-screen look) is the acceptance gate; they fail independently.
- Why it generalizes: mockup-before-build and conform-to-existing-style-before-inventing are general design-process rules. (Concrete tokens, `paper_export`, ~1/8"=1' stay in memory.)

---

## Already covered (brief)
- **Reuse sweep (REUSE/GENERALIZE/GAP), before design** → Phase 1b step 4 (feedback_reuse_sweep_before_building).
- **Verify agent verdicts against session-settled decisions** → Phase 1b step 4 (feedback_subagent_report_numbers_stale caveat, feedback_reuse_sweep_before_building).
- **Ground/Forge/Account leash hooks + spec-change tier** → Phase 1b + Phase 6 step 6 (feedback_todo_spec_hooks).
- **Smoke test gates mark-done + Account (don't finalize before user confirms)** → Phase 6 steps 2→3, 6 explicit ordering (feedback_phase6_after_smoketest).
- **Route smoke-test issues to systematic-debugging, don't guess** → Phase 6 step 2 (feedback_subagent_bugs partial).
- **Wrap-up follow-up-task review** → Phase 6 step 4 (feedback_wrapup_followups).
- **Lessons-learned routing to feedback/project/doc** → Phase 6 step 7.
- **Grill owns "what", brainstorming owns "how"; spec-only tasks stop at spec** → Phase 2/3 boundary + exit ramps (feedback_spec_vs_implementation — the "confirm before implementing" exit ramp exists, though it could be sharpened; judged covered).
- **Match working architecture / don't build parallel systems; grep for consumers during Ground** → Phase 1b Reuse hook + reuse-sweep (feedback_match_working_architecture) — substantially covered by Reuse.
- **Subagent-implementer bug rate / manual walkthrough of integration points** → covered by proposed #1 + #2 (feedback_subagent_bugs, subagent_targeted_tests_not_full_suite reconciles with full-suite-at-wrap-up in #3).
- **Question existing (LLM-scaffolded) code from first principles in spec sessions** → implicit in Forge orphan-gate grill + Phase 3 brainstorming (feedback_question_existing_code); borderline, not proposing a dedicated edit.

## Out of scope (project-specific — keep in memory, not the skill)
- **feedback_dimension_input_pattern** — `format_length`/`parse_dimension` + `QLineEdit`, never `QDoubleSpinBox`. FirePro3D API convention → belongs in units spec, not a generic skill.
- **feedback_pytest_pipe_masks_exitcode** — `pytest | tail` masks exit code; `${PIPESTATUS[0]}`; the suite's pre-existing 139/0xe0000001 crashes. Shell/env-specific. (The generic kernel — "verify the real exit code, reproduce pre-existing crashes on main" — is thin; folded lightly into #3's full-suite line, not its own addition.)
- **feedback_suite_runs_popup_windows** — offscreen QPA non-viable (VTK), zombie-window sweep via `Get-CimInstance`. FirePro3D/Qt/VTK-specific (the "give exact cd + warn about popping windows" kernel is in #7).
- **feedback_native_crash_evidence_first** — WER faulting module + exception code for silent native crashes. Windows/native-crash-specific debugging; lives fine in memory (evidence-before-hypothesis is generic but already implied by systematic-debugging).
- **feedback_artifact_attribution** — verify which item produces a screenshotted artifact before fixing. Real, but narrow visual-bug-triage; adjacent to #3, not worth its own skill line.
- **feedback_refactor_audit_1000_lines** — flag files >~1000 lines. Useful heuristic but a codebase-hygiene tripwire, not a /todo phase concern; keep in memory.
- **feedback_spec_dedup_note_misdiagnoses / feedback_spec_cross_module_tracing / feedback_verify_stale_spec_refs** — spec-authoring/spec-verification craft. Valuable, but they're grill/brainstorming-internal craft rather than orchestrator structure. (feedback_verify_stale_spec_refs' "offer skip-grill, verify-code when a complete approved spec exists" is a plausible Phase-2 exit-ramp tweak — noted as a candidate but not promoted; the existing exit ramps partly cover it.)
- **feedback_replacement_review_parity_vs_old_code** — port/replace tasks: brief the reviewer to diff against the OLD impl. Strong lesson; borderline generalizable. Judged review-brief craft rather than a phase; could fold one clause into #2 if desired, but excluded to keep #2 focused.
- **feedback_property_panel_over_dialog / feedback_port_prototype_not_rebuild** — FirePro3D UX pattern (property panel over modal) and "port the provided prototype, don't rebuild from prose." Project-specific (the reuse/match-architecture kernel of port_prototype is already covered by Phase 1b Reuse).
- **feedback_spec_dedup_note_misdiagnoses, feedback_grep_repo_after_symbol_rename** — grep-whole-repo craft; the actionable kernel of the latter is in #3 (launch-smoke + repo-wide grep).

---

### Note on selectivity
9 additions is deliberately at the upper bound; #1–#5 are the high-leverage core (subagent
verification, seam review, live-gate, test quality, whack-a-mole). #6–#9 are lower-frequency
but each closes a phase the skill is currently silent on (conventions, validation hygiene,
performance, visual). If trimming, drop #9 and #6 first (most FirePro3D-flavored).
