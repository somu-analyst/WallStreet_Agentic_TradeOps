---
description: Router — decide Claude vs cheaper lane (Gemini/local agent) and emit a paste-ready handoff prompt
argument-hint: <task to route>
allowed-tools: Read, Grep
---
Route this task to the right lane per `.claude/rules/workflow.md`: `$ARGUMENTS`

1. Classify it: hard/multi-file/security/signal-logic → **Claude lane** (stay here). Bulk research,
   summarizing, doc drafts, mechanical/repetitive edits → **cheap lane** (Gemini / Cline / local).
   Consider current usage too (if throttled or near limits, bias to the cheap lane).
2. If **Claude lane**: say so in one line and either start it or queue it in `docs/PLAN.md`.
3. If **cheap lane**: emit a self-contained, paste-ready prompt for that tool containing exact file
   paths + line anchors, the constraints that matter (no patch scripts, canonical files, date
   format, secrets rules), the acceptance criteria, and what to hand BACK (diff or file list) so
   Claude can verify cheaply. Never include secrets or DB contents in the handoff.
4. One-line justification of the routing choice (what it saves / what it risks).
