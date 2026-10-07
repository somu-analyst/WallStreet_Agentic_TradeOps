# Jev: reference notes

Status (2026-10-05): **not in use.** No code calls Jev, and the key vault has no Jev or TypeSafe
key. Keep this file up to date; add a use case here only once it is mapped to a real place in
our code and validated against our history.

## What it is

A fast, cheap decision model that picks one option from a list you define, and returns a
probability for each. Built for classification and routing, not general text generation.
Source poster: "12 agentic use cases for Jev" (shared by the user, 2026-10-05).

## The 12 patterns and where they could fit here

| # | Pattern | What Jev decides | Candidate in our code | Status |
|---|---|---|---|---|
| 1 | Browser next action | Click / type / stop | none (no browser agent) | not applicable |
| 2 | Model routing | Cheap model vs frontier model | `_llm_chat` provider choice; Gemini delegation hook | candidate |
| 3 | Agent loop control | Continue / retry / ask user / stop | none | not applicable |
| 4 | Tool and subagent selection | Search / code exec / subagent | none | not applicable |
| 5 | Prompt guardrail | On-topic / off-topic / jailbreak | Telegram free-text `ai_chat_handler` input | candidate |
| 6 | Output verification | Accept / review / reject a draft | LLM-written reports (`/insight`, `/desk`, `/why`) | candidate |
| 7 | Extraction verification | Is the field supported by the source? | `_income_stmt` / `/sankey` figures from filings | candidate |
| 8 | Confidence-gated review | Auto-run vs human queue | `/hiprob` POP gate; alert triggers | candidate, needs calibration first |
| 9 | Ticket triage and routing | Category / urgency / owner | none | not applicable |
| 10 | Live stream scoring | Breaking / useful / noise per post | `/breaking`, `/feed`, news alerts | candidate |
| 11 | Retrieval reranker | Score each passage for relevance | RAG-style lookups (none yet) | not applicable |
| 12 | Memory promotion gate | Promote / discard a lesson | `narrative_checks`, memory files | candidate |

## Rules before any Jev use case goes live

1. Pick one use case, map it to one function, and state the expected output in plain words.
2. Measure Jev against labelled history from our own DB: hit-rate vs a baseline, not a demo.
3. Check calibration. Pattern 8 depends on probabilities being honest, so measure that before
   setting a threshold.
4. Use walk-forward when Jev's threshold is a tuned parameter (see CLAUDE.md).
5. Never let Jev place or size a trade on its own. It can label or route; humans and the
   existing risk limits decide.

## Keys

No key is set. Adding one follows the vault process in CLAUDE.md (`api_keys.env` next to the
bot, merged into `api_keys.enc`). Do not paste keys into chat.
