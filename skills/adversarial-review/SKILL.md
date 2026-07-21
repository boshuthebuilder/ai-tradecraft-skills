---
name: adversarial-review
description: >-
  Run the cross-model adversarial review gate on a pull request: a *different* model from the one
  that wrote the code reviews the open PR adversarially and posts its findings as PR comments, before
  the change is declared done. Covers reviewer selection (the fallback chain), the auditable
  PR-comment protocol, the bundled headless-Gemini harness (`tools/agy-review`, typed exits), and the
  one-time machine setup headless reviewers need. Also covers reviewing a numeric or engineering
  contract (a physical model, sizing or pricing calculation, tolerance table — anything whose units
  mean something), where findings carry counterexamples, fixes carry recomputations, and each
  counterexample becomes a permanent test vector. Use for any complex change — more than one layer
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
   strand the branch under you. The bundled `agy-review` harness removes this hazard at source by
   running the reviewer in an isolated worktree (see *The headless-reviewer contract*), but the rule
   still holds for the Codex leg and any CLI you drive raw in the live tree.

## The fallback chain

Pick the first *available* reviewer that is a different model from the author:

1. **Codex** (primary when Claude authored) — `codex review --base <main>` reviews the branch diff.
   Note it takes **no** custom prompt (`--base` and `[PROMPT]` are mutually exclusive), so when you
   need to forward instructions to the reviewer — a focus, or the evidence contract in *Reviewing a
   numeric or engineering contract* — use the `codex exec` form in *Bounding a review CLI* instead.
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

   Exits 4 and 5 are also where a *window-burn* lands — a run that spent itself waiting on a
   long-running command. The harness detects that shape (repeated "waiting…" narration, nothing
   posted) and says so explicitly instead of reporting a generic silence, so you can tell "the
   reviewer wasted its round" apart from "the reviewer died", and reword an offending `--label`
   before the next leg.
   | 6 | bad-args / missing prerequisites | fix the invocation |

3. **Independent same-vendor agent** (last resort) — spawn a fresh agent of the author's own vendor
   with *no shared context*: hand it only the PR diff, the PR description, and a mandate to break
   the change. Disclose on the PR that the gate ran same-vendor.

## Reviewing a numeric or engineering contract

Some changes carry numbers the world will hold you to: a structural or physical model, a sizing or
capacity calculation, a pricing or rate formula, a tolerance table — any spec whose units mean
something. This class reviews *differently*, and unusually well. Truth conditions are crisp, so
neither side can hand-wave: one gate run over an engineering document returned thirteen findings and
**every one was real** — a units trap, load cases that failed to superpose, an unstated support
geometry, an absent material limit, and under-specified vectors.

That hit rate is not luck, and it does not survive prose. It comes from holding *both* sides to
executable evidence:

- **A finding must carry a counterexample.** Concrete inputs, the value the change produces, and the
  value that is correct — "with `F = 4 kN` and `L = 800 mm` this returns `M = 3200 kN·m`; the moment
  is `4 × 0.8 = 3.2 kN·m`, so the length was never converted from millimetres — a factor of 1000"
  beats "the units look wrong". Note that the *unit alone proves nothing*: `3.2 kN·m` and
  `3200 kN·mm` are the same quantity, so a finding has to put two **numbers of the same quantity**
  side by side, not two spellings of one.
- **Where the contract is under-specified, demonstrate the divergence instead.** For an omitted
  support condition, an unstated sign convention or a missing limit there is often no single correct
  value *yet* — the defect is precisely that several defensible readings give different answers. The
  evidence is then two readings and their two numbers ("modelled as pinned the reaction is 12.4 kN,
  as fixed it is 18.1 kN; the spec never says which"), which is as executable as a wrong/right pair
  and must not be dismissed for lacking one. What makes a finding an opinion is the absence of
  *concrete numbers*, not the absence of a single right answer.
- **A fix must carry a recomputation.** The fix commit includes the script or derivation that
  produces the new numbers, and the reply shows before → after. "Fixed" is not evidence: a reviewer
  who cannot see the recomputation has to re-derive it, which is exactly how rounds stop shrinking.
  The headless grants already allow `uv run`, so the reviewer can *execute* the check rather than
  trust it.
- **The counterexample becomes a test vector.** Fold the reviewer's own numbers into the artefact's
  permanent checks — a test, an assertion, a worked-example row. This is the step that pays forward:
  it turns a one-off adversarial exchange into a regression guard, so the same defect cannot return
  silently once the thread is closed.

**Forward this contract — no leg of the chain reads this page.** Every reviewer sees only what you
hand it, so a protocol documented here alone is never applied: you get ordinary prose findings and
none of the hit rate above. Forward the block below on whichever leg you use, keeping it inside the
label-hygiene rules (static reading, name only permitted extras, never cite an external reference):

- **Gemini** — pass it as `tools/agy-review <pr> --label "…"`.
- **Codex** — pass it in the prompt to `codex exec` (see *Bounding a review CLI*). Note that
  `codex review --base <branch>` takes **no** custom prompt: the two are mutually exclusive
  (`the argument '--base <BRANCH>' cannot be used with '[PROMPT]'`), so `exec` is the form that can
  carry this contract. Forwarding matters most here — Codex is the primary leg for Claude-authored
  code, so it is the leg most numeric reviews actually run on.
- **Independent agent** — include it in the brief, alongside the diff and PR description.

```
Numeric contract. For EVERY finding give concrete inputs, the value the change produces, and the
value that is correct — two numbers of the same quantity, since a unit alone proves nothing. Where
the spec is under-specified, instead give two defensible readings and the different numbers they
produce. You may check arithmetic with 'uv run'. On a follow-up round, also check the fix side: each
correction must ship a recomputation showing before and after, and the counterexample must have been
added to the artefact's permanent checks — flag any correction missing either. Look for: units and
scale factors; sign and direction conventions left unstated; cases that must combine or superpose
but do not; boundary, support or initial conditions assumed rather than declared; a missing limit
(strength, capacity, rate, budget); and the domain of validity — the range outside which the formula
quietly stops being true.
```

The fix-side clause matters because follow-up rounds are exactly when the recomputation and the test
vector are due, and a reviewer holding only the finding rules will approve a correction that ships
neither. Each defect class above is invisible to a prose read, and each has shipped at least once.

## Machine setup (one-time, per machine) — headless Gemini

These grants govern the **headless reviewer only** — the sandboxed `agy -p` process the harness
drives. Authoring agents (the ones picking up issues, editing labels, opening PRs) run under their
own harnesses' permission systems and are not constrained by this block; do not read it as the
capability envelope of the whole workflow.

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
proved to be a real defect). Note that this grant is what makes the *prompt-side* ban on running the
test suite necessary (see *The headless-reviewer contract*): the permission layer decides what is
allowed, not what is wise, and the suite is now allowed. Sign in once by running `agy`
interactively.

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

**The relay salvage.** The posting step is the fragile one: the permission validator shell-parses
the composed `--body`, so backticks, escape sequences, or nested quoting in an otherwise-legitimate
comment can kill a run whose review is already complete. When an autopsy shows a finished verdict
that simply failed to post, first ask the resumed run to re-post with a plainer body; if that is
denied too, **relay it yourself**: post the reviewer's verdict verbatim with `gh pr comment`,
naming the reviewer, noting the relay, and including the conversation id — the same pattern the
Codex leg (which cannot post at all) uses routinely. The gate's requirement is an auditable verdict
on the PR, not that the reviewer's own process wrote the bytes.

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
  fatal mid-run: one review died staging its comment body via a denied write path, another reaching
  for a command the grants did not cover. Granting a command does not make it safe to invoke,
  though — see the next rule.
- **Ban the long-running command; keep the fast checks.** The mirror-image death: a reviewer decided
  to run the project's test suite — a *granted* command — and then spent its entire remaining window
  polling it ("I am waiting for pytest … checking back in 60 seconds", over and over) before exiting
  cleanly with nothing posted. Nothing was denied, so no grant change fixes this; the leg is lost
  just as completely, and the typed no-comment looks identical to every other silence. The prompt
  must therefore say plainly that the reviewer does **not** run the suite, and why: the author has
  already run it and reports the result in the PR description, a full run can outlast the whole
  review window, and the gate's value is careful reading, not re-running CI. State a **time budget**
  rather than a blacklist — *nothing you cannot expect to return in about 30 seconds* — so the rule
  generalises to any slow gate rather than to `pytest` alone, and name the fast checks that stay
  allowed (`bash -n`, a linter, a bundle-freshness check). Add the in-flight recovery too: if the
  reviewer notices itself waiting, it should stop waiting, finish reading, and post. The same care
  belongs in your `--label`: a focus phrase like "check the tests pass" walks the reviewer straight
  into this.
- **Post with one inline call, and no backticks in the body.** The final `gh pr comment --body
  "..."` must carry the body inline — staging it in a file via echo/printf/redirection/file-write
  tools is denied and kills the run at the last step. And the permission validator parses
  **backticks inside the body as command substitutions**, permission-checking their contents as
  commands: a review comment that backticks any un-granted identifier (which is most of them) dies
  at the posting step, while one whose snippets happen to start with granted words slips through —
  the most confusing failure in the whole class. The prompt therefore bans backticks in the body
  (code identifiers go in single quotes); a run that died here anyway can be salvaged by resuming
  it and asking it to re-post without backticks (see *Follow-ups*).
- **Ensure the reviewer's scratch clone exists and is fresh.** agy reviews in its own clone
  (`~/.gemini/antigravity-cli/scratch/<repo>`). Stale, a just-merged SHA does not exist there;
  *absent*, agy bootstraps one itself via commands outside the allow-list and dies silently at
  step 1 — the first review of any repo agy has never seen fails this way. The harness clones or
  fetches it deterministically before the run; do the same when driving agy raw.
- **Run the reviewer in an isolated worktree, never your live tree.** A headless review CLI's
  workspace layer checks out a `pr-<n>` branch in its own working directory mid-review. When that
  directory is the coordinator's live checkout, two things break: the branch is *stranded* (the
  caller's `HEAD` moves under them — commits then land on the wrong branch, the push reports
  up-to-date, and the tell is only spotted later), and worse, a coordinator editing files while a
  background round runs hits a *contested tree* — an edit lands against the wrong branch's contents
  or a file the round's checkout has removed (an `Edit` hit a missing file exactly this way). The
  harness fetches the PR head and runs agy in a **detached worktree** at that SHA (`git worktree add
  --detach`), so the reviewer's branch-switching is confined to a throwaway tree and the caller's
  checkout is never touched — you can keep editing while a review runs. It falls back (loud) to the
  caller's tree plus a before/after branch-restore guard only when a worktree cannot be made. This
  is the structural fix for rule 6: prefer worktree isolation over re-asserting the branch after the
  fact.
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
