---
description: Evaluator-optimizer — review the last loop commit(s) against house rules, fix small issues
argument-hint: [N commits to review] (default 1)
allowed-tools: Read, Edit, Grep, Bash(git diff*), Bash(git log*), Bash(git show*), Bash(git add*), Bash(git commit*), Bash(python -m py_compile*), PowerShell
---
Review the last `$ARGUMENTS` (default 1) commit(s) as a skeptical second engineer, then optimize.

1. `git log --oneline -N` + `git show --stat` to scope; read ONLY the changed hunks (`git diff HEAD~N`).
2. Evaluate against the repo's failure modes, not style: MM-DD-YYYY date sort trick used for date
   ordering? `not (iv > 0)` NaN guards? `_pipe_table` (not hand-rolled grids) for bot tables?
   emoji in column 0 only? dead columns (`vol_rank_*`, `money_coi_*`) untouched? secrets never
   printed/committed? `datetime.utcnow()` avoided? Telegram `<pre>` ≤28 chars? errors swallowed
   where they should surface?
3. Verdict per finding: **fix now** (small, safe) / **queue** (real but bigger → add `- [ ]` to
   `docs/PLAN.md`) / **fine** (say why). No rewrites, no scope creep.
4. Apply the fix-now items, `py_compile` touched files, commit once: `review: <what was tightened>`.
5. Report: finding · verdict · action, most severe first. If nothing survived scrutiny, say so
   plainly — a clean review is a valid outcome.
