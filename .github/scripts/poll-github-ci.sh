#!/usr/bin/env bash
# Poll GitHub Actions workflow runs until tracked workflows complete.
# Exits 0 on success, 1 on failure/timeout.
#
# Usage:
#   .github/scripts/poll-github-ci.sh \
#     --repo OWNER/REPO \
#     --token GITHUB_TOKEN \
#     --sha COMMIT_SHA \
#     [--workflows 'regex']         # default: ^(CI|Staging Tests|Security Audit)$
#     [--expected-count N]          # default: 3
#     [--max-polls N]               # default: 300
#     [--poll-interval SECONDS]     # default: 10
#     [--initial-delay SECONDS]     # default: 15
#
# Environment alternative: set GITHUB_TOKEN instead of --token.
set -euo pipefail

# --- defaults ---
REPO=""
TOKEN="${GITHUB_TOKEN:-}"
SHA=""
TRACKED_WORKFLOWS='^(CI|Staging Tests|Security Audit)$'
EXPECTED_WORKFLOW_COUNT=3
# 300 × 10s = 50 minutes. sized to cover staging-tests (45 min) plus a bit
# of slack. callers that know their workflow is shorter can pass --max-polls
# to cap the wait.
MAX_POLLS=300
POLL_INTERVAL=10
INITIAL_DELAY=15

# --- parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)    REPO="$2";                    shift 2 ;;
    --token)   TOKEN="$2";                   shift 2 ;;
    --sha)     SHA="$2";                     shift 2 ;;
    --workflows) TRACKED_WORKFLOWS="$2";     shift 2 ;;
    --expected-count) EXPECTED_WORKFLOW_COUNT="$2"; shift 2 ;;
    --max-polls) MAX_POLLS="$2";             shift 2 ;;
    --poll-interval) POLL_INTERVAL="$2";     shift 2 ;;
    --initial-delay) INITIAL_DELAY="$2";     shift 2 ;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2 ;;
  esac
done

# --- validate ---
if [ -z "$REPO" ] || [ -z "$TOKEN" ] || [ -z "$SHA" ]; then
  echo "ERROR: --repo, --token (or GITHUB_TOKEN), and --sha are required" >&2
  exit 2
fi

# --- poll ---
echo "polling github actions for $REPO @ $SHA"
echo "  tracked: $TRACKED_WORKFLOWS (expecting $EXPECTED_WORKFLOW_COUNT)"

ZERO_RUNS=0
STATUS="pending"

sleep "$INITIAL_DELAY"

for i in $(seq 1 "$MAX_POLLS"); do
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/actions/runs?head_sha=$SHA")

  HTTP_CODE=$(printf '%s' "$RESPONSE" | tail -1)
  BODY=$(printf '%s' "$RESPONSE" | sed '$d')

  # a bad token, wrong sha, or missing repo won't fix itself on the next
  # poll — stop right away with a clear message. keep retrying on 5xx and
  # rate-limit responses since those do tend to clear up.
  case "$HTTP_CODE" in
    200) ;;
    401|403|404)
      echo "ERROR: HTTP $HTTP_CODE from GitHub API — check token scope, SHA, and repo name" >&2
      STATUS="failure"
      break
      ;;
    *)
      echo "  [$i/$MAX_POLLS] HTTP $HTTP_CODE from GitHub API, retrying..."
      sleep "$POLL_INTERVAL"
      continue
      ;;
  esac

  # on first poll, dump all runs for debugging
  if [ "$i" -eq 1 ]; then
    echo "  all workflow runs for this SHA:"
    printf '%s' "$BODY" | jq -r \
      '(.workflow_runs // [])[] | "    [\(.id)] \(.name) status=\(.status) conclusion=\(.conclusion) head_sha=\(.head_sha[0:12])"'
  fi

  LATEST_RUNS=$(printf '%s' "$BODY" | jq -c --arg names "$TRACKED_WORKFLOWS" '
    [(.workflow_runs // [])[] | select(.name | test($names))] |
    group_by(.name) | map(sort_by(.created_at) | last)')

  RUN_COUNT=$(printf '%s' "$LATEST_RUNS" | jq 'length')

  # wait ~5 min (30 × 10s default) for tracked workflows to appear.
  # absorbs github enqueue latency on brand-new repos and during
  # provider incidents.
  if [ "$RUN_COUNT" -eq 0 ]; then
    ZERO_RUNS=$((ZERO_RUNS + 1))
    if [ "$ZERO_RUNS" -gt 30 ]; then
      echo "No tracked workflow runs found after $((ZERO_RUNS * POLL_INTERVAL))s"
      STATUS="timeout"
      break
    fi
    echo "  [$i/$MAX_POLLS] pending (no workflow runs yet, ${ZERO_RUNS}/30)"
    sleep "$POLL_INTERVAL"
    continue
  fi

  printf '%s' "$LATEST_RUNS" | jq -r \
    '.[] | "    \(.name): status=\(.status) conclusion=\(.conclusion) head_sha=\(.head_sha)"'

  # wait for all expected workflows before evaluating
  if [ "$RUN_COUNT" -lt "$EXPECTED_WORKFLOW_COUNT" ]; then
    echo "  [$i/$MAX_POLLS] pending (${RUN_COUNT}/${EXPECTED_WORKFLOW_COUNT} tracked workflows started)"
    sleep "$POLL_INTERVAL"
    continue
  fi

  # startup_failure conclusions (e.g. malformed workflow yaml, runner
  # unavailable) are treated as failure — we don't want a required
  # workflow that couldn't even start to be excluded from the success
  # evaluation. pending remains pending (null conclusion); everything
  # else must be success/neutral/skipped to qualify as success.
  STATUS=$(printf '%s' "$LATEST_RUNS" | jq -r '
    map(.conclusion) |
    if any(. == null) then "pending"
    elif all(. == "success" or . == "neutral" or . == "skipped") then "success"
    else "failure" end')

  echo "  [$i/$MAX_POLLS] $STATUS (${RUN_COUNT}/${EXPECTED_WORKFLOW_COUNT} tracked workflows)"

  if [ "$STATUS" = "success" ]; then
    echo "all tracked workflows passed"
    break
  elif [ "$STATUS" = "failure" ]; then
    echo "one or more tracked workflows failed"
    break
  fi

  sleep "$POLL_INTERVAL"
done

# --- result ---
STATUS=${STATUS:-timeout}
if [ "$STATUS" = "timeout" ] || { [ "$STATUS" != "success" ] && [ "$STATUS" != "failure" ]; }; then
  STATUS="timeout"
  echo "timeout waiting for github actions"
fi

# exit code: 0 = success, 1 = failure/timeout
if [ "$STATUS" = "success" ]; then
  exit 0
else
  exit 1
fi
