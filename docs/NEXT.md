[RESUME AFTER] 2026-08-28 01:00  (limit-guard: block at 113228560 tokens >= 80000000)
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
