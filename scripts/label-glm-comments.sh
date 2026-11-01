#!/usr/bin/env bash
# Make sure every review comment GLM posted says it is GLM's (#142). GLM and
# Claude both post as github-actions[bot], so the "GLM review" prefix is the
# only way to tell their findings apart, and the prompt asking for it is not
# enforced. GLM's comments are found by the comment_id each successful
# create_inline_comment call returned in its transcript, never by author or
# time (Claude may be posting at the same moment). Each one's current body is
# fetched; any without the prefix gets it, with a warning in the job log.
set -euo pipefail

repo="${1:?usage: $0 <owner/repo> <execution-file>}"
trace="${2:?usage: $0 <owner/repo> <execution-file>}"
label="GLM review"

# One line per successful comment call: its comment_id, or "missing".
ids="$(jq -r '
  [.[] | select(.type == "assistant") | .message.content[]?
   | select(.type == "tool_use" and .name == "mcp__github_inline_comment__create_inline_comment")
   | .id] as $calls
  | .[] | select(.type == "user") | .message.content[]?
  | select(.type == "tool_result" and (.is_error | not) and (.tool_use_id | IN($calls[])))
  | [.content[]? | select(.type == "text") | .text | fromjson? | .comment_id // empty]
  | first // "missing"
' "$trace")"

for id in $ids; do
  if [[ "$id" == missing ]]; then
    echo "A comment GLM posted has no comment_id in the transcript; it can't be checked." >&2
    exit 1
  fi
  body="$(gh api "repos/$repo/pulls/comments/$id" --jq .body)"
  if [[ "$body" != "$label"* ]]; then
    gh api -X PATCH "repos/$repo/pulls/comments/$id" -f body="$label $body" > /dev/null
    echo "::warning::GLM's comment $id lacked the \"$label\" prefix; it was added."
  fi
done
