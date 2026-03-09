"""
NOVA Layer 7 - Dialogue Manager
The brain that decides what to do with each intent.

UPDATES IN THIS VERSION:
- Layer 3 connected for real voice verification
- Selective verification — only payment and communication
- Vehicle, navigation, media, general_question = NO verification needed
- Context decay after 5 min silence
- pause / resume commands
- help keyword
- emergency keyword — highest priority
- queue overflow graceful rejection (max 5)
- queue read-aloud
- all-voice audit logging for OEM analytics
- FIFO QUEUE BUFFER — new commands during speaking go to buffer,
  auto-processed when current answer finishes
"""

from intent_classifier import IntentClassifier, IntentResult
from dataclasses import dataclass, field
from typing import Optional
import time
import random
import sys
import os

# ── Connect to Layer 3 ─────────────────────────────────────────────────────────
L3_PATH = os.path.join(os.path.dirname(__file__), '..', 'L-3')
sys.path.insert(0, os.path.abspath(L3_PATH))

L3_AVAILABLE = False
try:
    from layer3_main import check_session, authorize_payment, _create_and_register_token
    from verify import verify_voice
    from pin_handler import verify_pin
    from face_handler import verify_face
    L3_AVAILABLE = True
    print("[Layer 7] Layer 3 connected — real voice verification active")
except ImportError as e:
    print(f"[Layer 7] Layer 3 not available ({e}) — running in simulation mode")

# ── Connect to Audit Log ───────────────────────────────────────────────────────
AUDIT_AVAILABLE = False
try:
    from audit_log import log_event
    AUDIT_AVAILABLE = True
    print("[Layer 7] Audit log connected")
except ImportError:
    print("[Layer 7] Audit log not available — skipping logging")


# ── Constants ──────────────────────────────────────────────────────────────────
NEEDS_VERIFICATION     = ["payment", "communication"]
NO_VERIFICATION        = ["vehicle_control", "navigation", "media",
                          "general_question", "stop"]
CONTEXT_DECAY_SECONDS  = 300   # 5 minutes
QUEUE_MAX              = 5     # max items in buffer


# ── Dataclasses ────────────────────────────────────────────────────────────────
@dataclass
class ConversationTurn:
    role: str
    text: str
    intent: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class QueuedCommand:
    """A command saved to buffer while Nova was speaking."""
    text: str
    received_at: float = field(default_factory=time.time)


@dataclass
class DialogueState:
    fsm_state: str = "IDLE"
    current_intent: str = None
    pending_entities: dict = field(default_factory=dict)
    missing_slots: list = field(default_factory=list)
    slot_attempt: int = 0
    confirm_action: str = None
    confirm_details: dict = field(default_factory=dict)

    # Layer 3 session
    session_token: str = None
    session_valid: bool = False
    session_start: float = None
    session_duration: int = 900      # 15 minutes

    # Conversation
    history: list = field(default_factory=list)
    last_interaction: float = field(default_factory=time.time)

    # ── FIFO buffer ────────────────────────────────────────────────────────────
    # Commands received while Nova is speaking go here
    # After Nova finishes speaking — auto-process next from buffer
    command_buffer: list = field(default_factory=list)

    # Whether Nova is currently speaking (TTS playing)
    # Set True when response goes out, False when TTS finishes
    is_speaking: bool = False


# ── Response builder ───────────────────────────────────────────────────────────
def build_response(
    message: str,
    state: str,
    intent: str,
    routing: str,
    entities: dict = None,
    action: str = None,
    otp: list = None,
    verification_status: str = None,
    queued: bool = False,
    queue_position: int = None,
    buffered_response: dict = None,
    **kwargs
) -> dict:
    response = {
        "nova_says":        message,
        "fsm_state":        state,
        "intent":           intent,
        "routing":          routing,
        "entities":         entities or {},
        "action":           action,
        "otp":              otp,
        "verification_status": verification_status,
        "queued":           queued,           # True if command was saved to buffer
        "queue_position":   queue_position,   # position in buffer (1, 2, 3...)
        "buffered_response":buffered_response,# next queued response if any
        "timestamp":        time.time()
    }
    response.update(kwargs)
    return response


# ── Required slots ─────────────────────────────────────────────────────────────
REQUIRED_SLOTS = {
    "navigation":      ["destination"],
    "communication":   ["contact"],
    "payment":         [],
    "vehicle_control": ["component", "action"],
    "media":           [],
    "general_question":[],
    "stop":            [],
    "emergency":       [],
    "help":            [],
    "pause":           [],
    "resume":          [],
    "queue_status":    [],
}

SLOT_QUESTIONS = {
    "destination": "Where would you like to go?",
    "contact":     "Who would you like to call or message?",
    "component":   "Which component — AC, window, heater, or lights?",
    "action":      "Should I turn it on or off?",
}

# ── Interrupt keyword groups ───────────────────────────────────────────────────
EMERGENCY_KEYWORDS = ["emergency", "accident", "help me", "call 911", "call ambulance"]
STOP_KEYWORDS      = ["stop", "cancel", "quit", "shut up", "nevermind", "never mind"]
REPEAT_KEYWORDS    = ["repeat", "say that again", "say again", "what did you say"]
PAUSE_KEYWORDS     = ["pause", "hold on", "wait", "one second", "one moment"]
RESUME_KEYWORDS    = ["resume", "continue", "go ahead", "carry on"]
HELP_KEYWORDS      = ["help", "what can you do", "what do you know", "commands"]
QUEUE_KEYWORDS     = ["what's in the queue", "what is in the queue",
                      "how many requests", "what are you processing", "queue status"]


# ── Route handlers ─────────────────────────────────────────────────────────────
def handle_vehicle_control(entities: dict) -> dict:
    component = entities.get("component", "system")
    action    = entities.get("action", "on")
    return build_response(
        message=f"Done. {component.upper()} turned {action}.",
        state="IDLE", intent="vehicle_control",
        routing="Direct hardware command via CAN bus — no AI, no cost, under 50ms",
        entities=entities, action="hardware_command"
    )

def handle_navigation(entities: dict) -> dict:
    destination = entities.get("destination", "your destination")
    eta_minutes = random.randint(10, 45)
    distance_km = round(random.uniform(5, 30), 1)
    return build_response(
        message=f"Navigating to {destination}. Estimated {eta_minutes} minutes — {distance_km} km via fastest route.",
        state="IDLE", intent="navigation",
        routing="Maps API call — HERE / Google Maps — no LLM needed",
        entities=entities, action="maps_api_call"
    )

def handle_media(entities: dict) -> dict:
    query = entities.get("query", "your music")
    return build_response(
        message=f"Playing {query} on Spotify.",
        state="IDLE", intent="media",
        routing="Spotify API — direct call — no AI, no cost",
        entities=entities, action="spotify_api_call"
    )

def handle_general_question(text: str, history: list) -> dict:
    return build_response(
        message=f"Let me think about that...",
        state="IDLE", intent="general_question",
        routing="Local Qwen3.5 LLM with context",
        entities={}, action="llm_call",
        original_text=text
    )

def handle_communication(entities: dict) -> dict:
    contact = entities.get("contact", "contact")
    return build_response(
        message=f"Calling {contact} now.",
        state="IDLE", intent="communication",
        routing="Phone API — direct call",
        entities=entities, action="phone_call"
    )

def generate_otp() -> list:
    return [random.randint(0, 9) for _ in range(4)]

def otp_to_words(otp: list) -> str:
    words = ["zero","one","two","three","four","five",
             "six","seven","eight","nine"]
    return ", ".join(words[d] for d in otp)

def _log_command(driver_id: str, command: str, intent: str, is_verified: bool):
    if not AUDIT_AVAILABLE:
        return
    try:
        log_event(
            event_type="COMMAND", driver_id=driver_id, passed=is_verified,
            details={"command": command, "intent": intent, "is_verified": is_verified}
        )
    except Exception as e:
        print(f"[audit] Log failed: {e}")


# ── Main Dialogue Manager ──────────────────────────────────────────────────────
class DialogueManager:

    def __init__(self):
        self.classifier          = IntentClassifier()
        self.state               = DialogueState()
        self._otp_active         = None
        self._driver_id          = "driver1"
        self._paused_intent      = None
        self._paused_entities    = None
        self._last_nova_response = None

    # ══════════════════════════════════════════════════════════════════════════
    # BUFFER / QUEUE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def speaking_started(self):
        """
        Call this when TTS starts playing audio.
        While is_speaking=True, new commands go to buffer instead of
        being processed immediately.

        When TTS is connected — call dm.speaking_started() before playing audio.
        """
        self.state.is_speaking = True
        print("[dialogue] Nova started speaking — buffer active")

    def speaking_done(self) -> Optional[dict]:
        """
        Call this when TTS finishes playing audio.
        Automatically checks buffer and processes next queued command.

        When TTS is connected — call dm.speaking_done() after audio finishes.
        Returns next response if buffer had items, None if buffer was empty.

        Example in TTS code:
            tts.play(response_text)
            tts.wait_until_done()
            next_response = dm.speaking_done()
            if next_response:
                tts.play(next_response["nova_says"])
        """
        self.state.is_speaking = False
        print("[dialogue] Nova finished speaking — checking buffer...")

        if self.state.command_buffer:
            # Get next command from buffer (FIFO — first in, first out)
            next_command = self.state.command_buffer.pop(0)
            wait_time    = round(time.time() - next_command.received_at, 1)
            print(f"[dialogue] Processing buffered command: '{next_command.text}' "
                  f"(waited {wait_time}s)")

            # Process it now
            response = self._process_command(next_command.text)

            # Tell the response it came from buffer
            response["from_buffer"]  = True
            response["buffer_waited"] = wait_time

            if self.state.command_buffer:
                remaining = len(self.state.command_buffer)
                response["nova_says"] += f" ({remaining} more in queue)"

            return response

        print("[dialogue] Buffer empty — returning to IDLE")
        return None

    def _push_to_buffer(self, text: str) -> dict:
        """
        Save command to buffer when Nova is currently speaking.
        Returns acknowledgment response — NOT the actual answer.
        """
        position = len(self.state.command_buffer) + 1
        self.state.command_buffer.append(QueuedCommand(text=text))

        print(f"[dialogue] Buffered: '{text}' at position {position}")

        return build_response(
            message=f"Got it. I'll answer that next — finishing current response first.",
            state="BUFFERED",
            intent="buffered",
            routing=f"Command buffered at position {position} — will process after current response",
            queued=True,
            queue_position=position
        )

    # ══════════════════════════════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _is_session_valid(self) -> bool:
        if not self.state.session_valid or not self.state.session_token:
            return False
        if L3_AVAILABLE:
            try:
                result = check_session(self.state.session_token)
                return result.get("valid", False)
            except Exception:
                return False
        elapsed = time.time() - (self.state.session_start or 0)
        return elapsed < self.state.session_duration

    def _run_layer3_auth(self, audio_buffer=None) -> tuple:
        if L3_AVAILABLE:
            print("[Layer 7] Calling Layer 3 authenticate()...")
            token = authenticate(self._driver_id, audio_buffer=audio_buffer)
            return (True, token) if token else (False, "Authentication failed")
        print("[Layer 7] Simulation mode — auto-passing verification")
        self.state.session_start = time.time()
        self.state.session_valid = True
        return True, "simulated_token"

    def _start_session(self, token: str):
        self.state.session_token = token
        self.state.session_valid = True
        self.state.session_start = time.time()

    def _check_context_decay(self):
        silence = time.time() - self.state.last_interaction
        if silence > CONTEXT_DECAY_SECONDS:
            print(f"[dialogue] Context decayed after {int(silence)}s")
            self.state.history = []

    def _add_to_history(self, role: str, text: str, intent: str):
        self.state.history.append(
            ConversationTurn(role=role, text=text, intent=intent)
        )
        if len(self.state.history) > 10:
            self.state.history = self.state.history[-10:]
        self.state.last_interaction = time.time()

    def _resolve_context(self, text: str) -> str:
        import re
        text_lower       = text.lower()
        last_turns       = self.state.history[-2:]
        last_destinations = []
        last_contacts     = []

        for turn in last_turns:
            if turn.intent == "navigation":
                m = re.search(r"(?:to|at|near)\s+([A-Z][a-zA-Z\s]+)", turn.text)
                if m:
                    last_destinations.append(m.group(1).strip())
            if turn.intent == "communication":
                m = re.search(r"call\s+(\w+)", turn.text.lower())
                if m:
                    last_contacts.append(m.group(1))

        if any(w in text_lower for w in ["there", "that place", "same place"]):
            if last_destinations:
                text = re.sub(r"\b(there|that place|same place)\b",
                              last_destinations[-1], text, flags=re.IGNORECASE)
        if any(w in text_lower for w in ["him", "her", "them"]):
            if last_contacts:
                text = re.sub(r"\b(him|her|them)\b",
                              last_contacts[-1], text, flags=re.IGNORECASE)
        return text

    def _check_missing_slots(self, intent: str, entities: dict) -> list:
        return [s for s in REQUIRED_SLOTS.get(intent, []) if not entities.get(s)]

    def _store_response(self, response: dict) -> dict:
        if response.get("nova_says"):
            self._last_nova_response = response["nova_says"]
            self._add_to_history("nova", response["nova_says"],
                                 response.get("intent", ""))
        return response

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════════════════════

    def process(self, user_input: str, audio_buffer=None) -> dict:
        """
        Main entry point — call this for every user message.
        """
        user_input = user_input.strip()
        if not user_input:
            return build_response(
                message="I didn't catch that. Could you repeat?",
                state="IDLE", intent="unknown", routing="None"
            )

        text_lower = user_input.lower().strip()

        # ── Check if it's an interrupt — interrupts BYPASS buffer ─────────────
        is_interrupt = (
            any(kw in text_lower for kw in EMERGENCY_KEYWORDS) or
            any(kw in text_lower for kw in STOP_KEYWORDS)
        )

        # ── If Nova is speaking AND this is NOT an interrupt → buffer it ──────
        if self.state.is_speaking and not is_interrupt:
            if len(self.state.command_buffer) >= QUEUE_MAX:
                return build_response(
                    message="I already have several questions waiting. Please wait a moment.",
                    state="BUFFERED", intent="queue_full",
                    routing=f"Buffer full — max {QUEUE_MAX} items"
                )
            return self._push_to_buffer(user_input)

        # ── Not speaking or is interrupt — process normally ───────────────────
        return self._process_command(user_input, audio_buffer=audio_buffer)

    def _process_command(self, user_input: str, audio_buffer=None) -> dict:
        """
        Internal — actually processes the command.
        Called directly when not speaking, or from speaking_done() for buffered commands.
        """
        self._check_context_decay()
        text_lower = user_input.lower().strip()

        # ══════════════════════════════════════════════════════════════════════
        # INTERRUPT CHECKS — priority order
        # ══════════════════════════════════════════════════════════════════════

        # Emergency — absolute first
        if any(kw in text_lower for kw in EMERGENCY_KEYWORDS):
            self.state.is_speaking = False
            self.state.command_buffer.clear()
            self.state.fsm_state    = "IDLE"
            self.state.current_intent = None
            self._otp_active        = None
            _log_command(self._driver_id, user_input, "emergency",
                         self._is_session_valid())
            return self._store_response(build_response(
                message="Emergency detected. Automatically calling 911 and alerting your family members, Mom and Dad. Please stay calm.",
                state="IDLE", intent="emergency",
                routing="Emergency — absolute highest priority — buffer cleared",
                action="emergency_call"
            ))

        # Stop — clears buffer too
        if any(kw in text_lower for kw in STOP_KEYWORDS):
            self.state.is_speaking = False
            self.state.command_buffer.clear()
            self.state.fsm_state    = "IDLE"
            self.state.current_intent = None
            self._otp_active        = None
            self._paused_intent     = None
            _log_command(self._driver_id, user_input, "stop",
                         self._is_session_valid())
            return self._store_response(build_response(
                message="Stopped. Buffer and queue cleared. Ready for commands.",
                state="IDLE", intent="stop",
                routing="Interrupt — immediate halt — buffer + queue flushed"
            ))

        # Repeat
        if any(kw in text_lower for kw in REPEAT_KEYWORDS):
            if self._last_nova_response:
                return self._store_response(build_response(
                    message=self._last_nova_response,
                    state="IDLE", intent="repeat",
                    routing="Repeat last response"
                ))
            return self._store_response(build_response(
                message="Nothing to repeat yet.",
                state="IDLE", intent="repeat", routing="No previous response"
            ))

        # Pause
        if any(kw in text_lower for kw in PAUSE_KEYWORDS):
            if self.state.current_intent:
                self._paused_intent   = self.state.current_intent
                self._paused_entities = self.state.pending_entities.copy()
                self.state.fsm_state  = "IDLE"
                _log_command(self._driver_id, user_input, "pause",
                             self._is_session_valid())
                return self._store_response(build_response(
                    message=f"Paused. Saved your {self._paused_intent} request. Say resume when ready.",
                    state="IDLE", intent="pause",
                    routing="Paused — intent saved — context preserved"
                ))
            return self._store_response(build_response(
                message="Nothing active to pause.",
                state="IDLE", intent="pause", routing="Nothing to pause"
            ))

        # Resume
        if any(kw in text_lower for kw in RESUME_KEYWORDS):
            if self._paused_intent:
                restored_intent   = self._paused_intent
                restored_entities = self._paused_entities
                self._paused_intent = None
                self._paused_entities = None
                self.state.current_intent   = restored_intent
                self.state.pending_entities = restored_entities
                _log_command(self._driver_id, user_input, "resume",
                             self._is_session_valid())
                filled = IntentResult(intent=restored_intent, confidence=1.0,
                                      entities=restored_entities, raw_text=user_input)
                response = self._route(filled)
                response["resume_message"] = f"Resuming your {restored_intent} request."
                return self._store_response(response)
            return self._store_response(build_response(
                message="Nothing to resume.",
                state="IDLE", intent="resume", routing="No paused context"
            ))

        # Help
        if any(kw in text_lower for kw in HELP_KEYWORDS):
            _log_command(self._driver_id, user_input, "help",
                         self._is_session_valid())
            return self._store_response(build_response(
                message=(
                    "Here's what I can help with: "
                    "Vehicle controls — AC, windows, lights. "
                    "Navigation — directions and routes. "
                    "Music — play, pause, skip. "
                    "Calls and messages — hands free. "
                    "Payments — order food, fuel, parking. "
                    "General questions — weather, news, anything. "
                    "Say stop to cancel. Say pause to hold. Say repeat to hear again."
                ),
                state="IDLE", intent="help",
                routing="Help message delivered"
            ))

        # Queue status
        if any(kw in text_lower for kw in QUEUE_KEYWORDS):
            buf = self.state.command_buffer
            if not buf:
                msg = "Buffer is empty. Ready for your next command."
            else:
                items = ", ".join(f'"{c.text}"' for c in buf[:5])
                msg   = f"I have {len(buf)} command{'s' if len(buf)>1 else ''} waiting: {items}"
            return self._store_response(build_response(
                message=msg, state="IDLE", intent="queue_status",
                routing="Buffer status read aloud"
            ))

        # ══════════════════════════════════════════════════════════════════════
        # SPECIAL FSM STATES
        # ══════════════════════════════════════════════════════════════════════

        if self.state.fsm_state == "SLOT_FILL":
            return self._store_response(self._handle_slot_fill(user_input))

        if self.state.fsm_state == "CONFIRM_PENDING":
            return self._store_response(self._handle_confirmation(user_input))

        if self.state.fsm_state == "OTP_PENDING":
            return self._store_response(self._handle_otp(user_input))

        if self.state.fsm_state == "VERIFY":
            return self._store_response(self._handle_verify_voice(user_input, audio_buffer))

        if self.state.fsm_state == "VERIFY_PIN":
            return self._store_response(self._handle_verify_pin(user_input))

        if self.state.fsm_state == "VERIFY_FACE":
            return self._store_response(self._handle_verify_face(user_input))

        # ══════════════════════════════════════════════════════════════════════
        # NORMAL FLOW
        # ══════════════════════════════════════════════════════════════════════

        resolved_text = self._resolve_context(user_input)
        result        = self.classifier.classify(resolved_text)
        self._add_to_history("user", user_input, result.intent)

        # Log for OEM analytics
        _log_command(
            driver_id   = self._driver_id if self._is_session_valid() else "unknown_user",
            command     = user_input,
            intent      = result.intent,
            is_verified = self._is_session_valid()
        )

        # Verification for sensitive intents
        if result.intent in NEEDS_VERIFICATION:
            if not self._is_session_valid():
                self.state.fsm_state        = "VERIFY"
                self.state.pending_entities = result.entities
                self.state.current_intent   = result.intent
                return self._store_response(build_response(
                    message="This action requires identity verification. Please verify your identity.",
                    state="VERIFY", intent=result.intent,
                    routing="Layer 3 — voice biometric required",
                    verification_status="needed"
                ))

        # Slot filling
        missing = self._check_missing_slots(result.intent, result.entities)
        if missing:
            self.state.fsm_state        = "SLOT_FILL"
            self.state.current_intent   = result.intent
            self.state.pending_entities = result.entities
            self.state.missing_slots    = missing
            self.state.slot_attempt     = 0
            question = SLOT_QUESTIONS.get(missing[0], f"What is the {missing[0]}?")
            return self._store_response(build_response(
                message=question, state="SLOT_FILL", intent=result.intent,
                routing=f"Slot filling — missing: {missing}",
                entities=result.entities
            ))

        return self._store_response(self._route(result))

    # ── Route ──────────────────────────────────────────────────────────────────

    def _route(self, result: IntentResult) -> dict:
        if result.intent == "vehicle_control":
            return handle_vehicle_control(result.entities)
        elif result.intent == "navigation":
            return handle_navigation(result.entities)
        elif result.intent == "media":
            return handle_media(result.entities)
        elif result.intent == "communication":
            return handle_communication(result.entities)
        elif result.intent == "general_question":
            return handle_general_question(result.raw_text, self.state.history)
        elif result.intent == "payment":
            self.state.fsm_state      = "CONFIRM_PENDING"
            self.state.confirm_action = "payment"
            self.state.confirm_details = {
                "item":   result.raw_text,
                "amount": result.entities.get("amount", "unknown amount")
            }
            return build_response(
                message=f"Please confirm: '{result.raw_text}'. Say YES to proceed or NO to cancel.",
                state="CONFIRM_PENDING", intent="payment",
                routing="Confirm Pending — explicit confirmation required"
            )
        else:
            return handle_general_question(result.raw_text, self.state.history)

    # ── State handlers ─────────────────────────────────────────────────────────

    def _handle_verify_voice(self, user_input: str, audio_buffer=None) -> dict:
        print(f"[Layer 7] Starting Layer 3 auth for: {self._driver_id}")
        
        if L3_AVAILABLE and audio_buffer is not None:
            # Try voice first
            result = verify_voice(self._driver_id, verbose=True, audio_buffer=audio_buffer)
            
            if result.get("error") or not result["passed"]:
                self.state.fsm_state = "VERIFY_PIN"
                return build_response(
                    message="Voice not recognized. Please say your PIN number.",
                    state="VERIFY_PIN", intent="verify",
                    routing="Layer 3 — voice failed, falling back to PIN",
                    verification_status="needed"
                )
            
            # Voice passed! Create token.
            token = _create_and_register_token(self._driver_id, "voice", verbose=True)
            self._start_session(token)
            self.state.fsm_state = "IDLE"
            
            filled = IntentResult(
                intent=self.state.current_intent, confidence=1.0,
                entities=self.state.pending_entities, raw_text=user_input
            )
            response = self._route(filled)
            response["verify_message"]      = "Voice recognized. Identity verified."
            response["session_started"]     = True
            response["verification_status"] = "passed"
            return response
            
        elif not L3_AVAILABLE:
            # Simulation
            self.state.session_start = time.time()
            self.state.session_valid = True
            self.state.fsm_state = "IDLE"
            filled = IntentResult(
                intent=self.state.current_intent, confidence=1.0,
                entities=self.state.pending_entities, raw_text=user_input
            )
            response = self._route(filled)
            response["verify_message"]      = "Identity verified (simulation)."
            response["session_started"]     = True
            response["verification_status"] = "passed"
            return response
            
        return build_response(
            message="No audio buffer provided for verification.",
            state="IDLE", intent="verify",
            routing="Layer 3 — Missing audio buffer",
            action="verification_failed", verification_status="failed"
        )

    def _handle_verify_pin(self, user_input: str) -> dict:
        if L3_AVAILABLE:
            result = verify_pin(self._driver_id, user_input, verbose=True)
            if result.get("error") or not result["passed"]:
                self.state.fsm_state = "VERIFY_FACE"
                return build_response(
                    message="PIN incorrect. Please look at the cabin camera for Face ID.",
                    state="VERIFY_FACE", intent="verify",
                    routing="Layer 3 — PIN failed, falling back to Face ID",
                    verification_status="needed"
                )
                
            token = _create_and_register_token(self._driver_id, "pin", verbose=True)
            self._start_session(token)
            self.state.fsm_state = "IDLE"
            
            filled = IntentResult(
                intent=self.state.current_intent, confidence=1.0,
                entities=self.state.pending_entities, raw_text=user_input
            )
            response = self._route(filled)
            response["verify_message"]      = "PIN accepted. Identity verified."
            response["session_started"]     = True
            response["verification_status"] = "passed"
            return response
            
    def _handle_verify_face(self, user_input: str) -> dict:
        if L3_AVAILABLE:
            result = verify_face(self._driver_id, verbose=True)
            if result.get("error") or not result["passed"]:
                self.state.fsm_state = "IDLE"
                self.state.current_intent = None
                return build_response(
                    message="Face ID failed. Identity verification failed. Access denied.",
                    state="IDLE", intent="verify",
                    routing="Layer 3 — all levels failed",
                    action="verification_failed", verification_status="failed"
                )
                
            token = _create_and_register_token(self._driver_id, "face", verbose=True)
            self._start_session(token)
            self.state.fsm_state = "IDLE"
            
            filled = IntentResult(
                intent=self.state.current_intent, confidence=1.0,
                entities=self.state.pending_entities, raw_text=user_input
            )
            response = self._route(filled)
            response["verify_message"]      = "Face recognized. Identity verified."
            response["session_started"]     = True
            response["verification_status"] = "passed"
            return response

    def _handle_slot_fill(self, user_input: str) -> dict:
        self.state.slot_attempt += 1
        if self.state.slot_attempt > 3:
            self.state.fsm_state    = "IDLE"
            self.state.current_intent = None
            return build_response(
                message="I'm sorry, I couldn't understand. Please try again.",
                state="IDLE", intent=self.state.current_intent or "unknown",
                routing="Slot fill failed after 3 attempts"
            )
        missing_slot = self.state.missing_slots[0]
        self.state.pending_entities[missing_slot] = user_input
        self.state.missing_slots.pop(0)
        if self.state.missing_slots:
            question = SLOT_QUESTIONS.get(self.state.missing_slots[0],
                                          f"What is the {self.state.missing_slots[0]}?")
            return build_response(
                message=question, state="SLOT_FILL",
                intent=self.state.current_intent,
                routing=f"Slot filling — still missing: {self.state.missing_slots}",
                entities=self.state.pending_entities
            )
        self.state.fsm_state = "IDLE"
        filled = IntentResult(
            intent=self.state.current_intent, confidence=1.0,
            entities=self.state.pending_entities.copy(), raw_text=user_input
        )
        return self._route(filled)

    def _handle_confirmation(self, user_input: str) -> dict:
        yes_words  = ["yes","yeah","yep","confirm","proceed","ok","okay","sure","do it"]
        no_words   = ["no","nope","cancel","stop","don't","abort"]
        user_lower = user_input.lower().strip()
        if any(w in user_lower for w in yes_words):
            self.state.fsm_state = "OTP_PENDING"
            otp = generate_otp()
            self._otp_active = otp
            return build_response(
                message=f"Voice OTP: Please repeat — {otp_to_words(otp)}.",
                state="OTP_PENDING", intent="payment",
                routing="Voice OTP — unique per transaction",
                otp=otp
            )
        elif any(w in user_lower for w in no_words):
            self.state.fsm_state    = "IDLE"
            self.state.confirm_action = None
            return build_response(
                message="Payment cancelled.",
                state="IDLE", intent="payment",
                routing="Payment cancelled by driver"
            )
        else:
            return build_response(
                message="Please say YES to confirm or NO to cancel.",
                state="CONFIRM_PENDING", intent="payment",
                routing="Waiting for YES or NO"
            )

    def _handle_otp(self, user_input: str) -> dict:
        number_words = {
            "zero":0,"one":1,"two":2,"three":3,"four":4,
            "five":5,"six":6,"seven":7,"eight":8,"nine":9,
            "0":0,"1":1,"2":2,"3":3,"4":4,"5":5,
            "6":6,"7":7,"8":8,"9":9
        }
        spoken = [number_words[w.strip(".,!?")] for w in user_input.lower().split()
                  if w.strip(".,!?") in number_words]

        if spoken == self._otp_active:
            self.state.fsm_state = "IDLE"
            self._otp_active     = None
            return build_response(
                message="OTP verified. Payment authorized. Transaction sent — digitally signed.",
                state="IDLE", intent="payment",
                routing="Payment Layer 8 — digitally signed",
                action="payment_authorized"
            )
        else:
            self.state.fsm_state = "IDLE"
            self._otp_active     = None
            return build_response(
                message="OTP did not match. Payment denied. Please try again.",
                state="IDLE", intent="payment",
                routing="OTP failed — payment denied",
                action="payment_denied"
            )


# ── Quick test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dm = DialogueManager()

    print("\n" + "="*60)
    print("  NOVA Layer 7 — Buffer / Queue Test")
    print(f"  Layer 3: {L3_AVAILABLE}  |  Audit: {AUDIT_AVAILABLE}")
    print("="*60)

    # ── Test 1: Buffer behaviour ───────────────────────────────────────────────
    print("\n--- TEST: Buffer while speaking ---")

    # Simulate Nova starting to speak
    r1 = dm.process("navigate to the airport")
    print(f"\n  CMD    : navigate to the airport")
    print(f"  Nova   : {r1['nova_says']}")
    print(f"  State  : {r1['fsm_state']}")

    # Simulate TTS started
    dm.speaking_started()

    # New command arrives while Nova is speaking — should go to buffer
    r2 = dm.process("also play some music")
    print(f"\n  CMD    : also play some music (Nova is speaking)")
    print(f"  Nova   : {r2['nova_says']}")
    print(f"  Queued : {r2['queued']}  Position: {r2['queue_position']}")

    # Another command — also goes to buffer
    r3 = dm.process("what is the weather")
    print(f"\n  CMD    : what is the weather (Nova still speaking)")
    print(f"  Nova   : {r3['nova_says']}")
    print(f"  Queued : {r3['queued']}  Position: {r3['queue_position']}")

    # Simulate TTS finished — should auto-process next from buffer
    print(f"\n  [TTS finished — calling speaking_done()]")
    next_r = dm.speaking_done()
    if next_r:
        print(f"  Auto   : {next_r['nova_says']}")
        print(f"  Buffer : {next_r.get('from_buffer')}  Waited: {next_r.get('buffer_waited')}s")

    # ── Test 2: Emergency bypasses buffer ─────────────────────────────────────
    print("\n--- TEST: Emergency bypasses buffer ---")
    dm.speaking_started()
    r4 = dm.process("emergency")
    print(f"  CMD    : emergency (Nova is speaking)")
    print(f"  Nova   : {r4['nova_says']}")
    print(f"  Queued : {r4.get('queued', False)}  ← should be False — bypassed buffer")

    # ── Test 3: Normal flow ────────────────────────────────────────────────────
    print("\n--- TEST: Normal commands (not speaking) ---")
    normal_tests = [
        "turn on the AC",
        "help",
        "what's in the queue",
        "pause",
        "resume",
        "stop",
    ]
    for cmd in normal_tests:
        r = dm.process(cmd)
        print(f"\n  CMD  : {cmd}")
        print(f"  Nova : {r['nova_says']}")
        print(f"  State: {r['fsm_state']}")