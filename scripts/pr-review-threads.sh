#!/usr/bin/env bash
# Print a pull request's review threads as Markdown, so the CI reviewer can
# see earlier findings and the author's replies before reviewing again.
# The repo is public: anyone can comment, so only comments from maintainers and
# the reviewer bots are passed on. The rest are replaced with a placeholder.
set -euo pipefail

repo="${1:?usage: $0 <owner/repo> <pr-number>}"
number="${2:?usage: $0 <owner/repo> <pr-number>}"

# $owner, $name, $number and $endCursor are GraphQL variables, not shell
# expansions. --paginate follows $endCursor through every page of threads.
# shellcheck disable=SC2016
gh api graphql --paginate --slurp -f owner="${repo%%/*}" -f name="${repo#*/}" -F number="$number" -f query='
query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          path
          line
          isResolved
          comments(first: 100) {
            nodes { author { login __typename } authorAssociation body }
          }
        }
      }
    }
  }
}' | jq -j '
  [.[].data.repository.pullRequest.reviewThreads.nodes[]]
  | if length == 0 then "No earlier review threads.\n"
    else map(
      "## \(.path)\(if .line then ":\(.line)" else "" end)"
      + " (\(if .isResolved then "resolved" else "open" end))\n\n"
      + (.comments.nodes | map(
          if (.authorAssociation | IN("OWNER", "MEMBER", "COLLABORATOR"))
            or (.author.__typename == "Bot"
                and (.author.login | IN("github-actions", "chatgpt-codex-connector")))
          then "**\(.author.login):** \(.body)\n\n"
          else "(comment from an untrusted author omitted)\n\n"
          end
        ) | join(""))
    ) | join("")
    end'
