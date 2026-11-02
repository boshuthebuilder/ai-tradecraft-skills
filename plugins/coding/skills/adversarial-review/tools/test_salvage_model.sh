#!/usr/bin/env bash
# Regression test: the relay salvage must resume on the same --model as the review run.
# Extracts attempt_relay_salvage() from agy-review and runs it against a stub `agy`.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FN="$WORK/fn.sh"
sed -n '/^attempt_relay_salvage() {/,/^}/p' "$HERE/agy-review" >"$FN"
[ -s "$FN" ] || { echo "FAIL: attempt_relay_salvage not found in agy-review" >&2; exit 1; }

mkdir "$WORK/bin"
cat >"$WORK/bin/agy" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$AGY_ARGS_FILE"
echo "Verdict: APPROVE"
STUB
printf '#!/usr/bin/env bash\nexit 0\n' >"$WORK/bin/gh"
chmod +x "$WORK/bin/agy" "$WORK/bin/gh"

run_case() { # $1 = MODEL value ("" for none); prints the recorded agy args
  AGY_ARGS_FILE="$WORK/args" PATH="$WORK/bin:$PATH" MODEL="$1" bash -c '
    kill_tree() { :; }
    count_marker_comments() { echo $((++N)); }
    N=0; BEFORE=0
    CONV=conv-123 PR=1 REPO=owner/name MARKER="marker" REVIEW_ROOT="$PWD"
    SALVAGE_PRINT_TIMEOUT=4m SALVAGE_WATCHDOG_SECS=1 OUT="$AGY_ARGS_FILE.out" REVIEW_BODY="$AGY_ARGS_FILE.body"
    source "'"$FN"'"
    attempt_relay_salvage
  ' >/dev/null 2>&1
  cat "$WORK/args"
}

fail=0
with="$(run_case "gemini-test-model")"
printf '%s\n' "$with" | tr '\n' ' ' | grep -q -- '--model gemini-test-model --conversation conv-123' \
  || { echo "FAIL: salvage did not pass --model before --conversation when MODEL is set:" >&2; echo "$with" >&2; fail=1; }
without="$(run_case "")"
printf '%s\n' "$without" | grep -q -- '--model' \
  && { echo "FAIL: salvage passed --model although none was given:" >&2; echo "$without" >&2; fail=1; }
printf '%s\n' "$without" | grep -qx -- '--conversation' \
  || { echo "FAIL: salvage did not resume the conversation without MODEL" >&2; fail=1; }
[ "$fail" -eq 0 ] && echo "ok: relay salvage model passthrough"
exit "$fail"
