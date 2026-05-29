"""
DriveLegal LLM Proxy
====================
A thin reverse proxy that sits in front of the real LLM endpoint so that the
public submission only ever sees THIS Railway URL — never the underlying
provider URL.

Why this exists
---------------
- The hackathon requires submitting a live API endpoint URL.
- We do NOT want to expose the real upstream LLM endpoint (we don't control it,
  can't rotate it, and an attacker could hit it directly).
- This proxy:
    * keeps the real upstream URL in a server-side env var (UPSTREAM_LLM_URL),
      so it is never sent to any client;
    * exposes the exact same contract  POST {messages:[...]} -> {completion: str};
    * can be paused / deleted on Railway at any time after judging, instantly
      cutting off all access to the real endpoint;
    * optionally enforces a shared secret (PROXY_TOKEN) so only our own app can
      use it.

Contract (identical to the upstream so DriveLegal needs no code changes):
    POST /            body: {"messages": [{"role": "...", "content": "..."}]}
    POST /text/llm    (alias, same body)  -> {"completion": "<text>"}
    GET  /health      -> {"status": "ok"}
"""
import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# The REAL endpoint. Set this in Railway -> Variables. It is intentionally NOT
# given a default here so the real URL never appears in this (public) repo.
UPSTREAM_LLM_URL = os.getenv("UPSTREAM_LLM_URL", "")

# Optional shared secret. If set, callers must send header  X-Proxy-Token: <value>.
# Set the same value in DriveLegal's environment so only our app can call this.
PROXY_TOKEN = os.getenv("PROXY_TOKEN", "")

# Upstream request timeout (seconds).
TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "30"))

app = FastAPI(title="DriveLegal LLM Proxy", version="1.0")


def _check_auth(request: Request):
    if PROXY_TOKEN:
        if request.headers.get("X-Proxy-Token") != PROXY_TOKEN:
            raise HTTPException(status_code=401, detail="unauthorized")


async def _forward(request: Request):
    _check_auth(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    if "messages" not in body:
        raise HTTPException(status_code=400, detail="body must contain 'messages'")

    if not UPSTREAM_LLM_URL:
        raise HTTPException(status_code=500, detail="UPSTREAM_LLM_URL is not configured")

    # Forward ONLY the safe payload upstream. Strip client headers so nothing
    # leaks through; the real URL stays server-side.
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.post(UPSTREAM_LLM_URL, json={"messages": body["messages"]})
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"upstream error: {e.response.status_code}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"upstream unreachable: {type(e).__name__}")

    data = r.json()
    # Normalise to {"completion": str} regardless of minor upstream variations.
    completion = data.get("completion")
    if completion is None:
        # Some OpenAI-style endpoints nest the text differently; try a fallback.
        try:
            completion = data["choices"][0]["message"]["content"]
        except Exception:
            completion = ""
    return JSONResponse({"completion": completion})


@app.post("/")
async def root_llm(request: Request):
    return await _forward(request)


@app.post("/text/llm")
async def text_llm(request: Request):
    # Alias so DriveLegal can point at  https://<railway-url>/text/llm  and the
    # path matches the original upstream shape exactly.
    return await _forward(request)


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "service": "drivelegal-llm-proxy"}
