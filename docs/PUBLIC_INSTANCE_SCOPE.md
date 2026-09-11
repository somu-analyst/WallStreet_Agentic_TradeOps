# Public instance scope — what's actually safe to show (row 356)

**Purpose.** Row 356 settled the licensing RULE (vendor terms restrict redistribution, not
use) but never answered the practical question: of the 38 dashboard pages, which ones can a
public instance actually show? This is that answer, as a proposal to react to, not a build.

**The test applied to each page:** does it display raw CBOE/Finnhub/Yahoo-sourced
quotes, chains, IV, or OI to someone who isn't you? If yes, it's vendor-gated regardless of
whether it also shows a derived signal on top. Government-filed data (SEC, BLS, Treasury,
CFTC) carries no such restriction — it's public record, not a personal-use vendor license.

| Page | Verdict | Why |
|---|---|---|
| 🎯 Signal Accuracy | ✅ Safe | Our own graded track record — literally the credibility showcase |
| 📊 Backtest Lab | ✅ Safe | Our own walk-forward methodology and results |
| 💧 Money Flow (Sankey) | ✅ Safe | SEC filings only, never a vendor quote |
| 🏆 Legendary Investors (13F) | ✅ Safe | SEC 13F filings, public record |
| 📈 Insider / Congress / Whales | ✅ Safe (verify) | SEC Form 4 / congressional disclosures — public record, but confirm no vendor price overlay before shipping |
| 📡 Macro/Event Hub | ✅ Safe | BLS/Treasury/CFTC — already documented as keyless/public |
| 📰 Market Wrap | ⚠️ Needs review | Macro narrative likely safe, but check whether it quotes vendor prices inline |
| 📰 News & Calendar | ⚠️ Needs review | RSS aggregation is a different (looser) license class than market data, but confirm |
| 📺 TradingView | ⚠️ Needs review | Their own embed, not our data — but their terms are a separate question from CBOE/Finnhub's |
| 🧮 Valuation (DCF) | ⚠️ Needs review | The math is ours; the input fundamentals may be vendor-sourced |
| ⚡ Trade Risk Calculator | ⚠️ Needs review | If it's a bare calculator (no live quote needed to demo), likely safe |
| 🎛️ Command Center | ❌ Vendor + private | Mixes book P&L with live market data — exclude entirely |
| 🌍 Market Overview | ❌ Vendor | Live prices/quotes |
| 🔄 Rotation Tracker | ❌ Vendor | Sector price data |
| 🔬 OI Comparison Charts | ❌ Vendor | Raw OI |
| 🔥 OI Analytics & Prediction | ❌ Vendor | Raw OI |
| 💡 Action Board | ❌ Vendor | Signal is ours, but built on live chains shown alongside it |
| 🫧 Anti-Bubble Radar | ❌ Vendor | Same pattern |
| 🎯 High-Prob Options | ❌ Vendor | Raw chain scan |
| 📐 Spreads Scanner | ❌ Vendor | Raw chain scan |
| 🎡 Wheel / CSP | ❌ Vendor | Raw chain scan |
| ⚙️ Strategy Scanners | ❌ Vendor | Raw chain scan |
| 📐 GEX Command | ❌ Vendor | Live walls/bid-ask — the flagship feature, and the clearest vendor-data case |
| 🏁 Spread Backtest | ❌ Vendor | Backtest logic is ours, but runs against live chains on screen |
| 🔎 Smart-Money Flow | ❌ Vendor | Vendor OI flow |
| 🎯 Prop Trading Screen | ❌ Vendor | Raw chain scan |
| 🧠 High-Prob Engine | ❌ Vendor | Ensemble output shown alongside live chain data |
| 🧑‍💼 AI Hedge Fund | ❌ Vendor | LLM synthesis over live market data |
| 🚀 Live Momentum Scanner | ❌ Vendor | Live price/volume |
| 📐 DMA & Mean Reversion | ❌ Vendor | Live price data |
| 📐 Chart Reader | ❌ Vendor | Live price charts |
| 🌍 Global Opportunities | ❌ Vendor | Live market data |
| 🧠 Smart Money Hub | ❌ Vendor | Aggregated vendor flow |
| 💼 Portfolio & Suggestions | 🔒 Already private-gated | Holdings/P&L |
| 👀 Watchlist | 🔒 Already private-gated | Reveals tracked tickers |
| 📝 Paper Trading | 🔒 Already private-gated | — |
| 🔮 Live Position Predictor | 🔒 Already private-gated | Prices the real book |
| 🎯 Next-Day Exit Planner | 🔒 Already private-gated | Per-position exits |

## The shape this suggests

**5 pages ship clean today:** Signal Accuracy, Backtest Lab, Money Flow, Legendary Investors,
Macro/Event Hub. That alone is a real public instance — a credibility showcase (proven track
record + real methodology) plus two genuinely distinctive, non-vendor features (SEC-sourced
Sankey, 13F tracking).

**5 more likely join after a quick look**, not a redesign — mostly "does this one inline a
live quote or not."

**The other 28** (GEX, every scanner, every live-price page) stay private. That's not a
smaller product than it sounds: it's the same shape as most public trading-content
sites — proven results and methodology in front, the live engine behind a login.

## What this does NOT decide

- Whether the 5-clean-page version is worth building at all (that's still your call)
- Hosting shape (same VM/different port vs the AMD Micro shape vs something else — no free
  ARM headroom either way per the corrected Zero-cost guarantee in CLOUD_PROJECT_PLAN.md)
- Whether "Needs review" pages are worth the time to check, or simpler to just leave private
