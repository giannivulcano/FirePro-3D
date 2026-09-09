# Audit Tooling — Census 2026-09-09

Baseline tag: `v-pre-audit`. Tests collected: **4293** (`pytest --collect-only -q`). No `from X import *` anywhere (vulture dead-code confidence not blinded).

Tools were **absent** from venv/global/pipx at probe time; installed into the working venv (user-approved) for this run:
`ruff 0.16.6`, `vulture 2.16`, `radon 6.0.1`, `pylint 4.0.8`, `deptry 0.25.1`, `pydeps 3.0.8`.

| Tool | Status | Output | Notes |
|---|---|---|---|
| ruff | ✅ | `ruff.txt` | 1032 lint errors, 737 auto-fixable |
| vulture | ✅ | `vulture.txt` | 349 @≥60%, 6 @100% |
| radon cc | ✅ | `radon_cc.txt` | avg A(4.06); many D–F functions |
| radon mi | ✅ | `radon_mi.txt` | ~15 files at C(0.00) |
| pylint dup | ✅ | `pylint_dup.txt` | 13 duplicate blocks (needed `PYTHONUTF8=1` — cp1252 crash) |
| deptry | ✅ | `deptry.txt` | 4 unused deps, 1 transitive (needed root-scoped run) |
| pyright / mypy | ❌ gap | — | not installed (pyright needs Node); F821 via ruff partly covers undefined-name |
| pydeps | ⚠ not run | — | installed; graph run deferred (needs graphviz for output; `--show-cycles` only) |
| cloc / tokei | ❌ gap | — | absent; line counts via `git ls-files | wc -l` instead |

## Coverage gaps
- **No type-checker** (pyright/mypy): possibly-undefined / missing-attribute bugs beyond ruff F821 are uncovered.
- **pydeps circular-import scan not run** — layering/cycle findings absent this pass.
- **cloc absent** — size numbers are raw line counts, not code-vs-comment split.

## Host/architecture notes (capability profile match)
Python single-package, local native venv (`D:\Custom Code\FirePro3D\venv`), PowerShell host — matches skill profile. No `[audit-gap]` self-task filed. Windows-specific tool snags (deptry arg parsing, pylint cp1252) worked around, not gaps.
