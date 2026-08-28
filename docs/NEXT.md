[RESUME AFTER] 2026-08-28 11:00  (limit-guard: block at 83352305 tokens >= 80000000)
# NEXT - handoff (2026-08-27)

## Cloud is LIVE. Read `python tools/show_pending.py --cloud` first (22 rows, own ID series).

Connect:   ssh -i C:\Users\srini\oci-nyse.key ubuntu@150.136.41.250
Env:       cd ~/nyse && source .venv/bin/activate && set -a && . ~/nyse.env && set +a
Verify:    python cloud_smoke.py    (7 gates; gate C must read "DATACENTER IP - authoritative")
Dashboard: /terminal in @WallStreet_AI_Ops_bot returns the live URL + token

## Do next, in order
1. OFFSITE backup. A verified 1.1 GB snapshot sits at ~/backups but has NEVER left Oracle, so an
   account loss takes it along with the database. Build the laptop-side pull.
2. EXPLAIN QUERY PLAN the three slow query shapes (cloud ID 22). cache_size was tested and
   rejected; the index prefix is the suspect.
3. Check no capture is running before enabling any timer - Persistent=true fires on enable.

## User owns
- Recreate the OCI budget as Monthly (currently non-recurring; stops watching after August).
- Flip WallStreet_Agentic_TradeOps to Private (14 MB DB still reachable in its git history).

## Rules learned the hard way this session
- Edits go in NYSE_DATA. NYSE_Cloud is a build artifact; the mirror overwrites it.
- Do not scp files that git also delivers - it aborts the next git pull. Happened twice.
- Never paste secrets into chat. An SSH key, a vault passphrase and a bot token all leaked that
  way; the token had to be revoked.

## Non-cloud session, 2026-08-28 — decisions that CANCEL earlier work

**NO SHARING of the private book, and NO USER ACCOUNTS.** This supersedes the earlier
"read-only viewers" answer. Consequences:
- Do **not** add `user_id` to the schema. That was groundwork for viewers who no longer
  exist and would touch 171 query sites for nothing.
- Do **not** build auth, sign-up or viewer accounts.
- The parallel repo `../WallStreet_TradingOps` has 4 local commits, no remote, and its
  premise (multi-user front end) is gone. Decide whether to keep or drop it.

**Two instances planned:** a public anonymous one and a private one. Two constraints:
- Removing positions does **not** solve the data licence. CBOE/Finnhub/Yahoo are
  personal-use licensed, so the PUBLIC instance must avoid raw vendor quotes and chains,
  not merely hide the portfolio. The **Sankey money-flow page is the clean exception** —
  built entirely from SEC filings, which carry no redistribution restriction.
- Give the public instance **its own database**, populated by an explicit publish step.
  Filtering production with a `WHERE` clause leaks the book the first time someone adds a
  page and forgets — separation by database, never by query.

Licences restrict redistribution, not use: the PRIVATE instance keeps everything.

### Landed
- **Revenue split works for filers that don't phrase it Palantir's way** (`3bf76b7`).
  Visa and Alphabet showed no geography; the fault was report SELECTION, not parsing.
  Verified on 4 filers. A true geography match must beat the segment-shaped fallback
  regardless of filing order, or Alphabet's geography slot is taken by its segment table.
- **Signal Accuracy page led with a green tick it had not earned** (`d8f3da9`). It marked
  "edge" on a raw threshold with no significance test. The multiplicity-corrected verdict
  now leads; the replay is demoted and relabelled "raw +".

### Still open, non-cloud
- **ID 350 — second-level drill.** The child data exists (`"Google Search & other |
  Google Services"` 63,271 under 94,540) but no name-matched candidate table holds it.
  Two attempts failed: one collapsed both axes (reverted), one corrupted the file
  (restored). **Do not** use a cross-axis heuristic — the axes are told apart by name and
  nothing else. Next: widen the segment regex, or read instance-document contexts.
- **ID 334 — `vrvp/SELL_PREMIUM` has now cleared the Bonferroni bar three runs running**
  (2.51 → 3.48 → 3.41 as the sample grew). Still 48 days and still entangled with its
  SELL_PREMIUM family (63–92% fire overlap). Re-run `tools/measure_signal_base_rates.py
  --cohorts` at ~80 and ~120 dates and see whether it HOLDS.
- **ID 357 — verifying nobody else uses the dashboard.** A token in a URL is not access
  control. The durable fix is a firewall allowlist (ufw + the OCI Security List).
