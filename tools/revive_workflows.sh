#!/usr/bin/env bash
# Start a workflow again when nothing of it is alive.
#
#   tools/revive_workflows.sh update_today_matches.yml update_all_epg.yml:30
#
# Each argument is a workflow file, optionally ":N" — then it is started
# only when its newest run is also more than N minutes old.
#
# WHY EVERY FREQUENT WORKFLOW CALLS THIS. On 5 October 2026 the screens
# froze for three hours (20:58 to 23:58 UTC). The screen chain hands each
# run on to the next one with a workflow_dispatch, and the 21:05 successor
# was cancelled by GitHub — "The job was not acquired by Runner of type
# hosted even after multiple attempts" — so there was nothing left to ask
# for the next. The crons that are meant to restart a dead chain were not
# delivered either: no scheduled run of any workflow from 18:49 to 23:13.
# The first cron that did land (Health check, 23:13; Build every EPG,
# 23:20) found the chain dead and had no way of knowing.
#
# Now every one of them does know. Whichever workflow GitHub lets run
# first after a silence brings the others back, so one landed event is
# enough to restart everything, and the chains watch each other while
# they run.
#
# A run counts as alive while it is queued, waiting, pending or in
# progress — a successor waiting behind the current run is alive. Never
# fails the job that calls it: a watchdog that breaks the build it rides
# on would be worse than none.

set -uo pipefail
repo="${GITHUB_REPOSITORY:-Saudi23723/Unified-MENA-EPG}"
ref="${REVIVE_REF:-main}"
now=$(date +%s)

for spec in "$@"; do
  wf="${spec%%:*}"
  min_age=0
  [ "$spec" != "$wf" ] && min_age="${spec#*:}"

  runs=$(gh api "repos/$repo/actions/workflows/$wf/runs?per_page=20" 2>/dev/null) || {
    echo "::warning::revive: could not read the runs of $wf"
    continue
  }
  alive=$(jq '[.workflow_runs[] | select(.status != "completed")] | length' <<<"$runs")
  if [ "${alive:-0}" -gt 0 ]; then
    echo "revive: $wf has $alive run(s) alive"
    continue
  fi
  newest=$(jq -r '.workflow_runs[0].created_at // empty' <<<"$runs")
  if [ -n "$newest" ] && [ "$min_age" -gt 0 ]; then
    age=$(( (now - $(date -d "$newest" +%s)) / 60 ))
    if [ "$age" -lt "$min_age" ]; then
      echo "revive: $wf last started ${age} min ago — not yet"
      continue
    fi
  fi
  echo "revive: nothing of $wf is alive (newest run: ${newest:-none}) — starting it"
  gh workflow run "$wf" --repo "$repo" --ref "$ref" \
    || echo "::warning::revive: could not start $wf"
done
exit 0
