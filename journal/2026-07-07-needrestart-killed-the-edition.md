# 2026-07-07 — needrestart killed the edition (and nobody was told)

**What happened.** No edition this morning. The 05:00 generate was running normally (a slow
day, ~72 min in, well inside its ~3h budget) when unattended-upgrades installed the
python3.12 security update at 06:11:44 UTC and needrestart's apt hook restarted every Python
worker service on `.75` — including `grazlab-fleet-worker-conductor`, whose cgroup kill took
the in-flight `cli run` subprocess with it. With `retryCount: 0` the orphaned Conductor task
sat IN_PROGRESS; the community-standalone's SQLite-backed sweeper never enforced the 11400s
timeout (`SQLITE_BUSY` on the decider queue), so the workflow showed RUNNING all day, no
failure alert fired (they key off FAILED), and the site quietly served yesterday's paper.

**What it wasn't.** Not the previous day's thegeekwiththepeak fixes — coincidental
shared-host work. (It did leave its own lesson: that session's geek backfill stalled RUNNING
forever because its workflow definition was re-registered mid-flight. Terminate + re-run.)

**Recovery (same day).** Terminated the stuck workflow, one-off
`POST /api/workflow/craicgpt_daily_content` (10:09→11:26), one-off `craicgpt_publish_gate`
(the poll cron only runs 06–08 UTC — an afternoon recovery must fire it by hand). Live by
early afternoon: rubric APPROVE, 18/18 articles with audio, podcast + TL;DR, all languages.

**Fixes.**
- `.75`: `apt-daily-upgrade.timer` → 12:00 UTC (every pipeline is idle);
  `/etc/needrestart/conf.d/50-grazlab-workers.conf` exempts the worker services from
  library-upgrade auto-restarts (deploy scripts own those; pending restarts still logged).
- fleet PR #135 (merged, registered, worker restarted): `craicgpt_generate_daily`
  retryCount 0→1 (`cli run` is same-day idempotent), plus a **freshness canary** at
  09:15 UTC — GETs today's public English paper over CloudFront exactly as a reader would
  and nags Graham on Telegram while it's missing. Mirrors the geek canary added the day
  before; this outage was exactly the silent-failure class it exists for.

**Lesson.** The deterministic/probabilistic split held fine — what failed was the boring
seam: an OS package manager and a workflow engine's database both quietly eating the "this
is broken" signal. Alert on the *outcome* (is today's paper on the public site?), not just
the machinery, because every in-band signal can be green while the reader sees yesterday.
