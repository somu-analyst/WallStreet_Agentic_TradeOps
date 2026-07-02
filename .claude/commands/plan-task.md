---
description: Orchestrator — decompose a big ask into PLAN.md subtasks (plan only, no code)
argument-hint: <the big task in one line>
allowed-tools: Read, Edit, Grep
---
Decompose, don't implement: `$ARGUMENTS`

1. Restate the goal in one line and define "done" (observable acceptance criteria, not vibes).
2. Locate the code it touches via CLAUDE.md's map (use `/map` logic — never read whole big files).
3. Split into the smallest independently-verifiable subtasks, each sized to fit ONE `/task-loop`
   iteration (< half a context window). Mark blockers as `(gated: …)` and user-side work `(user)`.
4. For each subtask write one `- [ ]` line in `docs/PLAN.md` § Open tasks: task — why / acceptance
   criteria. Order by dependency, ungated first.
5. Report the queue as a short table (subtask · gate · verify-by) + rough token impact per
   CLAUDE.md's token-aware rule. Then STOP — implementation happens via `/task-loop`.
