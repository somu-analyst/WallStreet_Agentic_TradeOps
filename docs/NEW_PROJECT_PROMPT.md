# Kickoff prompt — hosted multi-user front end

_Paste the block below into a fresh Claude Code session, in a NEW empty repo._
_Written 2026-08-22 from the measured state of NYSE_DATA. Everything marked MEASURED was
actually run — don't re-derive it, and don't trust anything here that isn't marked._

---

## The prompt

```
I'm starting a new project: a multi-user, cloud-hosted web front end for an options
analytics engine I already have. Do NOT write code yet — I want the plan first.

WHAT ALREADY EXISTS (do not rebuild any of this)
  Repo: C:\Users\srini\Options_chain_data\NYSE_DATA
  - telegram_bot_optimized.py (~40k lines) — THE engine: scanners, GEX, spreads, wheel,
    hiprob ensemble, signal template, tax, paper book. Runs as a Telegram bot.
  - dashboard.py (~26k lines) — Streamlit UI over the same engine, single-owner.
  - NYSE_OpenBB.py — nightly EOD capture: option chains for ~733 tickers.
  - SQLite at C:\Users\srini\Options_chain_data\US_data_OpenBB.db — 4.70 GB,
    6.37M chain rows, growing ~2-3 GB/yr.
  This engine is the source of truth. The new project REUSES it. Forking it guarantees
  the two drift and the signal logic gets duplicated.

WHAT I WANT
  A web app several people can log into. Free hosting (Oracle Cloud Always Free:
  2 OCPU / 12 GB ARM / 200 GB, no expiry). HTTPS. Real accounts.

THE DECISION THAT DRIVES EVERYTHING — ask me this before planning anything else:
  Do other users see THEIR OWN positions, or are they read-only viewers of MY book?
  - Read-only viewers  -> no data-model change; auth + a proxy is most of the work.
  - Their own book     -> every table (trades, paper_trades, watchlist, app_settings)
                          needs a user_id, and every query in a 40k-line engine assumes
                          a single owner. This is perhaps 20x the first option.
  Do not guess. The answer changes the entire architecture.

MEASURED FACTS (already proven — don't re-test)
  - yfinance is UNUSABLE from a datacenter IP: Yahoo flags within ~50 requests, and the
    nightly lane makes ~730. Fixed already: NYSE_PRICE_SOURCE=finnhub matched the real
    stock_daily closes at 0.000% mean AND max difference across 8 tickers. Finnhub free
    tier is 60 calls/min => ~12 min for 730 tickers.
  - Option chain capture works on BOTH paths: primary OpenBB (SPY 3,105 rows / 6.7s)
    and the CBOE CDN fallback (same rows). Whether a DATACENTER IP is blocked is still
    UNKNOWN — run NYSE_DATA/cloud_smoke.py on the VM; gate C answers it and prints
    "authoritative" only when it detects a cloud host.
  - ARM is fine: every dependency is pure-Python or ships an aarch64 wheel. OpenBB is
    pure Python.
  - Secrets: the vault key derives from user|hostname, so it will NOT decrypt on a new
    host unless KEYVAULT_PASSPHRASE is set. That env var is the migration path.
  - Resources are not a constraint: bot is 392 MB resident; DB is 4.70 of 200 GB.

CONSTRAINTS
  - Free tier only. No paid services, no paid proxies.
  - SQLite stays unless you can show a concrete reason: one writer (the EOD lane) and a
    few readers is well inside its range. Multi-user READ access does not create
    concurrent writers. Enable WAL.
  - Never expose the book publicly. It contains real positions, cost basis and tax data,
    and the same host holds the API key vault and Telegram token.

WHAT I WANT FROM YOU FIRST
  1. Ask me the read-only-vs-own-book question above.
  2. Then propose an architecture: how the web app reaches the engine (import in-process
     vs a small API the bot exposes), where auth lives, and what the first vertical slice
     is — ONE page, end to end, logged in, real data.
  3. Tell me what you would NOT build yet, and why.
Do not start coding until I've answered question 1.
```

---

## How to start it (my advice)

**New repo, not a branch.** Different lifecycle, different deploy target, different
dependencies. This repo stays the engine of record.

**Reuse the engine; don't copy it.** Two ways, in order of preference:

1. **Import it** — the new app runs on the same box and does `import telegram_bot_optimized
   as engine`. Zero duplication, and it's already proven to import headlessly (smoke test
   gate E). Downside: one process pulls in a 40k-line module.
2. **Thin API** — the bot exposes a small read-only HTTP surface, the web app calls it.
   Cleaner boundary, but it's a second service to keep alive on a free VM.

Start with (1). Move to (2) only if you hit a real reason.

**Do the smallest vertical slice first.** One page — login → your positions → log out —
running on the VM over HTTPS. Not five pages locally. The slice flushes out auth, sessions,
deployment and the engine import all at once, which is where the surprises live.

**Order the work by what can kill the project:**

1. Run `cloud_smoke.py` on the VM. If the chain capture is blocked from a datacenter IP,
   stop — everything else is moot.
2. Answer the multi-user question. It decides whether this is a UI project or a
   data-model project.
3. Auth and HTTPS before any feature. Retrofitting auth is how books leak.
4. Only then, pages.

**Keep the tracker discipline.** It's the reason nothing in this project gets lost. Copy
`tools/tracker_io.py` and the "log the question before you answer it" rule.

## Traps already paid for — don't re-learn these

- **Verify numbers, not that they render.** The trend columns rendered perfectly and were
  wrong for every US ticker, because a stale DB series shifted every window.
- **A silent `except` around a fallback hides a dead fallback.** The CBOE throttle-buster
  returned `None` for every ticker for weeks — a `date > datetime` TypeError swallowed by a
  bare handler. It only mattered on the night it was needed.
- **`curl_cffi` carries its own CA bundle** and fails cert verification unless the engine's
  SSL fix is imported first.
- **Streamlit grids are canvas.** `<th>` and `[role=columnheader]` are the accessibility
  layer; CSS cannot style what you see.
- **Test the path the product uses.** A gate that tested the fallback said nothing about
  the primary, and I nearly reported the wrong conclusion twice.
