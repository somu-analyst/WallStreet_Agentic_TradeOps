# Demo media

Rendered in the main `README.md`.

## Current files
| File | What it is |
|------|------------|
| `dashboard-demo.gif` (2026-07-28) | Real Playwright screen-capture of the live Streamlit terminal: Next-Day Exit Planner → Market Overview → 24-model High-Prob Engine (run live on GOOG) → OI Analytics → Signal Accuracy. |
| `telegram-demo.gif` (2026-07-28) | A styled chat mockup (not an actual phone screenshot — no visual Telegram client was available to record) populated with real, live-pulled output from `high_prob_signals_engine`/`compute_capflow`/`_verdict_grounding`. Real GOOG numbers throughout, not fabricated. |

To replace either with a real recording of your own device: record the screen (Windows:
**Win+Alt+R** Game Bar, or [ScreenToGif](https://www.screentogif.com/) / OBS), export as
GIF (keep it < ~10 MB), and overwrite the file above — the README reference doesn't change.

## Two ways to embed in README
- **GIF (committed, autoplays):** already wired in `README.md` as
  `![Telegram demo](docs/media/telegram-demo.gif)` — just add the file and push.
- **MP4 with player (higher quality, not stored in repo):** open `README.md` in the
  GitHub web editor and **drag-and-drop** the `.mp4` into the Demo section. GitHub
  uploads it to its CDN and inserts a `https://github.com/user-attachments/...`
  link that renders as a video player (≤10 MB on free accounts).

> Tip: GIFs are the most reliable for viewers (autoplay, no click). Use MP4 drag-drop
> only if you need audio or longer/high-fidelity clips.
