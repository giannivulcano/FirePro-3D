# TODO — split into two files

This file was split on 2026-09-02 to keep the working task list lean:

- **`todo_open.md`** — active/backlog tasks (the `/todo` skill reads this for selection).
- **`todo_closed.md`** — append-only archive of completed tasks with their build notes.

On completion, the `/todo` skill **moves** a task from `todo_open.md` to `todo_closed.md`
(it no longer flips `[x]` in place). New tasks and follow-ups go into `todo_open.md`.
