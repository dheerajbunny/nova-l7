"""
NOVA Layer 7 - FastAPI Server
Connects the web UI to the dialogue manager.
Now includes WebSocket state broadcasting for Miti's UI.
"""

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dialogue_manager import DialogueManager
from pydantic import BaseModel
import uvicorn
import json

app = FastAPI(title="NOVA Layer 7 Demo")
templates = Jinja2Templates(directory="templates")

# One dialogue manager per server instance
dm = DialogueManager()

# Active WebSocket connections — Miti's UI connects here
active_connections: list[WebSocket] = []


# ── WebSocket state broadcaster ────────────────────────────────────────────────
async def broadcast_state(event: str, data: dict = {}):
    """
    Broadcast state change to all connected UIs.
    Miti's UI listens to these events and shows correct visuals.

    Events:
        NOVA_IDLE           → sleeping screen
        NOVA_LISTENING      → listening animation
        VERIFICATION_NEEDED → show lock screen
        VERIFICATION_FAIL   → shake animation + incorrect
        VERIFICATION_PASS   → unlock animation
        NOVA_SPEAKING       → show response text
        PAYMENT_CONFIRM     → show confirm screen
        PAYMENT_DONE        → show success screen
        OTP_NEEDED          → show OTP input screen
    """
    message = json.dumps({"event": event, "data": data})
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except Exception:
            disconnected.append(connection)
    for c in disconnected:
        active_connections.remove(c)


# ── WebSocket endpoint ─────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    print(f"[ws] UI connected. Total connections: {len(active_connections)}")
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print(f"[ws] UI disconnected. Total connections: {len(active_connections)}")


# ── REST endpoints ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
async def chat(req: ChatRequest):
    # Broadcast listening state to UI
    await broadcast_state("NOVA_LISTENING", {"input": req.message})

    # Process through dialogue manager
    response = dm.process(req.message)

    # Broadcast correct state based on response
    fsm_state = response.get("fsm_state", "IDLE")

    if fsm_state == "VERIFY":
        await broadcast_state("VERIFICATION_NEEDED", {
            "message": response.get("nova_says", "")
        })

    elif response.get("action") == "verification_failed":
        await broadcast_state("VERIFICATION_FAIL", {
            "message": response.get("nova_says", "")
        })

    elif response.get("session_started"):
        await broadcast_state("VERIFICATION_PASS", {
            "message": response.get("nova_says", "")
        })

    elif fsm_state == "CONFIRM_PENDING":
        await broadcast_state("PAYMENT_CONFIRM", {
            "message": response.get("nova_says", "")
        })

    elif fsm_state == "OTP_PENDING":
        await broadcast_state("OTP_NEEDED", {
            "message": response.get("nova_says", ""),
            "otp": response.get("otp", [])
        })

    elif response.get("action") == "payment_authorized":
        await broadcast_state("PAYMENT_DONE", {
            "message": response.get("nova_says", "")
        })

    elif fsm_state == "IDLE":
        await broadcast_state("NOVA_SPEAKING", {
            "message": response.get("nova_says", "")
        })

    return JSONResponse(content=response)


@app.post("/reset")
async def reset():
    """Reset the dialogue manager — new session."""
    global dm
    dm = DialogueManager()
    await broadcast_state("NOVA_IDLE", {})
    return {"status": "reset", "message": "Session cleared"}


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  NOVA Layer 7 — Starting server")
    print("  Open browser at: http://localhost:8000")
    print("  WebSocket at:    ws://localhost:8000/ws")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)