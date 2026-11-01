#!/usr/bin/env bash
# Serve Button NZ from this machine as systemd user services: the API (and
# Blender, sandboxed, on the GPU) and the web app, both on 127.0.0.1 only, and
# a Cloudflare tunnel to the web app once there is a tunnel token. See
# docs/deploy.md. Run it again after pulling new code.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
config="${XDG_CONFIG_HOME:-$HOME/.config}/button-nz"
units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
settings="$config/deploy.env"
tunnel="$config/tunnel.env"
api_port=8000
web_port=3000

mkdir -p "$config" "$units"
chmod 700 "$config"
if [[ ! -f "$settings" ]]; then
  umask 077
  code="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
  cat > "$settings" <<SETTINGS
# Button NZ deployment settings (the model key stays in $repo/.env).
# Read by systemd and by install.sh: keep every value in double quotes.
# The code judges' links carry: https://<host>/?code=<this>
BUTTON_ACCESS_CODE="$code"
# Jobs, their files and the survey (survey.geojson) live here.
BUTTON_DATA="$repo/var"
# Design runs started in any 24 hours, originals and revisions alike.
BUTTON_DAILY_DESIGNS="30"
# Who decided the survey this server serves, fixed. Leave it empty while the
# owner decides it in the app (anyone who can reach the app can then change it:
# with no access code, anyone at all), and set it, then run this again, once
# they have.
BUTTON_SURVEY_DECIDED_BY=""
SETTINGS
  echo "Wrote $settings: check BUTTON_DATA and BUTTON_SURVEY_DECIDED_BY, then run this again."
  exit 0
fi
# shellcheck source=/dev/null
source "$settings"
if [[ ! -f "$BUTTON_DATA/survey.geojson" ]]; then
  echo "No survey at $BUTTON_DATA/survey.geojson: survey the site first (README, \"Run it\")." >&2
  exit 1
fi
if ! grep -q '^META_API_KEY=.' "$repo/.env"; then
  echo "No META_API_KEY in $repo/.env." >&2
  exit 1
fi

# Tools the services need, found where this shell finds them. A missing one
# stops the install: nothing else here runs Blender, so the services would
# start and every design would fail.
for tool in uv node pnpm blender; do
  command -v "$tool" >/dev/null || { echo "$tool isn't on PATH." >&2; exit 1; }
done
path="$(dirname "$(command -v uv)"):$(dirname "$(command -v node)"):$(dirname "$(command -v blender)"):/usr/local/bin:/usr/bin:/bin"

(cd "$repo" && uv sync --frozen)
# Next compiles its rewrites when it builds, so the API's address is fixed here.
(cd "$repo/apps/web" && pnpm install --frozen-lockfile \
  && BUTTON_API_URL="http://127.0.0.1:$api_port" pnpm build)

cat > "$units/button-api.service" <<UNIT
[Unit]
Description=Button NZ API: design jobs, run by Muse and sandboxed Blender

[Service]
WorkingDirectory=$repo
Environment=PATH=$path
EnvironmentFile=$repo/.env
EnvironmentFile=$settings
ExecStart=$(command -v uv) run --frozen python -m button_nz.api.serve --host 127.0.0.1 --port $api_port --data \${BUTTON_DATA} --daily-designs \${BUTTON_DAILY_DESIGNS} --survey-decided-by \${BUTTON_SURVEY_DECIDED_BY}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

# The web app gets the access code, never the model key.
cat > "$units/button-web.service" <<UNIT
[Unit]
Description=Button NZ web app, behind its access code
After=button-api.service

[Service]
WorkingDirectory=$repo/apps/web
Environment=PATH=$path
Environment=NODE_ENV=production
EnvironmentFile=$settings
ExecStart=$(command -v pnpm) start --hostname 127.0.0.1 --port $web_port
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

services=(button-api.service button-web.service)
if [[ -f "$tunnel" ]]; then
  cloudflared="$(command -v cloudflared)" \
    || { echo "cloudflared isn't installed (docs/deploy.md, \"Tunnel\")." >&2; exit 1; }
  cat > "$units/button-tunnel.service" <<UNIT
[Unit]
Description=Cloudflare tunnel to the Button NZ web app
After=button-web.service

[Service]
EnvironmentFile=$tunnel
ExecStart=$cloudflared tunnel --no-autoupdate run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT
  services+=(button-tunnel.service)
else
  echo "No $tunnel yet: serving on 127.0.0.1:$web_port only (docs/deploy.md, \"Tunnel\")."
fi

systemctl --user daemon-reload
systemctl --user enable "${services[@]}"
systemctl --user restart "${services[@]}"
if [[ "$(loginctl show-user "$USER" -p Linger --value)" != yes ]]; then
  loginctl enable-linger "$USER" \
    || echo "Could not enable linger: the services stop at logout until 'sudo loginctl enable-linger $USER'." >&2
fi
systemctl --user --no-pager status "${services[@]}" | grep -E '●|Active:'
