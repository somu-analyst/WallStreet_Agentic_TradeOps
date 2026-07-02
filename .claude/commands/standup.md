---
description: Session kickoff — read PLAN/LOG/NEXT + git, propose today's loop targets
allowed-tools: Read, Grep, Bash(git log*), Bash(git status*), PowerShell
---
Morning standup for this repo — orient, then propose, don't implement.

1. Read `docs/NEXT.md`, `docs/PLAN.md` § Open tasks, the newest `docs/LOG.md` entry, and
   `git log --oneline -8` + `git status`. Note anything uncommitted or half-done.
2. Check gates: which `(gated: …)` tasks have cleared (e.g. scn_* rows with t+5 outcomes in
   `signal_accuracy`, OpenBB `--compare` agreement days accumulated)? Which are still waiting?
3. Propose today's plan: 1–3 `/task-loop` targets that fit CLAUDE.md's session budget
   (~2–3 focused sessions, subtasks < half a context window), ordered by value; flag anything
   that should go to a cheaper lane via `/route`.
4. Output: a 5-line brief — where we left off · what unblocked · today's targets · what NOT to
   touch · one risk. Then wait for the user's pick.
