# Scheduling the code archetype jobs

How a deployment wires the two `code` jobs. Platform-agnostic — the concrete timer is yours (a launch
agent, a cron entry, a systemd timer, a person running a command). The shared design is in
[`ARCHITECTURE.md`](../../../../ARCHITECTURE.md).

## The deterministic git read both jobs depend on

Before reasoning, the gather stage reads the project's git **clone** (at the deployment-recorded
`backing.path`) with read-only `git` commands — recent commits and their file-level churn. This read
is **deterministic**: the same clone state yields the same report, so it sits below the determinism
boundary (the *reasoning* — summary or review — is the only non-deterministic part). Two rules:

- **Keep the clone current.** A `fetch` before the read (idempotent) so the digest/review see the
  latest pushed history. The system never writes to the clone; it only reads and fetches.
- **Fail loud on a bad read.** A missing clone, an unborn repo (no commits), a shallow clone, and a
  genuine `git` failure are **distinct states** the report names (`missing` / `empty` / `shallow` /
  `error`) — never a blank read masquerading as "no changes this period". The reasoning template skips
  with a surfaced reason on `missing`/`empty`/`error`, and proceeds-but-flags on `shallow`.

## `digest` and `review` — periodic, not reactive

Unlike `file-ingest`'s reactive `ingest`, a code project has **no inbox to drain**, so both jobs run on
a **fixed cadence** (e.g. weekly). Offset them if you like — the digest one weekday, the review
another — so two report pages don't land at once. A run with nothing to report still writes a short
"no notable changes this period" page (or skips per the deployment's preference); it never errors on a
quiet week.

One pair **per code project** — each reads its own clone and writes its own reports area.

## Writes stay guarded

Both jobs return a structured report that the deployment's **deterministic write stage** applies under
the project's reports area — the same guards as any other write (propose-on-human-edit, in-root path
containment). The reasoning never writes directly, and never to the code clone.
