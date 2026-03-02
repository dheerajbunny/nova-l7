"""
NOVA Layer 7 - FastAPI Server
Connects the web UI to the dialogue manager.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dialogue_manager import DialogueManager
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="NOVA Layer 7 Demo")
templates = Jinja2Templates(directory="templates")

# One dialogue manager per server instance
dm = DialogueManager()


class ChatRequest(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
async def chat(req: ChatRequest):
    response = dm.process(req.message)
    return JSONResponse(content=response)


@app.post("/reset")
async def reset():
    """Reset the dialogue manager — new session."""
    global dm
    dm = DialogueManager()
    return {"status": "reset", "message": "Session cleared"}


if __name__ == "__main__":
    print("\n" + "="*50)
    print("  NOVA Layer 7 — Starting server")
    print("  Open browser at: http://localhost:8000")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)