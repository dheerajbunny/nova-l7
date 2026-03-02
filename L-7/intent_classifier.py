"""
NOVA Layer 7 - Intent Classifier
Classifies user commands into categories.
Runs on device, no internet, no AI model needed.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class IntentResult:
    intent: str          # what type of command
    confidence: float    # how sure we are (0 to 1)
    entities: dict       # extracted info from command
    raw_text: str        # original command


# ── Keyword rules for each intent ──────────────────────────────────────────

INTENT_RULES = {

    "stop": [
        r"\bstop\b", r"\bcancel\b", r"\bquit\b",
        r"\bshut up\b", r"\bnevermind\b", r"\bnever mind\b"
    ],

    "vehicle_control": [
        r"\bturn (on|off)\b", r"\bswitch (on|off)\b",
        r"\bac\b", r"\bair condition\b", r"\bair con\b",
        r"\bwindow(s)?\b", r"\bwiper(s)?\b", r"\bheater\b",
        r"\bfan\b", r"\blights?\b", r"\bheadlight(s)?\b",
        r"\bseat(s)?\b", r"\bvolume\b", r"\bmute\b",
        r"\bhorn\b", r"\bparking\b", r"\bbrake(s)?\b",
        r"\bopen\b", r"\bclose\b", r"\badjust\b",
        r"\bincrease\b", r"\bdecrease\b", r"\bhigher\b", r"\blower\b"
    ],

    "navigation": [
        r"\bnavigate\b", r"\bdirections?\b", r"\bgo to\b",
        r"\btake me\b", r"\bdrive to\b", r"\bhead to\b",
        r"\broute to\b", r"\bhow (far|long)\b", r"\bdistance\b",
        r"\beta\b", r"\bnearest\b", r"\bclosest\b",
        r"\bwhere is\b", r"\bfind\b.*\bnear\b",
        r"\bmap\b", r"\btraffic\b", r"\bavoide?\b"
    ],

    "media": [
        r"\bplay\b", r"\bpause\b", r"\bstop music\b",
        r"\bnext (song|track|music)\b", r"\bprevious (song|track)\b",
        r"\bshuffle\b", r"\brepeat\b", r"\bskip\b",
        r"\bspotify\b", r"\bmusic\b", r"\bsong\b",
        r"\bradio\b", r"\bpodcast\b", r"\bplaylist\b",
        r"\bvolume up\b", r"\bvolume down\b"
    ],

    "payment": [
        r"\bpay\b", r"\border\b", r"\bbook\b", r"\bbuy\b",
        r"\bpurchase\b", r"\btransaction\b", r"\bcheckout\b",
        r"\bcharge\b", r"\bfuel\b.*\bpay\b", r"\bpay.*\bfuel\b",
        r"\bsend money\b", r"\btransfer\b"
    ],

    "communication": [
        r"\bcall\b", r"\bphone\b", r"\bdial\b", r"\bring\b",
        r"\btext\b", r"\bsend.*message\b", r"\bwhatsapp\b",
        r"\bemail\b", r"\bsms\b", r"\bmessage\b"
    ],

    "general_question": [
        r"\bwhat\b", r"\bhow\b", r"\bwhy\b", r"\bwhen\b",
        r"\bwhere\b", r"\bwho\b", r"\btell me\b", r"\bexplain\b",
        r"\bwhat is\b", r"\bwhat are\b", r"\bcan you\b",
        r"\bweather\b", r"\bnews\b", r"\btime\b", r"\bdate\b"
    ],
}


# ── Entity extractors ───────────────────────────────────────────────────────

def extract_entities(text: str, intent: str) -> dict:
    entities = {}
    text_lower = text.lower()

    if intent == "navigation":
        # Extract destination — everything after "to" or "navigate"
        dest_match = re.search(
            r"(?:go to|navigate to|take me to|drive to|head to|route to|directions? to)\s+(.+)",
            text_lower
        )
        if dest_match:
            entities["destination"] = dest_match.group(1).strip()
        else:
            entities["destination"] = None  # missing — slot fill needed

    if intent == "vehicle_control":
        # Extract what to control
        controls = ["ac", "window", "heater", "fan", "lights", "seat", "wiper"]
        for control in controls:
            if control in text_lower:
                entities["component"] = control
                break
        # Extract action
        if any(w in text_lower for w in ["on", "open", "increase", "higher", "up"]):
            entities["action"] = "on"
        elif any(w in text_lower for w in ["off", "close", "decrease", "lower", "down"]):
            entities["action"] = "off"

    if intent == "media":
        # Extract song/artist if mentioned
        play_match = re.search(r"play\s+(.+)", text_lower)
        if play_match:
            entities["query"] = play_match.group(1).strip()

    if intent == "payment":
        # Extract amount if mentioned
        amount_match = re.search(r"(?:rs\.?|rupees?|inr)?\s*(\d+)", text_lower)
        if amount_match:
            entities["amount"] = amount_match.group(1)

    if intent == "communication":
        # Extract contact name
        call_match = re.search(r"(?:call|phone|text|message)\s+(.+)", text_lower)
        if call_match:
            entities["contact"] = call_match.group(1).strip()

    return entities


# ── Main classifier ─────────────────────────────────────────────────────────

class IntentClassifier:

    def classify(self, text: str) -> IntentResult:
        text_clean = text.strip().lower()
        scores: dict[str, float] = {} 

        for intent, patterns in INTENT_RULES.items():
            match_count = sum(1 for pattern in patterns if re.search(pattern, text_clean))
            if match_count > 0:
                # normalize score — more matches = more confident
                scores[intent] = min(float(match_count) / 3.0, 1.0)

        if not scores:
            # nothing matched — treat as general question
            return IntentResult(
                intent="general_question",
                confidence=0.5,
                entities={},
                raw_text=text
            )

        # pick highest scoring intent
        best_intent = max(scores, key=lambda k: scores[k])
        confidence = scores[best_intent]

        # stop always wins regardless of score
        if "stop" in scores:
            best_intent = "stop"
            confidence = 1.0

        entities = extract_entities(text, best_intent)

        return IntentResult(
            intent=best_intent,
            confidence=round(confidence, 2),
            entities=entities,
            raw_text=text
        )


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    classifier = IntentClassifier()

    test_commands = [
        "turn on the AC",
        "navigate to the airport",
        "play some relaxing music",
        "order a coffee",
        "what is the weather today",
        "call mom",
        "stop",
        "take me to Hyderabad",
        "increase the volume",
        "pay for fuel",
    ]

    print("\n" + "="*55)
    print("  NOVA Layer 7 — Intent Classifier Test")
    print("="*55)

    for cmd in test_commands:
        result = classifier.classify(cmd)
        print(f"\n  Input    : {cmd}")
        print(f"  Intent   : {result.intent}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Entities : {result.entities}")
        print("  " + "-"*50)