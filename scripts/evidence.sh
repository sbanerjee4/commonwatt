#!/usr/bin/env bash
# Appends a timestamped evidence snapshot to KIRO.md under "## Evidence log".
# The log must stay the last H2 section, so the snapshot lands inside it.
set -u
cd "$(dirname "$0")/.." || exit 1

HEADING="## Evidence log"

if ! grep -qxF "$HEADING" KIRO.md; then
  printf '\n%s\n' "$HEADING" >> KIRO.md
fi

if awk -v h="$HEADING" '$0==h {found=1; next} found && /^## / {bad=1} END {exit !bad}' KIRO.md; then
  echo "KIRO.md: '$HEADING' must be the last H2 section" >&2
  exit 1
fi

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PYTEST_OUT="$(pytest tests/properties -q 2>&1)"
PYTEST_RC=$?
GIT_OUT="$(git log -n 10 --oneline 2>&1 || echo '(no git history)')"

{
  echo
  echo "### Snapshot $TS"
  echo
  echo '**pytest tests/properties -q**'
  echo
  echo '```'
  printf '%s\n' "$PYTEST_OUT"
  echo "exit code: $PYTEST_RC"
  echo '```'
  echo
  echo '**Last 10 git log lines**'
  echo
  echo '```'
  printf '%s\n' "$GIT_OUT"
  echo '```'
} >> KIRO.md

echo "Evidence snapshot appended to KIRO.md at $TS"
