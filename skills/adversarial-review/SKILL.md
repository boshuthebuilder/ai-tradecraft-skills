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
   code. Typed exits tell you what happened and what to do:

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
        "command(wc)", "command(uv run pytest)", "command(bash -n)"
      ]
    }
  }
}
```

Two distinct layers, both required: `command(...)` rules are **prefix** matches on the Bash command
line (`git` matches `git add`, *not* `github`), and `read_file(*)` covers agy's *internal*
Search/read tools — without it the reviewer dies the moment it greps. Keep the set scoped: do **not**
grant `command(echo)` or `write_file(*)` (echo + shell redirection is arbitrary file write), and do
not use `--dangerously-skip-permissions` (it removes the entire approval gate). Sign in once by
running `agy` interactively.

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
- **Steer review labels to static reading.** An open-ended "verify the shell fixes" label sends the
  model reaching for un-granted tools (shellcheck); say "by reading the diff" and name any permitted
  extras (`bash -n`).

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
