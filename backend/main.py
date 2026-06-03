import asyncio
import json

import uvicorn
from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.orchestrator import run_swarm

app = FastAPI(title="SwarmIQ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

connections: dict = {}
active_sessions: set = set()


@app.websocket("/ws/{sid}")
async def websocket_endpoint(websocket: WebSocket, sid: str):
    await websocket.accept()
    connections[sid] = websocket
    try:
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        connections.pop(sid, None)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "SwarmIQ", "version": "1.0"}


@app.get("/test")
async def test():
    return {"status": "ok", "message": "Backend running. Connect WebSocket at /ws/{session_id} then POST to /analyze"}


@app.post("/analyze")
async def analyze(query: str = Form(...), session_id: str = Form(...)):
    if session_id in active_sessions:
        return {"status": "error", "message": "Analysis already running for this session"}

    active_sessions.add(session_id)
    ws = connections.get(session_id)

    async def emit(agent: str, status: str, message: str = ""):
        if ws:
            try:
                await ws.send_text(json.dumps({"agent": agent, "status": status, "message": message}))
            except Exception:
                pass

    try:
        result = await run_swarm(query, emit)

        if ws:
            try:
                await ws.send_text(json.dumps({
                    "agent": "SYSTEM",
                    "status": "complete",
                    "report": result["report"],
                    "critic": result["critic"],
                }))
            except Exception:
                pass

        return {"status": "ok"}

    except Exception as e:
        if ws:
            try:
                await ws.send_text(json.dumps({"agent": "SYSTEM", "status": "error", "message": str(e)}))
            except Exception:
                pass
        return {"status": "error", "message": str(e)}

    finally:
        active_sessions.discard(session_id)


app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
