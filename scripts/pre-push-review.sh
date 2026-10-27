#!/usr/bin/env bash
# Pre-push review: send the outgoing diff to headless Claude Code (read-only)
# and block the push when it reports P0-P2 findings. Findings are written to
# ISSUES.md and printed so the agent that pushed gets the feedback.
# Fails closed: any review error blocks the push. NO FALLBACKS.
set -euo pipefail

readonly review_timeout="15m"
readonly schema='{
  "type": "object",
  "properties": {
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "severity": {"type": "string", "enum": ["P0", "P1", "P2"]},
          "file": {"type": "string"},
          "line": {"type": "integer"},
          "issue": {"type": "string"}
        },
        "required": ["severity", "file", "line", "issue"]
      }
    }
  },
  "required": ["findings"]
}'
readonly prompt="Review the outgoing git diff on stdin before it is pushed. \
You may read files in this repository for context. Report only real, serious findings: \
P0 = broken build, security hole, or data loss; P1 = likely bug or regression; \
P2 = correctness or maintainability risk worth fixing before merge. \
Skip style nits and speculation. Return an empty findings list when the diff is clean."

fail() {
  echo "pre-push review failed: $1" >&2
  exit 1
}

for tool in claude jq timeout; do
  command -v "$tool" >/dev/null || fail "$tool is not on PATH"
done

from_ref="${1:-${PRE_COMMIT_FROM_REF:-}}"
to_ref="${2:-${PRE_COMMIT_TO_REF:-}}"
if [[ -n "$from_ref" && -n "$to_ref" ]]; then
  # Compare the endpoint trees, not the merge base, so a force push that drops
  # remote commits shows those removals.
  range=("$from_ref" "$to_ref")
elif [[ -n "${PRE_COMMIT_LOCAL_BRANCH:-}" ]]; then
  # Pushing history from its root commit: pre-commit sets no refs, so review it all.
  range=("$(git hash-object -t tree /dev/null)" "$PRE_COMMIT_LOCAL_BRANCH")
else
  echo "usage: $0 <from-ref> <to-ref> (or run as a pre-commit pre-push hook)" >&2
  exit 2
fi

issues_file="$(git rev-parse --show-toplevel)/ISSUES.md"
rm -f "$issues_file"

diff="$(git diff "${range[@]}" -- . ':(exclude,glob)**/uv.lock' ':(exclude,glob)**/pnpm-lock.yaml')"
if [[ -z "$diff" ]]; then
  echo "pre-push review: no reviewable changes."
  exit 0
fi

echo "pre-push review: sending outgoing diff to Claude Code..."
response="$(printf '%s\n' "$diff" | timeout "$review_timeout" claude -p "$prompt" \
  --permission-mode plan \
  --disallowedTools Edit Write NotebookEdit \
  --no-session-persistence \
  --output-format json \
  --json-schema "$schema")" || fail "claude exited with status $?"

jq -e '.is_error == false and (.structured_output.findings | type == "array")' \
  <<<"$response" >/dev/null 2>&1 || fail "unexpected claude response: ${response:0:500}"

if jq -e '.structured_output.findings | length > 0' <<<"$response" >/dev/null; then
  jq -r '"# Pre-push review findings\n",
    (.structured_output.findings[] | "- **\(.severity)** `\(.file):\(.line)`: \(.issue)"),
    "\nFix the relevant findings, delete ISSUES.md, commit, then push again."' \
    <<<"$response" >"$issues_file"
fi

if [[ -f "$issues_file" ]]; then
  cat "$issues_file"
  exit 1
fi
echo "pre-push review: no serious findings."
