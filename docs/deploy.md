# Deploying for judging

Button NZ is served from the machine that already runs it: the API, Blender on
its GPU in the sandbox, and the web app, as systemd user services. Both listen
on 127.0.0.1 only. A Cloudflare tunnel carries the web app to the internet, so
no inbound port opens. The API is reached only through the web app's `/api`
rewrite.

## What a public server adds

| | What it does | Where |
|---|---|---|
| Access code | Every page and `/api` request needs it. A link with `?code=` sets an HttpOnly, Secure cookie and drops the code from the address; anything else gets a 401 page. | `apps/web/proxy.ts`, `lib/access.ts` |
| Daily cap | At most `BUTTON_DAILY_DESIGNS` design runs, originals and revisions, start in any 24 hours. One past it is refused (429, with when the next frees up), never queued. Each run is Meta Model API calls and a GPU Blender run. | `serve --daily-designs`, `api/limits.py` |
| Fixed survey | The survey is served with who decided it, and changes to it are refused (403), so one visitor can't change what everyone's designs are checked against. | `serve --survey-decided-by`, `api/features.py` |
| Design links | `/?design=<id>` opens that design and the designs it revises; the address bar follows the design on show. A judge can open a finished design at once. | `useDesignChain.ts` |

Run locally, as in the README, none of these is on.

## Install

```bash
scripts/deploy/install.sh   # first run: writes ~/.config/button-nz/deploy.env and stops
$EDITOR ~/.config/button-nz/deploy.env
scripts/deploy/install.sh   # builds, writes the units, starts the services
```

`deploy.env` has the access code (generated), the data directory, the daily
cap and who decided the survey. The model key is read from the repository's
`.env` by the API's unit only; the web app's unit never gets it. Run
`install.sh` again after pulling new code. `systemctl --user status
button-api button-web button-tunnel` and `journalctl --user -u button-api`
show how they are.

The data directory holds the jobs database, their files and `survey.geojson`.
Point it at the directory where the owner decided the survey and made the
designs to link. Only one API may use a data directory at a time: each runs
its own worker over the same queue. So stop any other server on it first.

Next compiles its rewrites when it builds, so the API's address
(`127.0.0.1:8000`) is fixed at build time. `install.sh` builds with it.

## Tunnel

`cloudflared` is installed from Cloudflare's [release](https://github.com/cloudflare/cloudflared/releases)
in `~/.local/bin`, its SHA-256 checked against the release notes. A named
tunnel needs a Cloudflare account with a domain on it:

1. In the Cloudflare dashboard (Zero Trust → Networks → Tunnels), create a
   tunnel. Give it a public hostname, e.g. `button.<domain>`, with the service
   `http://127.0.0.1:3000`.
2. Put its token in `~/.config/button-nz/tunnel.env` (mode 600):
   `TUNNEL_TOKEN="<token>"`.
3. Run `scripts/deploy/install.sh` again, which adds the tunnel's service.

To try it before then, `cloudflared tunnel --url http://127.0.0.1:3000` gives
a temporary `trycloudflare.com` address. It changes on every start, and
Cloudflare offers no uptime for it, so don't submit it.

## Check it

```bash
scripts/deploy/check.sh https://button.<domain> "$BUTTON_ACCESS_CODE" [DESIGN_ID]
```

This checks:

- that the page, the API and a wrong code are refused;
- that the code's link sets the cookie;
- that the page and the site load;
- that the survey is fixed;
- if a design is given, that it is done.

It ends by printing the link to submit:
`https://button.<domain>/?design=<id>&code=<code>`.

## What is exposed

Through the tunnel, only the web app is reachable, and only with the code.
Behind it, the API serves:

- the demo site;
- its fixed survey;
- the design jobs: create, revise and read;
- the listed artifacts of each attempt (`api/app.py` refuses any other file
  name, and links).

Designs are model-written Blender scripts. They run in the sandbox
(`blender_worker/sandbox.py`):

- no network;
- a cleared environment, so no keys;
- read-only system files and no home directory;
- size-limited scratch space;
- memory and process caps.

A visitor's brief reaches the model, never a shell. The daily cap bounds what
the visitors can spend together.
