#!/usr/bin/env bash
# Download, decrypt and summarise the CI reviewer's latest transcripts, for
# retrospectives on the review process. Needs the "button-nz CI review traces"
# private key in the local GPG keyring. Decrypted transcripts stay in <out-dir>.
set -euo pipefail

count="${1:-10}"
out="${2:-$(mktemp -d)}"
scripts_dir="$(cd "$(dirname "$0")" && pwd)"

# Newest first. Collected before `head` so it cannot cut gh off mid-page.
artifacts="$(gh api --paginate 'repos/{owner}/{repo}/actions/artifacts?per_page=100' --jq '
  .artifacts[]
  | select(.expired | not)
  | select(.name | startswith("claude-review-trace"))
  | "\(.workflow_run.id) \(.name)"')"

if [[ -z "$artifacts" ]]; then
  echo "No review traces found."
  exit 0
fi

while read -r run name; do
  dir="$out/$run-$name"
  gh run download "$run" --name "$name" --dir "$dir"
  gpg --batch --quiet --decrypt "$dir/claude-review-trace.json.gpg" > "$dir/trace.json"
  printf '# Run %s (%s)\n\n' "$run" "$name"
  "$scripts_dir/review-metrics.sh" "$dir/trace.json"
  echo
done < <(head -n "$count" <<< "$artifacts")

echo "Decrypted transcripts: $out"
