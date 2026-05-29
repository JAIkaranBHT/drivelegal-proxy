# DriveLegal LLM Proxy (Railway)

A thin reverse proxy that hides the real LLM endpoint behind a URL **you** control.

## Why

The hackathon requires submitting a live API endpoint. We do not want to expose the real
upstream LLM URL, because:

- we don't control it and can't rotate it,
- an attacker could hit it directly and run up usage,
- we want to be able to **shut it off** the moment judging is done.

This proxy solves all three: it sits on **your** Railway service, keeps the real URL in a
server-side environment variable (never sent to any client), exposes the exact same contract
DriveLegal expects, and can be paused or deleted on Railway at any time to instantly cut off
access.

## Contract (identical to upstream — no DriveLegal code changes needed)

```
POST /            body: {"messages": [ ... ]}   -> {"completion": "<text>"}
POST /text/llm    (alias, same body)            -> {"completion": "<text>"}
GET  /health                                    -> {"status": "ok"}
```

## Environment variables (set in Railway → Variables)

| Variable           | Required | Purpose                                                                 |
| ------------------ | -------- | ----------------------------------------------------------------------- |
| `UPSTREAM_LLM_URL` | yes      | The REAL endpoint URL. Lives only here — never exposed to clients.      |
| `PROXY_TOKEN`      | optional | If set, callers must send header `X-Proxy-Token: <value>`. Locks the proxy to your own app. |
| `UPSTREAM_TIMEOUT` | optional | Upstream request timeout in seconds (default 30).                       |

## Deploy on Railway

1. Push this folder to a GitHub repo (e.g. `drivelegal-proxy`).
2. In Railway: **New Project → Deploy from GitHub repo** → pick the repo.
3. Under **Variables**, add `UPSTREAM_LLM_URL` (the real endpoint) and optionally `PROXY_TOKEN`.
4. Railway builds via Nixpacks and starts the app on its dynamic `$PORT`.
5. Under **Settings → Networking → Generate Domain** to get a public URL, e.g.
   `https://drivelegal-proxy-production.up.railway.app`.

## Point DriveLegal at the proxy

In the DriveLegal app's environment:

```bash
export DRIVELEGAL_LLM_MODE=rork
export DRIVELEGAL_RORK_URL=https://<your-railway-domain>/text/llm
# if you set PROXY_TOKEN, also configure DriveLegal to send the X-Proxy-Token header
```

**This is the URL you submit to the hackathon** — not the real upstream endpoint.

## After judging

Pause or delete the Railway service (or rotate `UPSTREAM_LLM_URL`) to immediately revoke all
access to the real endpoint. The submitted URL becomes inert and the real endpoint stays
private throughout.

## Run locally (optional test)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export UPSTREAM_LLM_URL=https://your-real-llm-endpoint.example.com/text/llm
uvicorn main:app --host 0.0.0.0 --port 8080
# then:  curl -s -X POST localhost:8080/text/llm -H 'Content-Type: application/json' \
#          -d '{"messages":[{"role":"user","content":"say OK"}]}'
```
