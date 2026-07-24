# Scraping tools — reference (2026-07-24)

Picked for: occasional JS-rendered pages (e.g. tradingkey.com's Star Investors tool,
which renders its data client-side and returns nothing to a plain HTTP fetch). Criteria:
most-starred, actively maintained, **universal** (not single-site scrapers).

## Shortlist

| Tool | Stars | What it is | Status in this repo |
|---|---|---|---|
| **Firecrawl** | ~155k | The most-starred of the bunch. "API to search, scrape, and interact with the web at scale" — covers ~96% of the web incl. JS-heavy pages, no proxy hassle. Scrape→markdown/HTML/screenshot/structured JSON, click/scroll/type before extracting, crawl a whole site, map all URLs on a site, autonomous "agent" mode. Cloud API (firecrawl.dev) **or self-host** (AGPL-3.0, own Docker stack — no per-call cost, no data leaving our machine). | ❌ Not installed. Self-host = own compute (handles the proxy/anti-bot/rendering complexity for us); cloud = simplest but external API call + cost per page. |
| **Crawl4AI** | ~75k | Built ON TOP of Playwright. Adds LLM-ready output: turns any page into clean structured Markdown (headings/tables/code preserved), CSS-selector or LLM-driven extraction, deep-crawl strategies (BFS/DFS/best-first), stealth mode, Docker/API server option. Fully self-hosted, no cloud dependency. | ❌ Not installed. `pip install crawl4ai` (pulls Playwright as a dep — no conflict since we already have it). |
| **Playwright** | ~92k | Microsoft-maintained browser automation (Chromium/Firefox/WebKit, one API). Renders JS, waits for content, screenshots, full page interaction. The building block Crawl4AI (and Firecrawl's self-host mode) sit on top of. | ✅ Already installed + Chromium browser verified working (`python -c "from playwright.sync_api import sync_playwright..."` launches clean). |
| **Crawlee (Python)** | growing | Playwright-based crawler framework for multi-page/multi-site jobs (queueing, retries, storage). | Not installed — only worth it if we start scraping many pages/sites on a schedule, not one-off lookups. |
| Scrapy | huge, mature | Python's default crawling framework — **no JS rendering**. Built for large structured crawls of static/API-backed sites. | Not installed — wrong tool for JS-rendered single pages like TradingKey. |

## Recommendation

- **One-off lookup of a single JS-rendered page** (e.g. "what does TradingKey actually show right now") → **Playwright** directly. Already installed, zero extra deps, ~10 lines of script.
- **Repeated/ongoing scraping where we want clean Markdown/structured output** (e.g. periodically pulling a page's data into the DB, or feeding scraped content to an LLM narrative) → **Crawl4AI**. Adds real value over raw Playwright: async, gives you structured output instead of raw HTML, has an extraction-strategy API instead of hand-rolled CSS parsing.
- Skip Scrapy/Crawlee for this project unless we start crawling many pages/sites on a recurring schedule — both are overkill for single-page lookups.

## Practical notes

- `WebFetch` (the built-in tool) reads static HTML and converts it to Markdown via a small
  model — it cannot click "load more" or run JS, and on this page its HTML→Markdown pass
  also silently dropped the investor grid, so two fetch attempts on `/tools/star-investors`
  both came back "No Data" even though the data was there in the raw HTML the whole time.
- **Correction (2026-07-24, after actually checking):** TradingKey's Star Investors page is
  **NOT JS-gated** — it's server-rendered (Next.js SSR, `Server-Timing: ssr` header), and the
  full investor list ships as a plain JSON blob inside the initial HTML
  (`"investorData":{"list":[...],"total":88}`). A plain `curl`/`requests.get()` — **no
  Playwright, no browser at all** — returns it directly, and pagination is a simple
  `?page=N` query param (confirmed pages 1–15, all 88 investors pulled this way). This is
  why Tier 1 of the "recon with Playwright" plan turned out unnecessary in the end: the
  network-interception step wasn't needed once plain HTML was actually inspected properly.
  Lesson: always check the raw HTML directly before reaching for a browser-automation tool —
  "renders client-side" was an assumption, not a verified fact, and cost an extra step.
- Playwright still needs its browser binaries downloaded once if it IS needed for a truly
  JS-only site: `playwright install chromium` (~300MB). Already done in this environment.
- If we do wire Crawl4AI/Firecrawl in for a genuinely JS-gated site later, keep it a
  manual/on-demand script (`tools/scrape_*.py`), not something the bot/dashboard calls
  live — page layouts drift and a scraper embedded in a hot path becomes a silent-failure risk.

## Current call for TradingKey specifically

Not wired in as a scraper, and doesn't need to be. Cross-referenced all 88 names from
TradingKey's Star Investors roster against SEC EDGAR and folded the real 13F filers into
our EXISTING `_EDGAR_FUNDS` tracker (dashboard.py, 🏆 Legendary Investors → 📜 13F History) —
grew from 14 → 40 funds, every CIK verified directly against SEC EDGAR company search. One
engine, real filings, nothing to scrape or maintain against their page layout. The one-time
`requests` pull (see above) was only ever needed to get the name list to cross-reference —
not a permanent scraper.
