#!/usr/bin/env bash
# Download, decrypt and summarise the CI reviewer's latest transcripts, for
# retrospectives on the review process. Needs the "button-nz CI review traces"
# private key in the local GPG keyring. Decrypted transcripts stay in <out-dir>.
set -euo pipefail

count="${1:-10}"
out="${2:-$(mktemp -d)}"
scripts_dir="$(cd "$(dirname "$0")" && pwd)"

# The API does not list artifacts in date order, so sort all pages newest first.
# Collected before `head` so it cannot cut gh off mid-page.
artifacts="$(gh api --paginate --slurp 'repos/{owner}/{repo}/actions/artifacts?per_page=100' \
  | jq -r '
    [.[].artifacts[]]
    | map(select((.expired | not) and (.name | startswith("claude-review-trace"))))
    | sort_by(.created_at) | reverse
    | .[] | "\(.workflow_run.id) \(.name)"')"

if [[ -z "$artifacts" ]]; then
  echo "No review traces found."
  exit 0
fi

while read -r run name; do
  dir="$out/$run-$name"
  gh run download "$run" --name "$name" --dir "$dir"
  gpg --batch --quiet --decrypt "$dir/claude-review-trace.json.gpg" > "$dir/trace.json"
  printf '# Run %s (%s)\n\n' "$run" "$name"
  # A review that ran no command (exit 3) fails the CI check; here it is just
  # reported. Any other failure is a real error and stops the script.
  status=0
  "$scripts_dir/review-metrics.sh" "$dir/trace.json" 2> "$dir/metrics.err" || status=$?
  if [[ $status -eq 3 ]]; then
    printf '\n**No review happened:** no shell command succeeded.\n'
  elif [[ $status -ne 0 ]]; then
    cat "$dir/metrics.err" >&2
    exit "$status"
  fi
  echo
done < <(head -n "$count" <<< "$artifacts")

echo "Decrypted transcripts: $out"
