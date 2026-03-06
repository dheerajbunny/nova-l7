# NOVA — Layer 7: Dialogue Manager

## What This Layer Does
Layer 7 is the brain of NOVA. It receives every voice command,
understands what the driver wants, decides what to do,
and routes to the correct handler — all in under 100ms.

---

## Files
```
L-7/
├── main.py               — FastAPI server, WebSocket state broadcaster
├── dialogue_manager.py   — FSM, routing, buffer queue, interrupts
├── intent_classifier.py  — keyword-based intent classification
├── templates/
│   └── index.html        — browser demo UI
└── README.md             — this file
```

---

## How It Works

### Full Flow
```
Voice input (or typed text)
    ↓
Intent classifier → what type of command?
    ↓
Is it an interrupt? (stop/pause/emergency) → handle immediately
    ↓
Is it sensitive? (payment) → call Layer 3 for verification
    ↓
Missing info? (no destination) → ask for it (slot filling)
    ↓
Route to correct handler
    ↓
Return response + broadcast WebSocket state to UI
```

### Intents Supported
```
vehicle_control   → AC, windows, lights, fan — instant, no verification
navigation        → directions, routes — instant, no verification
media             → play, pause, skip — instant, no verification
general_question  → weather, news, questions — instant, no verification
communication     → calls, messages — instant, no verification
payment           → orders, bookings — requires Layer 3 + Voice OTP
```

### Interrupt Keywords
```
emergency / accident / call 911  → highest priority, clears everything
stop / cancel / nevermind        → clears queue and buffer
repeat / say that again          → replays last response
pause / hold on / wait           → saves current state
resume / continue / carry on     → restores paused state
help / what can you do           → lists all capabilities
what's in the queue              → reads buffer status
```

### Buffer Queue
```
Nova is answering question 1
Driver asks question 2 → saved to buffer (max 5)
Nova finishes question 1
speaking_done() called by TTS
Buffer auto-processes question 2
```

---

## Setup

### 1. Install Dependencies
```bash
pip install fastapi uvicorn jinja2 pydantic
```

### 2. Run as Administrator (Windows — needed for Layer 3)
```bash
# Open PowerShell as Administrator
cd D:\path\to\L-7
..\..\..\venv\Scripts\activate
python main.py
```

### 3. Open Browser
```
http://localhost:8000
```

### 4. WebSocket (for UI team)
```
ws://localhost:8000/ws
```

---

## Layer 3 Connection

Layer 7 automatically connects to Layer 3 on startup.
```
L-7/
└── dialogue_manager.py
        ↓ imports from
D:\path\to\L-3\
        ├── layer3_main.py → authenticate()
        ├── layer3_main.py → check_session()
        └── layer3_main.py → authorize_payment()
```

**If L-3 not found** — runs in simulation mode automatically.
Simulation mode auto-passes verification for demo/testing.

**Folder structure required:**
```
backend/
├── L-3/    ← must be here
│   ├── layer3_main.py
│   └── ... other L-3 files
└── L-7/    ← run from here
    ├── main.py
    └── dialogue_manager.py
```

---

## WebSocket Events — For UI Team

Connect to `ws://localhost:8000/ws`

Events broadcast by Layer 7:

| Event | When | UI Should Show |
|-------|------|----------------|
| `NOVA_IDLE` | Session reset | Sleeping screen |
| `NOVA_LISTENING` | Command received | Listening animation |
| `VERIFICATION_NEEDED` | Sensitive command | Lock screen |
| `VERIFICATION_FAIL` | Auth failed | Shake animation |
| `VERIFICATION_PASS` | Auth passed | Unlock animation |
| `PAYMENT_CONFIRM` | Confirm screen | Order details |
| `OTP_NEEDED` | OTP challenge | OTP screen |
| `PAYMENT_DONE` | Transaction complete | Receipt screen |
| `NOVA_SPEAKING` | Response ready | Show response text |

### Example WebSocket Client
```javascript
const ws = new WebSocket('ws://localhost:8000/ws')

ws.onmessage = (event) => {
    const { event: type, data } = JSON.parse(event.data)

    if (type === 'VERIFICATION_NEEDED') showLockScreen()
    if (type === 'VERIFICATION_FAIL')   shakeLockScreen()
    if (type === 'VERIFICATION_PASS')   unlockScreen()
    if (type === 'PAYMENT_DONE')        showReceipt(data)
    if (type === 'OTP_NEEDED')          showOTPScreen(data.otp)
}
```

---

## API Endpoints

| Method | Endpoint | What it does |
|--------|----------|-------------|
| GET | `/` | Browser demo UI |
| POST | `/chat` | Send command, get response |
| POST | `/reset` | Reset session |
| WS | `/ws` | WebSocket state stream |

### POST /chat
```json
Request:  { "message": "order a coffee from starbucks" }

Response: {
  "nova_says":    "Found Starbucks — 0.8km. Caramel Latte $6.50. Confirm?",
  "fsm_state":    "CONFIRM_PENDING",
  "intent":       "payment",
  "routing":      "Commerce tool — Maps + merchant API",
  "entities":     { "item": "coffee", "merchant": "starbucks" },
  "action":       null,
  "otp":          null,
  "queued":       false
}
```

---

## TTS Integration — When Ready

When Senthil connects TTS, add these two calls:

```python
# When TTS starts playing
dm.speaking_started()

# When TTS finishes playing
next_response = dm.speaking_done()
if next_response:
    tts.play(next_response["nova_says"])
```

This activates the buffer queue automatically.

---

## Security Model

```
Communication (calls, messages) → NO verification
  Reason: Voice at wake word already confirms identity
  Same as CarPlay / Android Auto behaviour

Payment / bookings / tool access → Layer 3 + Voice OTP
  Reason: Financial transaction — money involved
  Voice OTP is unique per transaction — replay proof
```

---

## Troubleshooting

**Layer 3 not found error**
Make sure L-3 folder is at `../L-3` relative to L-7.
Or runs in simulation mode — verification auto-passes.

**Port 8000 already in use**
```bash
# Find and kill process on port 8000
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

**WinError 1314**
Run PowerShell as Administrator — required for SpeechBrain symlinks.