---
description: Loop-engineering — pick next task from docs/PLAN.md, implement, verify, commit, tick, repeat
argument-hint: [N iterations or task keyword] (default: 1 iteration)
---
Run the engineering loop on `docs/PLAN.md`. Invoking this command IS the authorization to commit
each completed iteration to `main`. One iteration =

1. **Pick** — read `docs/PLAN.md` § Open tasks; take the FIRST unchecked `- [ ]` task, or the one
   matching `$ARGUMENTS` if a keyword was given. Skip tasks marked `(user)` or `(gated: …)` whose
   gate hasn't cleared — say why you skipped.
2. **Frame** — restate the task in one line + its acceptance criteria. If it's ambiguous, needs a
   user decision, or needs data we don't have → STOP and ask instead of guessing.
3. **Implement** — surgical edits, house rules apply (CLAUDE.md wins): edit
   `telegram_bot_optimized.py` / `dashboard.py` directly, no patch scripts, `_pipe_table` for bot
   tables, never touch secrets.
4. **Verify** — `python -m py_compile` every touched file; for anything signal-shaped, "test" means
   backtest vs DB history (hit-rate + avg fwd vs baseline, per CLAUDE.md § Signal validation), not
   "it runs". Record the actual verify output.
5. **Commit** — one atomic commit per iteration, only this task's files:
   `loop: <one-line task summary>` (+ the standard co-author trailer).
6. **Tick** — mark the checkbox `- [x]` in PLAN.md (append ` — done <YYYY-MM-DD>, <commit>`); add a
   one-liner to `docs/LOG.md` (what / how verified / what remains).
7. **Continue or stop** — if `$ARGUMENTS` requested more iterations AND context is under ~50%,
   loop to step 1. Otherwise stop and report a compact table: task · commit · verify result · next.

Hard stops (end the loop immediately, report why): destructive/irreversible operations, anything
touching secrets or pushing to remote, a task that changes scope, or context near ~50% (write the
recap to LOG.md/NEXT.md first so the next session resumes cold from git + docs).
