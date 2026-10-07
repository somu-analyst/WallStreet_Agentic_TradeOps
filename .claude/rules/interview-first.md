# Interview before building

Standing prompt (from the user, 2026-10-05):

> "I'm about to start this project. Interview me until you have 95% confidence about what I
> actually want, not what I think I should want."

The gap between what the user asks for and what they actually want is where most failed
projects begin. Close that gap before writing code or running analysis.

## When to apply

- A new feature, project, scanner, report, dashboard page, alert, or research question with
  more than one reasonable reading.
- Any ask where the output is something the user will look at, act on, or share.
- Any ask touching money, positions, or live systems (bot, cloud, scheduled tasks).

Skip it for small, unambiguous edits (typo, rename, one-line fix with a clear target) and for
follow-ups inside work already agreed.

## How

1. Ask the questions that would change the build: goal, who reads it, what "done" looks like,
   what to leave out, constraints (data available, budget, timing), and what to do on failure.
2. Use AskUserQuestion for 2-4 concrete choices. Use plain questions for open ones.
3. Keep asking until you could explain the request back in one paragraph and the user agrees
   with it. Stop at about 95% confidence, not at 100%.
4. Only then plan and build. Log the agreed scope to the tracker first (CLAUDE.md rule).

## Still applies

- Log every question and idea to the tracker before answering (CLAUDE.md).
- Validate a signal before shipping it; an interview does not replace the walk-forward rules.
- Do not interview in circles: if the answer is already in the code, the tracker, or the
  conversation, read it instead of asking.
