#!/usr/bin/env bash
# Check a served Button NZ the way a judge reaches it:
#   scripts/deploy/check.sh https://demo.example.nz ACCESS_CODE [DESIGN_ID]
# Without the code it must refuse pages and the API; with the code's link it
# must set the cookie and serve the page, the site, a fixed survey and, if
# given, a finished design. Exits non-zero at the first thing that's wrong.
set -euo pipefail

url="${1:?usage: check.sh URL ACCESS_CODE [DESIGN_ID]}"
code="${2:?usage: check.sh URL ACCESS_CODE [DESIGN_ID]}"
design="${3:-}"
jar="$(mktemp)"
trap 'rm -f "$jar"' EXIT

status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
expect() {
  local want="$1" what="$2"; shift 2
  local got
  got="$(status "$@")"
  if [[ "$got" != "$want" ]]; then
    echo "FAIL $what: HTTP $got, expected $want" >&2
    exit 1
  fi
  echo "ok   $what ($got)"
}

expect 401 "the page without the code" "$url/"
expect 401 "the API without the code" "$url/api/site"
expect 401 "a wrong code" "$url/?code=not-$code"
expect 307 "the link with the code" -c "$jar" "$url/?code=$code"
expect 200 "the page with the cookie" -b "$jar" "$url/"
expect 200 "the site" -b "$jar" "$url/api/site"
fixed="$(curl -s -b "$jar" "$url/api/site/features" | jq -r '.fixed')"
[[ "$fixed" == true ]] || { echo "FAIL the survey isn't fixed (fixed=$fixed)" >&2; exit 1; }
echo "ok   the survey is fixed"
if [[ -n "$design" ]]; then
  state="$(curl -s -b "$jar" "$url/api/designs/$design" | jq -r '.status')"
  [[ "$state" == "done" ]] || { echo "FAIL design $design is $state, not done" >&2; exit 1; }
  echo "ok   design $design is done: $url/?design=$design&code=$code"
fi
