# Meridian Home Comfort chat agent

A chat agent for Meridian Home Comfort's customer calls: it answers knowledge questions from document search, looks
up accounts, books, reschedules and cancels appointments, and hands off to staff with a ticket. It runs on one
always-on Fly.io machine. The full README (setup, results, how it works) comes with the final deliverables.

## Rollback runbook

One page for running, rolling back and restoring the live site (R83). Every Fly.io command goes through
`scripts/fly`, which finds the Fly.io command line tool even when it is not on PATH (or set `FLYCTL` to its path).

### What lives where

| Part | Where | Rolled back by |
| --- | --- | --- |
| Code, prompts, search index (`data/index/`), seed scheduling database, `docs/FINDINGS.md`, `data/results/final/` | The release image | Deploying an earlier release's image |
| Live scheduling database `/data/scheduling.sqlite`, operations database `/data/operations.sqlite` (conversations, tickets, costs, flags) | The volume `meridian_data` mounted at `/data` | Restoring the volume from a snapshot |
| Keys and passwords | Fly.io secrets | Not rolled back; set again by hand |

The machine count is always one: one worker holds the reset gate, the nightly scheduler and the message limits.

### Secrets

Set each once with `scripts/fly secrets set NAME=value`. Values never go in the repository, `fly.toml`, the
Dockerfile or this README. To keep a value out of shell history, read it first: `read -rs v && scripts/fly secrets
set NAME="$v"; unset v`. `scripts/fly secrets list` shows the names (never the values).

| Name | What it is |
| --- | --- |
| `ANTHROPIC_API_KEY` | A key made only for this site, in its own Anthropic console workspace with a monthly spend limit (D50); not the test-run key, which stays only in the local `.env` |
| `VOYAGE_API_KEY` | The Voyage AI key for search embeddings |
| `VISITOR_COOKIE_SECRET` | Signs the visitor cookie; at least 16 random characters (the plan calls it `SESSION_SECRET`; the code reads `VISITOR_COOKIE_SECRET`). Changing it signs every visitor and staff member out |
| `REVIEWER_TOKEN` | The secret behind the reviewer link `https://<app>.fly.dev/#r=<token>`, at least 16 random characters; every browser that opens the link gets a 7-day reviewer session sharing the $3-a-day reserve |
| `STAFF_PASSWORD_HASH` | The staff password's hash, made with `.venv/bin/python -m app.web.staff`; never the password itself |
| `ALERT_WEBHOOK_URL` | Where alerts are posted (error bursts, failed writes, a failed nightly reset, spend passing $5) |

`DATABASE_PATH` and `OPS_DATABASE_PATH` are ordinary settings in `fly.toml` (both on `/data`), not secrets.

### First setup (once)

1. `scripts/fly apps create <app>` and put the name in `fly.toml` (`app = ...`).
2. `scripts/fly volumes create meridian_data --region dfw --size 1 --snapshot-retention 7 --yes` (daily snapshots,
   kept 7 days).
3. Set the six secrets above.
4. `scripts/deploy.sh` (below). On the first start the machine copies the seed scheduling database to the empty
   volume; it never overwrites an existing one.
5. Open `https://<app>.fly.dev/health`; it answers `{"ok": true}`. Point the free outside uptime monitor at it.

### Deploy

`scripts/deploy.sh` runs the quick test run (`python -m eval.quick_run`, paid, test key) and stops if it fails; then
`scripts/fly deploy`, `scripts/fly scale count 1 --yes`, and `scripts/fly status --json`, failing unless exactly one
machine runs. `--skip-quick-run` skips the quick run, only if it has been cut. Fly.io's health check on `/health`
restarts the machine if it stops answering.

### Roll back a release (bad code, prompt or index)

1. `scripts/fly releases --image` lists the releases, newest first, with each one's image
   (`registry.fly.io/<app>:deployment-...`). Pick the last good one.
2. `scripts/fly deploy --image registry.fly.io/<app>:deployment-<id>` releases that image again. Code, prompts and
   the search index go back together; the volume and the secrets are untouched. (It uses the `fly.toml` in the
   current folder, so check out the matching commit if `fly.toml` itself changed.)
3. `scripts/fly scale count 1 --yes`, then `scripts/fly status` shows one machine, and `/health` answers
   `{"ok": true}`.
4. Send one knowledge question in the chat and check the reply.

### Restore the volume from a snapshot (damaged data)

Only the scheduling database damaged: the nightly reset (03:00 Austin time) rebuilds it from the seed anyway. To do
it at once, `scripts/fly ssh console -C "rm /data/scheduling.sqlite"` then `scripts/fly machine restart <machine-id>`;
the start copies the seed again. The operations database is not touched.

The operations database damaged, or both:

1. `scripts/fly volumes list` gives the volume id (`vol_...`) and `scripts/fly status` the machine id.
2. `scripts/fly volumes snapshots list <volume-id>` lists the daily snapshots; pick the last one before the damage.
3. `scripts/fly volumes create meridian_data --snapshot-id <snapshot-id> --region dfw --size 1 --yes` makes a new
   volume from it (note its new id).
4. `scripts/fly machine clone <machine-id> --attach-volume <new-volume-id>:/data` starts a machine on the restored
   volume; then `scripts/fly machine destroy <old-machine-id> --force`.
5. `scripts/fly status` shows exactly one machine, and `/health` answers `{"ok": true}`. Check that the staff view
   shows the tickets expected up to the snapshot's time.
6. Once checked, `scripts/fly volumes destroy <old-volume-id>`, so a later deploy can never attach the damaged
   volume.

Anything written after the snapshot (bookings, conversations, tickets) is lost; bookings return to the seed at the
next nightly reset in any case.

### Practice record

The release rollback is practised once before submission (R83). Practised on 2026-10-21 (04:49 UTC): from release
v2 (the reviewer-only note and the design fixes) back to v1's image with `scripts/fly deploy --image
registry.fly.io/ai-call-center-agent-bvgy9q:deployment-01M5EB2PGFD4CCCSM30R5XPWJ6 --ha=false`, which took 20 seconds;
`/health` answered `{"ok":true}` and the page showed v1 (no reviewer-only note). Then forward again to v2's image in
16 seconds (now release v4), with the note back. The volume and its databases were untouched throughout. The volume
snapshot restore has not been practised.

## Who can chat (D50)

The site is public to view: the chat page, the Results tab and the test customers. Chatting is reviewer-only.
`fly.toml` sets the public budget to $0 (`PER_VISITOR_DAILY_USD = "0"`), so a public message gets a plain handoff
before any model call, and the safety advice for an emergency still appears, since it is written in code. One
reusable reviewer link, included with the submission, starts a reviewer session in any browser that opens it;
all reviewer sessions share the $3-a-day reserve (about 300 typical conversations a day). The live
key is a site-only key with a monthly limit in the Anthropic console, a hard stop behind the site's own caps (about $25 a month covers a week at the full reserve).
To open chat to the public later, remove that line from `fly.toml` and redeploy.

## Live reply times

Measured on 2026-10-21 against the deployed site (release v4) with `scripts/measure_latency.py --reviewer`: 3 warm-up
messages, then 50 measured, each a fresh reviewer-link visitor, 31 seconds apart. All 50 replied, none failed. Median
time to the first sentence 2.55 seconds (target under 2.5) and to the full reply 4.60 seconds (target under 4.0), so
both targets were narrowly missed; the slowest replies were handoffs and long knowledge answers. The run is saved in
`data/results/latency/live-20261021.txt`.

