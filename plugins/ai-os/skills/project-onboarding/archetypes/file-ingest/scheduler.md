# Scheduling the file-ingest jobs

How a deployment wires the two jobs. Platform-agnostic — the concrete timer is yours (a launch agent,
a cron entry, a systemd timer, a person running a command). The design these share is in
[`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

## `ingest` — reactive

Run the **deterministic gate often** and let it no-op when nothing changed. Because the gate is a
cheap file-hash walk (plus a snapshot read) and makes **no model call** unless it finds new or changed
inputs, a frequent tick is safe and effectively free when idle.

- **Mechanism: a short-interval poll** (e.g. every few minutes), optionally also woken by an event.
  Prefer a poll over a fragile file-watcher on a synced/cloud folder — an idle no-op poll is reliable;
  a watcher on a folder that syncs from another device can miss or double-fire. If you add an event
  wake for lower latency, keep the poll as the reliability floor.
- **Run at load** so a backlog that accrued while the machine was down is drained on restart.
- **Coalescing is free:** several items dropped between two ticks are drained by one run — the poll
  interval *is* the debounce. No separate debounce layer is needed.
- **Contention is a clean skip, not an error.** If a tick fires while a previous run still holds the
  project lock, it should **skip quietly** (a no-op), not raise. A run that overlaps the previous one
  is the normal case under a short poll; treat "already running" as success.

## `reconcile` — periodic

A whole-wiki pass isn't triggered by a single change, so it stays on a **fixed cadence** (e.g. weekly,
off-hours). It is the more expensive job (a large prompt over the whole wiki), so don't poll it.

## The two constraints worth checking

1. **Write context.** The reactive `ingest` must run in a context that can actually write the wiki. On
   some platforms an unattended background scheduler cannot write a synced cloud folder (or read
   calendar/contacts behind a privacy grant) — the scheduler then **hops into a logged-in session**
   that holds the capability. Wire the timer to dispatch through whatever hop your platform needs;
   don't assume the background context can write.
2. **Calendar freshness.** If the project has a calendar feed, a **producer** with the grant writes a
   snapshot on its own cadence (e.g. every 15 minutes), and the `ingest` gate detects a change by
   diffing the snapshot. Run the producer often enough that a calendar change is seen promptly, and
   model the snapshot's freshness so a missed producer run reads as `stale`, never as "no change".

## Latency budget (a sensible default)

- Inbox: a dropped item is ingested within **one poll interval**.
- Calendar: a change is absorbed within **one producer interval + one poll interval**.

Both stages are deterministic and make no model call until the gate finds work, so tightening either
interval costs system churn, not model spend.
