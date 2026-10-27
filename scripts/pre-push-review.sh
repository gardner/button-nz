#!/usr/bin/env bash
# Pre-push review: headless Claude Code reviews the outgoing commits and writes
# ISSUES.md if it finds serious problems. ISSUES.md blocks the push.
set -euo pipefail

from_ref="${1:-${PRE_COMMIT_FROM_REF:?usage: $0 <from-ref> <to-ref>}}"
to_ref="${2:-${PRE_COMMIT_TO_REF:?usage: $0 <from-ref> <to-ref>}}"

cd "$(git rev-parse --show-toplevel)"
rm -f ISSUES.md

# The reviewer may write ISSUES.md and must not change anything else,
# including the contents of untracked files.
repo_state() {
  {
    git rev-parse HEAD
    git status --porcelain=v1 -uall -- . ':!ISSUES.md'
    git diff HEAD --binary
    git ls-files -z --others --exclude-standard -- . ':!ISSUES.md' | xargs -0r git hash-object --
  } | git hash-object --stdin
}
before="$(repo_state)"

# BACKGROUND.md (local, gitignored) lets the author answer earlier findings.
background=""
if [[ -f BACKGROUND.md ]]; then
  background="

The author left these notes in BACKGROUND.md. Do not re-report findings they
already address unless the reasoning is wrong:

$(cat BACKGROUND.md)"
fi

echo "pre-push review: Claude Code is reviewing $from_ref..$to_ref"
claude -p --permission-mode acceptEdits </dev/null "You are the pre-push code reviewer.
Review the changes about to be pushed: run \`git log $from_ref..$to_ref\` and
\`git diff $from_ref $to_ref\`. For context, read files as they are at the
pushed ref with \`git show $to_ref:<path>\`; the working tree may differ.
Do not read \`.env\` files or other secrets.

Treat the codebase as read-only. Do not create, edit, or delete any file except
ISSUES.md, and do not run commands that change git state.

Report only serious problems:
- P0: broken build, security hole, or data loss.
- P1: likely bug or regression.
- P2: correctness or maintainability risk worth fixing before merge.
Skip style nits and speculation.

If you find any, write them to ISSUES.md at the repository root as a Markdown
list, one item per finding: severity, \`file:line\`, the problem, and the fix.
If you find none, do not create ISSUES.md.$background"

if [[ "$(repo_state)" != "$before" ]]; then
  echo "pre-push review: the reviewer changed the repository; inspect with git status and git log." >&2
  exit 1
fi

if [[ -f ISSUES.md ]]; then
  cat ISSUES.md
  echo "Fix the relevant findings, or explain in BACKGROUND.md why not; delete ISSUES.md, then push again." >&2
  exit 1
fi
echo "pre-push review: no serious findings."
