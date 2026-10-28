#!/usr/bin/env bash
# Summarise a Claude Code execution file (the CI reviewer's transcript) as
# Markdown: model, turns, duration, cost, findings posted (inline comments
# whose call succeeded), tool calls (attempts), and denied calls. Prints tool
# names, commands and paths only, never output, so the summary is safe for the
# public job log. Exits 3 if no shell command succeeded (no review happened).
set -euo pipefail

trace="${1:?usage: $0 <execution-file>}"

jq -j '
  (map(select(.type == "result")) | last) as $result
  | if $result == null then error("no result message in \(input_filename)") else . end
  | (map(select(.type == "system" and .subtype == "init")) | first | .model // "unknown") as $model
  | [.[] | select(.type == "assistant") | .message.content[]? | select(.type == "tool_use")]
    as $uses
  | ($uses | map(.name)) as $tools
  | [.[] | select(.type == "user") | .message.content[]?
     | select(.type == "tool_result" and (.is_error | not)) | .tool_use_id] as $succeeded
  | [$uses[] | select(.name == "mcp__github_inline_comment__create_inline_comment")
     | select(.id | IN($succeeded[]))] as $posted
  | ($result.permission_denials // []) as $denied
  | ($result.total_cost_usd * 100 | round) as $cents
  | "## Claude review\n\n"
    + "| Model | Turns | Duration | Cost | Findings posted | Denied calls |\n"
    + "| --- | --- | --- | --- | --- | --- |\n"
    + "| \($model) | \($result.num_turns) | \($result.duration_ms / 1000 | floor)s"
    + " | $\($cents / 100 | floor).\($cents % 100 | tostring | if length < 2 then "0" + . else . end)"
    + " | \($posted | length)"
    + " | \($denied | length) |\n\n"
    + "**Tool calls:** "
    + (if $tools == [] then "none"
       else $tools | group_by(.) | map("\(.[0]) \(length)") | join(", ") end)
    + "\n"
    + (if $denied == [] then ""
       else "\n### Denied calls\n\n"
         + ($denied
            | map("- \(.tool_name) `\(.tool_input.command // .tool_input.file_path // "")`\n")
            | join(""))
       end)
    + (if $result.is_error then "\n**Error:** \($result.result)\n" else "" end)
' "$trace"

# A real review runs at least `git diff`. If no shell command succeeded (for
# example, the sandbox could not start them), fail rather than pass a review
# that never looked at the code.
if ! jq -e '
  [.[] | select(.type == "user") | .message.content[]?
   | select(.type == "tool_result" and (.is_error | not)) | .tool_use_id] as $succeeded
  | any(.[] | select(.type == "assistant") | .message.content[]?
        | select(.type == "tool_use" and .name == "Bash"); .id | IN($succeeded[]))
' "$trace" > /dev/null; then
  echo "The reviewer could not run a single shell command, so no review happened." >&2
  exit 3
fi
