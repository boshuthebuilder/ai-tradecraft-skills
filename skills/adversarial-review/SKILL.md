---
name: adversarial-review
description: >-
  Run the cross-model adversarial review gate on a pull request: a *different* model from the one
  that wrote the code reviews the open PR adversarially and posts its findings as PR comments, before
  the change is declared done. Covers reviewer selection (the fallback chain), the auditable
  PR-comment protocol, the bundled headless-Gemini harness (`tools/agy-review`, typed exits), and the
  one-time machine setup headless reviewers need. Use for any complex change — more than one layer
  touched, a new pattern introduced, or unattended/production consequences — in any repo, driven by
  any coding agent (Claude Code, Codex, or another CLI agent).
---

# adversarial-review

A change is not done when its author believes it works — it is done when a **different model** has
tried to break it and failed, on the record. Self-review shares the author's blind spots; the gate
exists to put a second, adversarial intelligence between "looks right" and "merged". The reference
deployment's history shows why this is worth the round-trips: reviewers have caught data-loss paths,
dedup bypasses that would have spammed a human every run, silent-failure windows, and — reviewing
this very skill's harness — eleven real defects the author had just written.

**When the gate applies:** any *complex* build — it touches more than one layer, introduces a new
pattern, or has unattended/production runtime consequences. Trivial mechanical edits don't need it.
When in doubt, it applies.

## The rules

1. **Reviewer ≠ author, by model.** Select by model *diversity* first, availability second. If
   Claude wrote the code, Codex or Gemini reviews it; if Codex wrote it, Gemini or Claude reviews
   it. Same-model review is a genuine last resort — and must be disclosed on the PR so the weaker
   gate is visible.
2. **PR-anchored.** Review the *open PR*, not a local diff: the merge-base diff (`main...HEAD`) is
   exactly the author's change, and the PR description is the stated intent the reviewer can check
   it against. (A quick local-diff pass is fine while iterating pre-push; the auditable gate before
   merge is the PR review.)
3. **Findings live on the PR.** The review lands as PR comments naming which reviewer ran and its
   verdict (APPROVE / CHANGES-REQUESTED) with findings as `file:line` + severity + why it is a real
   defect. The author replies on the PR addressing every finding — fixed, rebutted with evidence, or
   accepted-with-rationale — so the whole gate is auditable later.
4. **Iterate to convergence.** Fix, push, re-review. Healthy rounds shrink (11 findings → 3 → 0).
   A reviewer's own prescriptions can themselves introduce regressions — the next round exists to
   catch exactly that.
5. **A dead reviewer is a *done* reviewer.** A hang, timeout, rate-wall, or silent exit means that
   leg of the chain is finished for this round: advance to the next reviewer. Never retry in place,
   and never skip the gate because a tool misbehaved.
6. **Re-assert your working branch** after any review tool runs — review CLIs can check out or
   strand the branch under you.

## The fallback chain

Pick the first *available* reviewer that is a different model from the author:

1. **Codex** (primary when Claude authored) — `codex review --base <main>` reviews the branch diff.
   Codex doesn't post to the PR itself: relay its findings with `gh pr comment`. Run it bounded and
   in the background (see *Bounding a review CLI* below); expect a subscription rate wall after
   roughly a dozen rounds in a session.
2. **Gemini** — via the bundled harness: `tools/agy-review <pr> [--repo owner/name] [--label
   focus]` (path relative to this skill's directory — from a clone of this repo that is
   `skills/adversarial-review/tools/agy-review`), run from inside a checkout of the repo under
   review. It pre-flights the known silent
   killers, bounds the run, and verifies success by the *posted PR comment*, never the CLI's exit
   code. `--model "<label>"` runs the review on another Antigravity-pool model (see *Quota-aware
   reviewer selection*), and every result line carries the run's `conversation: <id>` for follow-ups
   (see *Follow-ups*). Typed exits tell you what happened and what to do:

   | exit | status | next action |
   |---|---|---|
   | 0 | ok | comment is on the PR — read it, address it |
   | 2 | auth-needed | run `agy` once interactively to sign in, retry |
   | 3 | permission-denied | restore the grants block (see *Machine setup*), retry |
   | 4 | timeout | treat this leg as done; advance the chain |
   | 5 | no-comment | narration tail is printed for diagnosis; advance the chain |
   | 6 | bad-args / missing prerequisites | fix the invocation |

3. **Independent same-vendor agent** (last resort) — spawn a fresh agent of the author's own vendor
   with *no shared context*: hand it only the PR diff, the PR description, and a mandate to break
   the change. Disclose on the PR that the gate ran same-vendor.

## Machine setup (one-time, per machine) — headless Gemini

`agy -p` (headless print mode) **auto-denies every confirmable tool** unless grants exist — and it
denies *silently*: exit 0, no output, no comment, indistinguishable from a hang. The grants live in
**`~/.gemini/config/config.json`** — the two look-alike files are decoys (`~/.gemini/settings.json`
belongs to gemini-cli; `~/.gemini/antigravity-cli/settings.json` loads but is not consulted):

```json
{
  "userSettings": {
    "globalPermissionGrants": {
      "allow": [
        "read_file(*)",
        "command(git)",
        "command(gh pr view)",
        "command(gh pr diff)",
        "command(gh pr comment)",
        "command(ls)", "command(cat)", "command(head)", "command(tail)",
        "command(grep)", "command(rg)", "command(find)", "command(sed -n)",
        "command(wc)", "command(uv run)", "command(bash -n)"
      ]
    }
  }
}
```

Two distinct layers, both required: `command(...)` rules are **prefix** matches on the Bash command
line (`git` matches `git add`, *not* `github`), and `read_file(*)` covers agy's *internal*
Search/read tools — without it the reviewer dies the moment it greps. Keep the set scoped: do **not**
grant `command(echo)` or `write_file(*)` (echo + shell redirection is arbitrary file write, and
keeping them denied forces review comments through the inline `--body` path the artifact contract
needs), and do not use `--dangerously-skip-permissions` (it removes the entire approval gate).
`command(uv run)` is deliberately whole: `uv run pytest` already executes arbitrary repo code via
test collection, so narrowing to it bought no safety — while the narrow form killed a reviewer
mid-insight when it reached for `uv run python -c` to check packaging metadata (a check that later
proved to be a real defect). Sign in once by running `agy` interactively.

## Quota-aware reviewer selection

Every reviewer burns a subscription window, and the windows are the real wall — plan spend the way
you plan the review:

- **The chain degrades reactively by design.** A walled or exhausted reviewer fails *typed*
  (rate-wall, `timeout`, `no-comment`) and you advance — no pre-flight quota probe is built in, and
  none is needed at review volumes. If your deployment already tracks provider windows, a glance
  there before a long review session is cheap; do not rebuild that tracking inside the gate.
- **The Antigravity pool is a separate budget.** `agy` exposes multiple model families (run
  `agy models` for the live labels — Gemini, Claude and GPT variants), all billed to the Antigravity
  subscription rather than the primary Claude/ChatGPT plans. When the primary plans are near their
  windows — or you simply want to preserve them for authoring — run the review on the pool:
  `tools/agy-review <pr> --model "<label>"`. An unknown label fails loud with the valid list.
- **Diversity still outranks quota.** The pool's Claude models let you review Claude-authored code
  without spending the primary Claude plan — but that is same-family review (weaker diversity, older
  generation). Prefer a genuinely different family first; reach for same-family-via-pool to preserve
  quota, and disclose it on the PR like any weaker gate.
- **Older pool models are fine for this job.** Adversarial review is careful *reading*; a
  previous-generation model with the diff in front of it catches real defects (the reference
  deployment's gate history is largely a mid-tier model finding genuine bugs).

## Follow-ups — interrogating a review

Continuity across rounds lives in the **PR comment thread** — the only session that survives
switching reviewer legs mid-chain — so rounds are deliberately stateless: each re-reads the PR,
including prior findings and author replies. Native conversation resume is NOT the round-to-round
mechanism (it cannot cross providers, exactly when the chain switches). It is, however, a superb
*diagnostic*: every `tools/agy-review` result line carries the run's `conversation: <id>`, and

    agy --conversation <id> -p "your follow-up"      # --conversation BEFORE -p; headless works

reopens that run with full context. Use it to ask a reviewer why it judged a finding as it did — or
to perform an autopsy on a dead run: a run killed by a denied tool can be *asked what it was trying
to do* ("what exact command did you propose at the final step, and why?"), which has turned an
opaque typed failure into the missing grant — and once revealed that the dying reviewer had been
mid-way to a genuine defect the next leg later confirmed.

## The headless-reviewer contract

These rules are what make *any* headless review CLI reliable — they are baked into `tools/agy-review`
and are the spec for porting the gate to a new reviewer:

- **Verify by artifact, never by exit code.** The success signal is the posted PR comment (the
  harness counts marker comments before and after — immune to clock skew and old comments). Headless
  CLIs exit 0 on every failure mode above.
- **Bound the run and kill the tree.** Set the CLI's own timeout above the review's real duration
  (agy's default print-timeout is 5m — too short; pass 15m), wrap it in a watchdog that kills the
  full descendant tree depth-first (review CLIs spawn node/language-server grandchildren a PID-only
  kill orphans).
- **Pin the reviewer's commands to permission-matchable forms.** The prompt instructs: `git -C
  <root>` and `gh ... --repo <owner/name>` only, never `cd`, never `&&`/`;` chains — prefix matching
  sees only the first word of a chained command.
- **Name the exact allowed command set in the prompt.** Any un-granted command the model invents is
  fatal mid-run. One review died deciding to run the test suite; another died staging its comment
  body via a denied write path.
- **Post with one inline call.** The final `gh pr comment --body "..."` must carry the body inline —
  staging it in a file via echo/printf/redirection/file-write tools is denied and kills the run at
  the last step.
- **Ensure the reviewer's scratch clone exists and is fresh.** agy reviews in its own clone
  (`~/.gemini/antigravity-cli/scratch/<repo>`). Stale, a just-merged SHA does not exist there;
  *absent*, agy bootstraps one itself via commands outside the allow-list and dies silently at
  step 1 — the first review of any repo agy has never seen fails this way. The harness clones or
  fetches it deterministically before the run; do the same when driving agy raw.
- **Steer review labels to static reading — and steer the opening move.** Every label phrase that
  implies a tool is a landmine: "verify the shell fixes" sends the model to shellcheck; naming
  "git-fetch(1)" sends it to `man` — each un-granted, each fatal at step 1 with zero narration.
  Say "by reading the diff", name any permitted extras (`bash -n`), never cite external
  references, and when a repo is new to the reviewer, open the label with "START by running
  'gh pr diff <n> --repo <owner/name>' — no other command first".

## Bounding a review CLI (Codex or any other)

Never run a review CLI bare in the foreground. Launch it in the background, wrap it in a
self-terminating watchdog that kills the child **tree**, and treat a hang or wall as that reviewer
being done:

```bash
codex exec "review ..." & p=$!
( sleep 600; pkill -KILL -P "$p" 2>/dev/null; kill -KILL "$p" 2>/dev/null ) & w=$!
wait "$p"; kill "$w" 2>/dev/null
```

Point `CODEX_HOME` at a lean home with no MCP servers configured — MCP loading is the commonest
Codex hang.
