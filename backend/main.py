import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.auth import get_current_user_optional, require_auth
from backend.db import close_db, get_analysis_by_id, get_user_analyses, init_db, save_analysis
from backend.orchestrator import run_swarm

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("swarmiq")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="SwarmIQ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "message": "Rate limit exceeded — max 5 requests per minute per IP.",
        },
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client: aioredis.Redis | None = None


@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info(f"[Server] Redis connected — {REDIS_URL}")
    await init_db()


@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.aclose()
    await close_db()


# ── Session state ─────────────────────────────────────────────────────────────
connections: dict = {}
_active_analyses: int = 0
_MAX_CONCURRENT: int = 3

_SESSIONS_KEY = "active_sessions"


@app.websocket("/ws/{sid}")
async def websocket_endpoint(websocket: WebSocket, sid: str):
    await websocket.accept()
    connections[sid] = websocket
    logger.info(f"[{sid}] [WebSocket] connected")
    try:
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        connections.pop(sid, None)
        logger.error(f"[{sid}] [WebSocket] disconnected")


@app.get("/health")
async def health():
    redis_status = "not_initialized"
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "ok"
        except Exception as exc:
            redis_status = f"error: {exc}"
    return {"status": "ok", "service": "SwarmIQ", "version": "1.0", "redis": redis_status}


@app.get("/test")
async def test():
    return {
        "status": "ok",
        "message": "Backend running. Connect WebSocket at /ws/{session_id} then POST to /analyze",
    }


@app.get("/config")
async def get_config():
    """Exposes public MSAL config for the frontend (client ID and tenant ID are not secrets)."""
    tenant_id = os.getenv("AZURE_AD_TENANT_ID", "")
    client_id = os.getenv("AZURE_AD_CLIENT_ID", "")
    auth_enabled = bool(tenant_id and client_id)
    return {
        "authEnabled": auth_enabled,
        "clientId": client_id if auth_enabled else "",
        "tenantId": tenant_id if auth_enabled else "",
        "authority": f"https://login.microsoftonline.com/{tenant_id}" if auth_enabled else "",
    }


@app.post("/analyze")
@limiter.limit("5/minute")
async def analyze(request: Request, query: str = Form(...), session_id: str = Form(...)):
    global _active_analyses

    user = await get_current_user_optional(request)

    # Global concurrency cap
    if _active_analyses >= _MAX_CONCURRENT:
        logger.error(f"[{session_id}] [Server] capacity_exceeded — {_active_analyses} active")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "Swarm at capacity — please try again in 30 seconds.",
            },
        )

    # Per-session dedup via Redis SET
    try:
        if redis_client and await redis_client.sismember(_SESSIONS_KEY, session_id):
            return JSONResponse(
                status_code=409,
                content={"status": "error", "message": "Analysis already running for this session"},
            )
        if redis_client:
            await redis_client.sadd(_SESSIONS_KEY, session_id)
    except Exception as exc:
        logger.warning(f"[{session_id}] [Server] redis_session_check_failed — {exc}")

    _active_analyses += 1
    ws = connections.get(session_id)
    t0 = time.perf_counter()
    logger.info(f"[{session_id}] [Server] analyze_start — query={query[:60]!r}")

    async def emit(agent: str, status: str, message: str = "", **extra):
        if ws:
            try:
                payload = {"agent": agent, "status": status, "message": message}
                if extra:
                    payload.update(extra)
                await ws.send_text(json.dumps(payload))
            except Exception:
                pass

    try:
        result = await run_swarm(query, emit, session_id=session_id, redis_client=redis_client)

        if ws:
            try:
                await ws.send_text(json.dumps({
                    "agent": "SYSTEM",
                    "status": "complete",
                    "report": result["report"],
                    "critic": result["critic"],
                    "outputs": result.get("outputs", []),
                    "debate": result.get("debate", {}),
                }))
            except Exception:
                pass

        # Persist to Cosmos DB if the user is authenticated
        if user is not None:
            elapsed = time.perf_counter() - t0
            user_id = user.get("oid") or user.get("sub") or "anonymous"
            analysis_doc = {
                "user_id": user_id,
                "session_id": session_id,
                "query": query,
                "company": result.get("company", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(elapsed, 2),
                "specialist_outputs": result.get("outputs", []),
                "critic_result": result.get("critic", {}),
                "final_report": result.get("report", ""),
                "debate": result.get("debate", {}),
                "status": "completed",
            }
            try:
                await save_analysis(analysis_doc)
            except Exception as exc:
                logger.warning(f"[{session_id}] [DB] save_analysis failed — {exc}")

        ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"[{session_id}] [Server] analyze_complete — {ms}ms")
        return JSONResponse(content={"status": "ok"})

    except Exception as e:
        logger.error(f"[{session_id}] [Server] analyze_error — {e}")
        if ws:
            try:
                await ws.send_text(json.dumps({"agent": "SYSTEM", "status": "error", "message": str(e)}))
            except Exception:
                pass
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )

    finally:
        try:
            if redis_client:
                await redis_client.srem(_SESSIONS_KEY, session_id)
        except Exception as exc:
            logger.warning(f"[{session_id}] [Server] redis_session_remove_failed — {exc}")
        _active_analyses -= 1


@app.get("/history")
async def history(request: Request):
    """Return the last 10 analyses for the authenticated user."""
    user = await require_auth(request)
    user_id = user.get("oid") or user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Cannot determine user identity from token")
    analyses = await get_user_analyses(user_id, limit=10)
    return JSONResponse(content={"status": "ok", "analyses": analyses})


@app.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str, request: Request):
    """Return a full analysis document — only to its owner."""
    user = await require_auth(request)
    user_id = user.get("oid") or user.get("sub")
    doc = await get_analysis_by_id(analysis_id)
    if not doc or doc.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return JSONResponse(content={"status": "ok", "analysis": doc})


@app.post("/email-report")
async def email_report(request: Request):
    """Send the SwarmIQ intelligence report to the signed-in user's email.

    Body (JSON): {query, report, critic, debate (optional), to (optional override)}
    """
    user = await require_auth(request)
    user_email = (user.get("email") or user.get("preferred_username") or "").strip()
    user_name = (user.get("name") or user_email.split("@")[0] or "there").strip()

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    to_addr = (body.get("to") or user_email).strip()
    if not to_addr or "@" not in to_addr:
        raise HTTPException(status_code=400, detail="No deliverable email address on this account")

    query = (body.get("query") or "").strip()
    report_md = body.get("report") or ""
    critic = body.get("critic") or {}
    debate = body.get("debate") or {}
    if not report_md:
        raise HTTPException(status_code=400, detail="No report body to email")

    try:
        from backend.mailer import send_report_email
        send_report_email(
            to_email=to_addr,
            user_name=user_name,
            query=query,
            report_md=report_md,
            critic=critic,
            debate=debate,
        )
    except Exception as exc:
        logger.error(f"[Email] send_failed — {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse(content={"status": "ok", "delivered_to": to_addr})


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
