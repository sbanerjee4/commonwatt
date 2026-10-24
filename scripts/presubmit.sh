#!/usr/bin/env bash
# Deterministic pre-submit checks. Prints PASS or FAIL per check and exits
# non-zero if any check fails. Read-only: it never modifies a file.
set -u
cd "$(dirname "$0")/.." || exit 1

failures=0

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS  $name"
  else
    echo "FAIL  $name"
    failures=$((failures + 1))
  fi
}

kiro_tracked() {
  [ -n "$(git ls-files .kiro)" ]
}

kiro_not_ignored() {
  ! grep -qxE '\.kiro/?' .gitignore
}

readme_has_make_demo() {
  grep -q 'make demo' README.md
}

readme_has_demo_accounts() {
  grep -qE '^#{1,6} +Demo accounts *$' README.md
}

kiro_has_seven_h2() {
  [ "$(grep -cE '^## ' KIRO.md)" -ge 7 ]
}

kiro_evidence_filled() {
  ! grep -E '^Evidence:' KIRO.md | grep -q 'TODO'
}

readme_has_video_url() {
  grep -qE 'https?://[^[:space:])]*(youtube\.com|youtu\.be|vimeo\.com|loom\.com)' README.md
}

check ".kiro is tracked by git (git ls-files .kiro is non-empty)" kiro_tracked
check ".gitignore does not ignore .kiro" kiro_not_ignored
check "README.md contains 'make demo'" readme_has_make_demo
check "README.md has a 'Demo accounts' heading" readme_has_demo_accounts
check "KIRO.md has at least seven H2 headings" kiro_has_seven_h2
check "KIRO.md has no Evidence line reading TODO" kiro_evidence_filled
check "README.md contains a video URL" readme_has_video_url

if [ "$failures" -gt 0 ]; then
  exit 1
fi
exit 0
