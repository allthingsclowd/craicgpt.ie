# 2026-07-10 — the Coke Zero powerdown: two outages for the price of one button

**What happened.** The grazlab hypervisor (.249) powered off at 05:37:40 BST. Root cause
from the previous boot's journal: `systemd-logind: Power key pressed short.` → fully
orderly poweroff — the physical power button, pressed during the Coke-Zero cleanup
(Graham's own theory, confirmed; no spill-short, no hard cut, zpool clean, no fsck).
Powered back on 08:34 BST. Lab dark 04:37–07:34 UTC.

**Blast radius & recovery — everything self-healed or was fixed same-morning:**

- **craicgpt.ie** — the missed 05:00 generate was re-fired by Conductor's boot-time
  catch-up (07:35); the LAST gate poll of the 06–08 window (07:55) promoted EN live with
  ~5 minutes to spare. it/ja/fr lost a race (translations landed 07:55–07:59; the
  workflow's own gate said `already-live` and skipped them) but narrate `--publish --live`
  (07:59–10:28) published every language WITH audio. End state: 6/6 languages live, full
  audio, zero manual re-runs.
- **thegeekwiththepeak.com** — `geek_ctem_daily` FAILED at 03:19 (BEFORE the outage,
  unrelated): its fabrication judge flagged EPSS-rounding "contradictions" its own
  reasoning called acceptable → 0/floor-3 survivors → hard hold. Re-run as a one-off
  after craicgpt finished (sequential — shared DGX/M3). The judge false-positive pattern
  (craicgpt's 2026-06-19 drought, same family) needs a gate fix in that repo.
- **cymulate lab** — the sneaky one. All 8 VMs and all 6 docker services restarted fine
  (`restart: unless-stopped`), but the hypervisor lost its lab-bridge footholds
  (`ip addr add 10.10.20.2/24 vmbr20` + `10.10.10.2/24 vmbr10` — applied live by
  `configure-lab.sh ph_footholds`, never persisted). No path into the lab → "6 key
  services down" while every service was up. Fix: idempotent re-add (one command) →
  `validate-lab.sh` **17/17 PASS**. Persistence PR: cymulate-demo-environment **#7**
  (post-up lines; the live apply to /etc/network/interfaces awaits Graham naming it —
  classifier-gated).
- **Everything else** — Conductor, both workers, LiteLLM, vault, PBS, agents, GPU VM,
  M3, DGX: clean. Two 6-week-old zombie `fleet_healthcheck_heartbeat` executions
  (stuck RUNNING since 2026-05-26 on a retired `probe_m3` task) found and removed.

**What the watchdog missed (→ fleet PR #136 + the sentinel-deep-agent project):**
the sentinel only inspects the LATEST execution of SCHEDULED workflow types (zombies
invisible), never notices its own dark gaps (3 hourly slots vanished silently), and
false-alarms on future one-shot schedules. PR #136 fixes those deterministically;
the approved sentinel-deep-agent plan (own VM 219, deepagents + rubric judge + memory +
Telegram-approved remediation, cymulate lab in scope) is the structural answer.

**Lessons.**
1. *Ephemeral network state is an outage waiting for a reboot.* Anything `ip addr add`/
   `ip route add` on a hypervisor must land in persistent config the same day.
2. *"Services down" ≠ services down.* Check the PATH before the services — the cymulate
   containers had been up 7 hours while every probe said dead.
3. *Catch-up crons are load-bearing.* Conductor's boot-time re-fire saved today's paper;
   nobody had ever verified that behavior. Now it's proven — and the gate's 07:55 squeak
   shows the 06–08 window has no slack after a late boot.
4. *A watchdog on the box it watches is half a watchdog.* Hence VM 219.
5. Physical hardening is cheap: `HandlePowerKey=ignore` on .249 would have made this a
   non-event (recommended, Graham's call).

**Shipped today:** fleet PR #136 (sentinel orphan-sweep / dark-gap / NEVER_RAN fix),
cymulate PR #7 (persist footholds), craicgpt journal (this), zombie cleanup, 17/17 lab
validation, full multi-lingual edition live with audio.
