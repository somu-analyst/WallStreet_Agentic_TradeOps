---
description: Parallel fan-out — answer a codebase/data question via read-only subagent search, conclusions only
argument-hint: <question about the codebase, DB, or signals>
---
Answer with evidence, without burning main-context on file dumps: `$ARGUMENTS`

1. Check CLAUDE.md's map + `docs/STRATEGY_BUILD.md` first — if they already answer it, stop there.
2. Otherwise launch ONE read-only **Explore** subagent (search breadth: medium) scoped to the
   question; for DB questions have it query `US_data.db` read-only (`file:...?mode=ro`). Never
   spawn more than two agents; never let them edit files.
3. Relay the conclusion in ≤10 lines: answer first, then `file:line` evidence, then caveats
   (thin samples, stale snapshot dates, NULL columns).
4. If the answer changes what we should build, propose the `- [ ]` line for `docs/PLAN.md` —
   don't add it without saying so.
