"""
NOVA Layer 7 - Dialogue Manager
The brain that decides what to do with each intent.
States: IDLE, PROCESSING, SLOT_FILL, CONFIRM_PENDING, SPEAKING
"""

from intent_classifier import IntentClassifier, IntentResult
from dataclasses import dataclass, field
from typing import Optional
import time
import random


# ── Session state ───────────────────────────────────────────────────────────

@dataclass
class ConversationTurn:
    role: str        # "user" or "nova"
    text: str
    intent: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class DialogueState:
    fsm_state: str = "IDLE"          # current FSM state
    current_intent: str = None       # what we are handling
    pending_entities: dict = field(default_factory=dict)    # slots filled so far
    missing_slots: list = field(default_factory=list)       # slots still needed
    slot_attempt: int = 0            # how many times we asked
    confirm_action: str = None       # what we are confirming
    confirm_details: dict = field(default_factory=dict)     # details for confirm
    session_valid: bool = False      # is identity verified
    session_start: float = None      # when session started
    session_duration: int = 900      # 15 minutes in seconds
    history: list = field(default_factory=list)  # conversation history
    queue: list = field(default_factory=list)     # queued commands


# ── Response builder ────────────────────────────────────────────────────────

def build_response(
    message: str,
    state: str,
    intent: str,
    routing: str,
    entities: dict = None,
    action: str = None,
    otp: list = None
) -> dict:
    return {
        "nova_says": message,
        "fsm_state": state,
        "intent": intent,
        "routing": routing,
        "entities": entities or {},
        "action": action,
        "otp": otp,
        "timestamp": time.time()
    }


# ── Required slots per intent ───────────────────────────────────────────────

REQUIRED_SLOTS = {
    "navigation": ["destination"],
    "communication": ["contact"],
    "payment": [],      # no slots — goes to Layer 3 auth
    "vehicle_control": ["component", "action"],
    "media": [],        # query optional
    "general_question": [],
    "stop": [],
}

SLOT_QUESTIONS = {
    "destination": "Where would you like to go?",
    "contact": "Who would you like to call?",
    "component": "Which component — AC, window, heater, or lights?",
    "action": "Should I turn it on or off?",
}


# ── Route handlers ──────────────────────────────────────────────────────────

def handle_vehicle_control(entities: dict) -> dict:
    component = entities.get("component", "system")
    action = entities.get("action", "on")
    return build_response(
        message=f"Done. {component.upper()} turned {action}.",
        state="IDLE",
        intent="vehicle_control",
        routing="Direct hardware command via CAN bus — no AI, no cost, under 50ms",
        entities=entities,
        action="hardware_command"
    )


def handle_navigation(entities: dict) -> dict:
    destination = entities.get("destination", "your destination")
    # Simulate maps API response
    eta_minutes = random.randint(10, 45)
    distance_km = round(random.uniform(5, 30), 1)
    return build_response(
        message=f"Navigating to {destination}. Estimated {eta_minutes} minutes — {distance_km} km via fastest route.",
        state="IDLE",
        intent="navigation",
        routing="Maps API call — HERE / Google Maps — no LLM needed",
        entities=entities,
        action="maps_api_call"
    )


def handle_media(entities: dict) -> dict:
    query = entities.get("query", "your music")
    return build_response(
        message=f"Playing {query} on Spotify.",
        state="IDLE",
        intent="media",
        routing="Spotify API — direct call — no AI, no cost",
        entities=entities,
        action="spotify_api_call"
    )


def handle_general_question(text: str, history: list) -> dict:
    context_turns = len(history)
    return build_response(
        message=f"Let me think about that... (LLM response would stream here with {context_turns} turns of context attached)",
        state="IDLE",
        intent="general_question",
        routing="LLM via OpenRouter — Mistral-7B — full conversation context attached",
        entities={},
        action="llm_call"
    )


def handle_communication(entities: dict) -> dict:
    contact = entities.get("contact", "contact")
    return build_response(
        message=f"Calling {contact} now.",
        state="IDLE",
        intent="communication",
        routing="Phone API — direct call",
        entities=entities,
        action="phone_call"
    )


def generate_otp() -> list:
    return [random.randint(0, 9) for _ in range(4)]


def otp_to_words(otp: list) -> str:
    words = ["zero","one","two","three","four","five","six","seven","eight","nine"]
    return ", ".join(words[d] for d in otp)


# ── Main Dialogue Manager ───────────────────────────────────────────────────

class DialogueManager:

    def __init__(self):
        self.classifier = IntentClassifier()
        self.state = DialogueState()
        self._otp_active = None      # current OTP waiting for match
        self._otp_intent_after = None

    def _is_session_valid(self) -> bool:
        if not self.state.session_valid:
            return False
        elapsed = time.time() - self.state.session_start
        return elapsed < self.state.session_duration

    def _start_session(self):
        self.state.session_valid = True
        self.state.session_start = time.time()

    def _add_to_history(self, role: str, text: str, intent: str):
        self.state.history.append(ConversationTurn(
            role=role, text=text, intent=intent
        ))
        # keep last 10 turns only
        if len(self.state.history) > 10:
            self.state.history = self.state.history[-10:]

    def _resolve_context(self, text: str) -> str:
        """Resolve pronouns using last 2 turns."""
        text_lower = text.lower()
        if not self.state.history:
            return text

        last_turns = self.state.history[-2:]
        last_destinations = []
        last_contacts = []

        for turn in last_turns:
            if turn.intent == "navigation" and "destination" in str(turn.text):
                # extract last mentioned place
                import re
                match = re.search(
                    r"(?:to|at|near)\s+([A-Z][a-zA-Z\s]+)",
                    turn.text
                )
                if match:
                    last_destinations.append(match.group(1).strip())
            if turn.intent == "communication":
                import re
                match = re.search(r"call\s+(\w+)", turn.text.lower())
                if match:
                    last_contacts.append(match.group(1))

        # replace pronouns
        if any(w in text_lower for w in ["there", "that place", "same place"]):
            if last_destinations:
                text = re.sub(
                    r"\b(there|that place|same place)\b",
                    last_destinations[-1],
                    text,
                    flags=re.IGNORECASE
                )
        if any(w in text_lower for w in ["him", "her", "them"]):
            if last_contacts:
                text = re.sub(
                    r"\b(him|her|them)\b",
                    last_contacts[-1],
                    text,
                    flags=re.IGNORECASE
                )
        return text

    def _check_missing_slots(self, intent: str, entities: dict) -> list:
        required = REQUIRED_SLOTS.get(intent, [])
        missing = []
        for slot in required:
            if not entities.get(slot):
                missing.append(slot)
        return missing

    def process(self, user_input: str) -> dict:
        """Main entry point — processes every user message."""

        user_input = user_input.strip()
        if not user_input:
            return build_response(
                message="I didn't catch that. Could you repeat?",
                state="IDLE",
                intent="unknown",
                routing="None"
            )

        # ── Handle SLOT_FILL state ──────────────────────────────────────────
        if self.state.fsm_state == "SLOT_FILL":
            return self._handle_slot_fill(user_input)

        # ── Handle CONFIRM_PENDING state ────────────────────────────────────
        if self.state.fsm_state == "CONFIRM_PENDING":
            return self._handle_confirmation(user_input)

        # ── Handle OTP state ────────────────────────────────────────────────
        if self.state.fsm_state == "OTP_PENDING":
            return self._handle_otp(user_input)

        # ── Handle VERIFY state (simulated) ─────────────────────────────────
        if self.state.fsm_state == "VERIFY":
            return self._handle_verify(user_input)

        # ── Step 1: Resolve context ─────────────────────────────────────────
        resolved_text = self._resolve_context(user_input)

        # ── Step 2: Classify intent ─────────────────────────────────────────
        result = self.classifier.classify(resolved_text)
        self._add_to_history("user", user_input, result.intent)

        # ── Step 3: Interrupt check — always first ──────────────────────────
        if result.intent == "stop":
            self.state.fsm_state = "IDLE"
            self.state.queue.clear()
            self.state.current_intent = None
            return build_response(
                message="Stopped. Queue cleared. I'm listening.",
                state="IDLE",
                intent="stop",
                routing="Interrupt handler — immediate halt — queue flushed"
            )

        # ── Step 4: Check session ───────────────────────────────────────────
        if not self._is_session_valid():
            # Simulate identity verification for demo
            self.state.fsm_state = "VERIFY"
            self.state.pending_entities = result.entities
            self.state.current_intent = result.intent
            return build_response(
                message="Please verify your identity. Say your name or 'verify me' to continue. (In production: voice biometric check via Layer 3)",
                state="VERIFY",
                intent=result.intent,
                routing="Layer 3 — Voice biometric verification required"
            )

        # ── Step 5: Check missing slots ─────────────────────────────────────
        missing = self._check_missing_slots(result.intent, result.entities)
        if missing:
            self.state.fsm_state = "SLOT_FILL"
            self.state.current_intent = result.intent
            self.state.pending_entities = result.entities
            self.state.missing_slots = missing
            self.state.slot_attempt = 0
            first_missing = missing[0]
            question = SLOT_QUESTIONS.get(first_missing, f"What is the {first_missing}?")
            return build_response(
                message=question,
                state="SLOT_FILL",
                intent=result.intent,
                routing=f"Slot filling — missing: {missing}",
                entities=result.entities
            )

        # ── Step 6: Route by intent ─────────────────────────────────────────
        return self._route(result)

    def _route(self, result: IntentResult) -> dict:
        """Route confirmed intent to correct handler."""

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
            # Payment requires confirm pending
            self.state.fsm_state = "CONFIRM_PENDING"
            self.state.confirm_action = "payment"
            self.state.confirm_details = {
                "item": result.raw_text,
                "amount": result.entities.get("amount", "unknown amount")
            }
            return build_response(
                message=f"Please confirm: '{result.raw_text}'. Say YES to proceed or NO to cancel.",
                state="CONFIRM_PENDING",
                intent="payment",
                routing="Confirm Pending — explicit driver confirmation required before payment"
            )

        else:
            return handle_general_question(result.raw_text, self.state.history)

    def _handle_slot_fill(self, user_input: str) -> dict:
        """Fill missing slot with user's answer."""
        self.state.slot_attempt += 1

        if self.state.slot_attempt > 3:
            # Too many attempts
            self.state.fsm_state = "IDLE"
            self.state.current_intent = None
            return build_response(
                message="I'm sorry, I couldn't understand. Please try again.",
                state="IDLE",
                intent=self.state.current_intent or "unknown",
                routing="Slot fill failed after 3 attempts — reset"
            )

        # Fill the first missing slot with user's answer
        missing_slot = self.state.missing_slots[0]
        self.state.pending_entities[missing_slot] = user_input
        self.state.missing_slots.pop(0)

        # Check if more slots needed
        if self.state.missing_slots:
            next_slot = self.state.missing_slots[0]
            question = SLOT_QUESTIONS.get(next_slot, f"What is the {next_slot}?")
            return build_response(
                message=question,
                state="SLOT_FILL",
                intent=self.state.current_intent,
                routing=f"Slot filling — still missing: {self.state.missing_slots}",
                entities=self.state.pending_entities
            )

        # All slots filled — now route
        self.state.fsm_state = "IDLE"
        intent = self.state.current_intent
        entities = self.state.pending_entities.copy()

        # Create a filled result and route
        from intent_classifier import IntentResult
        filled_result = IntentResult(
            intent=intent,
            confidence=1.0,
            entities=entities,
            raw_text=user_input
        )
        return self._route(filled_result)

    def _handle_confirmation(self, user_input: str) -> dict:
        """Handle yes/no confirmation for payment."""
        yes_words = ["yes", "yeah", "yep", "confirm", "proceed", "ok", "okay", "sure", "do it"]
        no_words = ["no", "nope", "cancel", "stop", "don't", "abort"]

        user_lower = user_input.lower().strip()

        if any(word in user_lower for word in yes_words):
            # Confirmed — trigger OTP
            self.state.fsm_state = "OTP_PENDING"
            otp = generate_otp()
            self._otp_active = otp
            otp_words = otp_to_words(otp)
            return build_response(
                message=f"Voice OTP: Please repeat — {otp_words}.",
                state="OTP_PENDING",
                intent="payment",
                routing="Voice OTP — unique per transaction — replay attack protection",
                otp=otp
            )

        elif any(word in user_lower for word in no_words):
            self.state.fsm_state = "IDLE"
            self.state.confirm_action = None
            return build_response(
                message="Payment cancelled. Returning to ready.",
                state="IDLE",
                intent="payment",
                routing="Payment cancelled by driver"
            )

        else:
            return build_response(
                message="Please say YES to confirm or NO to cancel.",
                state="CONFIRM_PENDING",
                intent="payment",
                routing="Waiting for explicit YES or NO"
            )

    def _handle_otp(self, user_input: str) -> dict:
        """Check if driver repeated OTP correctly."""
        number_words = {
            "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
            "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "0": 0, "1": 1, "2": 2, "3": 3, "4": 4,
            "5": 5, "6": 6, "7": 7, "8": 8, "9": 9
        }

        # Parse spoken digits
        words = user_input.lower().strip().split()
        spoken_digits = []
        for word in words:
            clean = word.strip(".,!?")
            if clean in number_words:
                spoken_digits.append(number_words[clean])

        if spoken_digits == self._otp_active:
            self.state.fsm_state = "IDLE"
            self._otp_active = None
            return build_response(
                message="OTP verified. Payment authorized. Transaction sent to payment gateway — digitally signed.",
                state="IDLE",
                intent="payment",
                routing="Payment tool Layer 8 — digitally signed transaction",
                action="payment_authorized"
            )
        else:
            self.state.fsm_state = "IDLE"
            self._otp_active = None
            return build_response(
                message="OTP did not match. Payment denied. Please try again.",
                state="IDLE",
                intent="payment",
                routing="OTP failed — payment denied — security enforced",
                action="payment_denied"
            )

    def _handle_verify(self, user_input: str) -> dict:
        """Simulate Layer 3 verification for demo."""
        # In production this calls SpeechBrain voice match
        # For demo — any input verifies successfully
        self._start_session()
        self.state.fsm_state = "IDLE"

        # Replay the original intent after verification
        original_intent = self.state.current_intent
        original_entities = self.state.pending_entities

        from intent_classifier import IntentResult
        filled_result = IntentResult(
            intent=original_intent,
            confidence=1.0,
            entities=original_entities,
            raw_text=user_input
        )

        verify_response = build_response(
            message="Identity verified. Session started — valid for 15 minutes.",
            state="PROCESSING",
            intent=original_intent,
            routing="Layer 3 verification passed — JWT session token created"
        )

        # Now route the original command
        route_response = self._route(filled_result)

        # Merge — show verify message + route result
        route_response["verify_message"] = verify_response["nova_says"]
        route_response["session_started"] = True
        return route_response


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dm = DialogueManager()

    print("\n" + "="*55)
    print("  NOVA Layer 7 — Dialogue Manager Test")
    print("="*55)

    # Simulate a full conversation
    test_conversation = [
        "verify me",                  # verify identity first
        "turn on the AC",             # vehicle control
        "navigate to the airport",    # navigation — destination known
        "navigate to",                # navigation — destination MISSING → slot fill
        "Hyderabad airport",          # fill destination slot
        "play some relaxing music",   # media
        "order a coffee",             # payment → confirm pending
        "yes",                        # confirm → OTP
        "seven two nine four",        # OTP attempt (may not match — random)
        "stop",                       # interrupt
        "what is the capital of France",  # general question
    ]

    for user_input in test_conversation:
        print(f"\n  You  : {user_input}")
        response = dm.process(user_input)
        print(f"  Nova : {response['nova_says']}")
        print(f"  State: {response['fsm_state']}")
        print(f"  Route: {response['routing']}")
        print("  " + "-"*50)