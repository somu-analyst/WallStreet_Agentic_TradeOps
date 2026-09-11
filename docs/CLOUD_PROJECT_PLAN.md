# Cloud project plan — unattended build, validated at every step, zero cost

**Purpose.** This is a handoff document: point a fresh Claude Code session at this repo and
this file, and it has everything needed to (a) verify the existing Oracle deployment is
healthy, or (b) stand up another instance the same way, without guessing and without ever
risking a charge. It exists because tracker ID 316 asked for four things together — minute-
level instructions, a validation check after every change, something that runs unattended,
and a hard guarantee against being billed — and none of those survive being done from memory
months later. Read this whole file before touching anything.

**Companion doc:** [Free Cloud Runbook](https://claude.ai/code/artifact/ef366ebf-db35-4e6b-bd1d-a7fbd19606c9)
(tracker ID 338) has the click-by-click Oracle console steps — account, VM launch via Cloud
Shell CLI, SSH keys, the traps that actually cost time. This file assumes that part is either
already done or about to be repeated, and adds the piece ID 338 didn't cover: a validation
gate after every step, so drift or a failed step is caught immediately instead of discovered
weeks later as a mystery outage.

---

## Zero-cost guarantee — read this before creating anything

Oracle's Always Free tier is free by **shape and quantity**, not by account. Going one unit
over any limit below bills the card on file, silently, with no in-console warning banner at
the moment it happens.

| Resource | Always Free limit | This system's actual usage |
|---|---|---|
| Ampere A1 compute | 2 OCPU + 12 GB RAM TOTAL for the tenancy (corrected 2026-09-11 — this table previously said 4/24, which was simply wrong, verified against Oracle's live docs) | 1 instance, 2 OCPU / 12 GB — **the entire allowance, zero headroom left** |
| Block storage | 200 GB total, all volumes combined | ~5.3 GB database + ~50 GB boot volume |
| Outbound data transfer | 10 TB / month | Nightly capture + Telegram + dashboard traffic — far under |
| Object storage | 20 GB | Unused |
| Load balancer | 1 flexible, 10 Mbps | Unused (dashboard reached via SSH tunnel / Tailscale, not a LB) |

*(Verify these figures at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/) before
relying on them if this document is more than a few months old — Oracle can change the
allowance.)*

**Correction (2026-09-11): there is NO free ARM headroom for ID 356 (a second, public
instance).** The existing VM at 2 OCPU / 12 GB already uses the entire Always Free ARM
allowance for the tenancy — confirmed against Oracle's live documentation and verified live
via SSH (the VM's own nproc/free -h match exactly, no other instance in this project's
history was ever left running). A second instance would need either the AMD Micro shape
(`VM.Standard.E2.1.Micro`, 1 OCPU / 1 GB — workable for a lightweight read-only public page,
not for running the full engine) or a paid shape.

**Non-negotiable before creating any resource:**
1. A budget alarm must exist, **Schedule = Monthly** (not Custom/one-time — a Custom budget
   silently stops evaluating after its single period, which is exactly the failure mode
   caught and still open as cloud-tracker row 3), amount $1, with a real email recipient on
   its alert rule.
2. Any new compute instance must be shape `VM.Standard.A1.Flex` or `VM.Standard.E2.1.Micro`
   — never a paid shape, even "just to try it."
3. Never enable a paid Load Balancer, a second Autonomous Database, or Object Storage beyond
   20 GB "temporarily" — temporary cloud resources are exactly how free tiers turn into bills.

---

## Section A — Validate the EXISTING instance before changing anything

Run this first, always. It costs nothing, changes nothing, and tells you whether the system
you're about to modify is actually in the state the docs claim.

| # | Check | Command (run on the VM via SSH) | Passes when |
|---|---|---|---|
| A1 | Services are up | `systemctl is-active nyse-bot nyse-dashboard cloud-keepalive fail2ban` | all print `active` |
| A2 | Timers are scheduled | `systemctl list-timers cloud-eod.timer cloud-backup.timer` | both show a future `NEXT` time, no `n/a` |
| A3 | Last night's capture actually ran | `sqlite3 <db path> "select trade_date, count(*) from options_openbb where trade_date = (select max(trade_date) from options_openbb) group by 1;"` | a trade_date within the last 1–2 business days, count in the hundreds of thousands (a normal night), not zero |
| A4 | No public attack surface | From OUTSIDE the VM: `nmap -p- <public-ip>` (or any external port scanner) | only port 22 (SSH) responds, nothing else |
| A5 | Budget alarm is real, not decorative | Console → Billing & Cost Management → Budgets → `limit_use` | Schedule = **Monthly**, an email address is listed under the alert rule, not blank |
| A6 | Compute usage is inside the free ceiling | Console → Compute → Instances, sum OCPU/RAM across every instance in the tenancy | total ≤ 2 OCPU / 12 GB |

If any row fails, stop and fix that row before doing anything else in this document — a
build on top of a system that's already silently wrong just adds a second thing to debug.

---

## Section B — Build a new instance (reusable for ID 356's public instance)

Every step pairs an action with a **validation gate**: a command that proves the step
actually landed, framed as current-state (before) → future-state (after). Don't move to the
next step until the gate passes — that is the whole point of doing this differently from the
first migration, where several failures (psutil missing, the job-queue extra, the FIPS/ed25519
key) were only found because something else broke later, not because the step that caused them
was checked.

### B1. Account + budget alarm

- **Action:** create the Oracle account (or, if reusing the existing tenancy for a second
  instance, skip to the budget check) and the $1 Monthly budget alarm — steps in the
  companion Free Cloud Runbook artifact linked above.
- **Validation gate:**
  - *Before:* no budget exists, or an existing one is not Monthly.
  - *After:* `Schedule = Monthly`, `Amount = $1`, alert rule has a real email recipient.
  - *Fails closed if:* you cannot see an email address under Email Recipients — the list
    view hides it; open the alert rule itself to confirm.

### B2. Launch the VM

- **Action:** `oci compute instance launch` with shape `VM.Standard.A1.Flex`,
  `--shape-config '{"ocpus":2,"memoryInGBs":12}'`, RSA key (not ed25519 — Cloud Shell's FIPS
  mode silently breaks ed25519 key generation and the instance ends up unreachable, requiring
  a full relaunch to fix since SSH keys are only read on first boot).
- **Validation gate:**
  - *Before:* `oci compute instance list` shows no instance with this display name.
  - *After:* the instance shows `lifecycle-state: RUNNING` and `ssh -i <key> ubuntu@<ip> echo ok`
    prints `ok` on the first try, no key errors.
  - *Fails closed if:* SSH prompts for a password or refuses the key — do not "fix" this by
    editing instance metadata and rebooting; the metadata is first-boot-only. Terminate and
    relaunch with a verified-nonempty key file (`test -s ~/<key>.pub && echo KEY OK` before
    the launch command, not after).

### B3. Clone the repo and check portability

- **Action:** `git clone https://github.com/somu-analyst/WallStreet_Agentic_TradeOps.git`,
  install dependencies, run `python cloud_smoke.py`.
- **Validation gate:**
  - *Before:* nothing on the VM knows whether this codebase even runs on Linux/ARM.
  - *After:* every gate in `cloud_smoke.py`'s output shows `PASS`, and Gate C specifically
    confirms a datacenter IP is not blocked by the option-chain source — the one gate a
    laptop run can never answer honestly, because a residential IP gets a different verdict.
  - *Fails closed if:* Gate C fails — that is a stop-the-build signal, not a warning. The
    whole point of moving to the cloud is a keyed, IP-agnostic data path; a Gate C failure
    means that path is not actually keyed everywhere it needs to be.

### B4. Move the database

- **Action:** copy the production SQLite file to the new instance (`scp` or an equivalent),
  set `NYSE_DB_PATH` to point at it, set `NYSE_PRICE_SOURCE=finnhub` (yfinance gets flagged
  from a datacenter IP within roughly 50 requests; Finnhub matched yfinance's own closes at
  0.000% mean/max difference when this was measured against real history).
- **Validation gate:**
  - *Before:* `sqlite3 <local db> "select count(*) from options_openbb;"` on the source.
  - *After:* the SAME query against the copied file on the VM returns the SAME count. Row
    counts matching on transfer is the actual proof of an uncorrupted copy — a file-size
    match is not enough for SQLite.
  - *Fails closed if:* the counts differ at all — re-copy, don't patch around a partial file.

### B5. Wire the services and let one full night run unattended

- **Action:** systemd units for the bot, the dashboard, the EOD timer, the backup timer, a
  keepalive (Oracle reclaims an idle instance; holding a few GB of memory in a lightweight
  process is far cheaper than fighting reclamation after the fact), and fail2ban.
- **Validation gate:**
  - *Before:* nothing runs unless someone is SSH'd in.
  - *After, the FIRST night with no one watching:* the scheduled capture produces a normal
    ticker count for that trade date, with zero manual intervention. This is the gate that
    actually answers "does this run unattended" — a clean `cloud_smoke.py` run only proves
    the pieces work once, by hand, with someone present.
  - *Fails closed if:* the timer fired but produced a partial or zero-row capture — check
    for a lock collision first (a manual run and the scheduled run overlapping throttles the
    data source), not a code bug, before changing anything.

### B6. Confirm the guarantee still holds

- **Action:** none — this is a read-only close-out check.
- **Validation gate:** re-run Section A (A1–A6) against the NEW instance. All six must pass.
  If this is a second instance alongside the first, re-check A6 across **both** instances
  combined, not each one separately — the 2 OCPU / 12 GB ceiling is tenancy-wide, and the
  first instance alone already uses all of it (see the Zero-cost guarantee section above).

---

## What this plan deliberately does NOT cover

- Standing up the **public-facing** side of a second instance (row 356) — that also needs
  its own database containing only publishable data, not a filtered view of the production
  one, and a decision on what "publishable" excludes (vendor-sourced raw quotes/chains,
  per CBOE/Finnhub/Yahoo personal-use licensing). That is a data-shape decision, not a
  build-steps one, and belongs in its own pass.
- Auto-deploying **code** changes to a running instance — this plan covers building an
  instance, not keeping it in sync afterward. That is cloud tracker row 45/50.
- Naming a broker to replace the CBOE scrape lane — the one open compliance item on the
  existing instance, and a decision only the user can make.
