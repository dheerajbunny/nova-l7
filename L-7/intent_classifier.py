"""
NOVA Layer 7 - Intent Classifier
Classifies user commands into categories.
Runs on device, no internet, no AI model needed.

UPDATES:
- Food/drink ordering keywords added
- Merchant name extraction (Starbucks, Subway etc)
- Item name extraction (frappuccino, latte etc)
- Improved payment patterns
- Dollar + Rupee amount extraction
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
        r"\bplay\b", r"\bpause music\b", r"\bstop music\b",
        r"\bnext (song|track|music)\b", r"\bprevious (song|track)\b",
        r"\bshuffle\b", r"\bskip\b",
        r"\bspotify\b", r"\bmusic\b", r"\bsong\b",
        r"\bradio\b", r"\bpodcast\b", r"\bplaylist\b",
        r"\bvolume up\b", r"\bvolume down\b"
    ],

    "payment": [
        # Action keywords
        r"\bpay\b", r"\border\b", r"\bbook\b", r"\bbuy\b",
        r"\bpurchase\b", r"\btransaction\b", r"\bcheckout\b",
        r"\bcharge\b", r"\bsend money\b", r"\btransfer\b",
        r"\bi want\b", r"\bget me\b", r"\bi('d| would) like\b",

        # Food and drink
        r"\bcoffee\b", r"\blatte\b", r"\bcappuccino\b",
        r"\bespresso\b", r"\bfrappuccino\b", r"\bcold brew\b",
        r"\btea\b", r"\bjuice\b", r"\bsmoothie\b",
        r"\bsandwich\b", r"\bburger\b", r"\bpizza\b",
        r"\bsub\b", r"\bwrap\b", r"\bsalad\b",
        r"\bbreakfast\b", r"\blunch\b", r"\bdinner\b",
        r"\bsnack\b", r"\bfood\b", r"\bmeal\b",
        r"\bdrink\b", r"\bbeverage\b",

        # Merchants
        r"\bstarbucks\b", r"\bsubway\b", r"\bmcdonald(s)?\b",
        r"\bpizza hut\b", r"\bdomino(s)?\b", r"\bkfc\b",
        r"\bblu(e)? bottle\b", r"\bdunkin\b", r"\btim hortons\b",
        r"\bchipotle\b", r"\bpanda express\b",

        # Fuel and services
        r"\bfuel\b", r"\bgas\b", r"\bpetrol\b",
        r"\bparking\b.*\bpay\b", r"\bpay.*\bparking\b",
    ],

    "communication": [
        r"\bcall\b", r"\bphone\b", r"\bdial\b", r"\bring\b",
        r"\btext\b", r"\bsend.*message\b", r"\bwhatsapp\b",
        r"\bsms\b", r"\bmessage\b"
    ],

    "general_question": [
        r"\bwhat\b", r"\bhow\b", r"\bwhy\b", r"\bwhen\b",
        r"\bwhere\b", r"\bwho\b", r"\btell me\b", r"\bexplain\b",
        r"\bwhat is\b", r"\bwhat are\b", r"\bcan you\b",
        r"\bweather\b", r"\bnews\b", r"\btime\b", r"\bdate\b"
    ],
}


# ── Known merchants and items for extraction ────────────────────────────────

KNOWN_MERCHANTS = [
    "starbucks", "subway", "mcdonalds", "mcdonald's",
    "pizza hut", "dominos", "domino's", "kfc",
    "blue bottle", "dunkin", "tim hortons",
    "chipotle", "panda express", "shell", "bp"
]

KNOWN_ITEMS = [
    "frappuccino", "caramel frappuccino", "mocha frappuccino",
    "latte", "caramel latte", "vanilla latte",
    "cappuccino", "espresso", "cold brew", "americano",
    "flat white", "macchiato", "chai latte",
    "veggie delight", "chicken teriyaki", "footlong",
    "big mac", "whopper", "double double",
    "sandwich", "burger", "pizza", "sub", "wrap",
    "coffee", "tea", "juice", "smoothie"
]


# ── Entity extractors ───────────────────────────────────────────────────────

def extract_entities(text: str, intent: str) -> dict:
    entities  = {}
    text_lower = text.lower()

    if intent == "navigation":
        dest_match = re.search(
            r"(?:go to|navigate to|take me to|drive to|head to|route to|directions? to)\s+(.+)",
            text_lower
        )
        if dest_match:
            entities["destination"] = dest_match.group(1).strip()
        else:
            entities["destination"] = None

    if intent == "vehicle_control":
        controls = ["ac", "window", "heater", "fan",
                    "lights", "seat", "wiper", "horn"]
        for control in controls:
            if control in text_lower:
                entities["component"] = control
                break
        if any(w in text_lower for w in
               ["on", "open", "increase", "higher", "up"]):
            entities["action"] = "on"
        elif any(w in text_lower for w in
                 ["off", "close", "decrease", "lower", "down"]):
            entities["action"] = "off"

    if intent == "media":
        play_match = re.search(r"play\s+(.+)", text_lower)
        if play_match:
            entities["query"] = play_match.group(1).strip()

    if intent == "payment":
        # ── Extract size ─────────────────────────────────────────────────
        sizes = ["small", "medium", "large", "grande", "venti", "tall", "regular", "extra large"]
        for size in sizes:
            if size in text_lower:
                entities["size"] = size
                break
                
        # ── Extract quantity ─────────────────────────────────────────────
        quantity_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "a": 1, "an": 1}
        qty_match = re.search(r"\b(one|two|three|four|five|a|an|\d+)\b", text_lower)
        if qty_match:
            word = qty_match.group(1)
            entities["quantity"] = quantity_map.get(word, int(word) if word.isdigit() else 1)
        else:
            entities["quantity"] = 1

        # ── Extract merchant name ────────────────────────────────────────
        for merchant in KNOWN_MERCHANTS:
            if merchant in text_lower:
                entities["merchant"] = merchant
                break

        # ── Extract item name ────────────────────────────────────────────
        # Try longest match first
        for item in sorted(KNOWN_ITEMS, key=len, reverse=True):
            if item in text_lower:
                entities["item"] = item
                break

        # If no known item — try to extract after "order/get/buy/want"
        if not entities.get("item"):
            item_match = re.search(
                r"(?:order|get me|buy|i want|i'd like|give me)\s+(?:a\s+|an\s+)?(.+?)(?:\s+from|\s+at|\s+near|$)",
                text_lower
            )
            if item_match:
                entities["item"] = item_match.group(1).strip()

        # ── Extract amount ───────────────────────────────────────────────
        # Dollar amounts
        dollar_match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", text_lower)
        if dollar_match:
            entities["amount"] = dollar_match.group(1)

        # Rupee amounts
        if not entities.get("amount"):
            rupee_match = re.search(
                r"(?:rs\.?|rupees?|inr)?\s*(\d+)", text_lower
            )
            if rupee_match:
                entities["amount"] = rupee_match.group(1)

        # ── Build query for merchant search ─────────────────────────────
        # Combine merchant + item as search query
        if entities.get("merchant") and entities.get("item"):
            entities["query"] = f"{entities['item']} from {entities['merchant']}"
        elif entities.get("merchant"):
            entities["query"] = entities["merchant"]
        elif entities.get("item"):
            entities["query"] = entities["item"]

    if intent == "communication":
        call_match = re.search(
            r"(?:call|phone|text|message|dial|ring)\s+(.+)", text_lower
        )
        if call_match:
            entities["contact"] = call_match.group(1).strip()

    return entities


# ── Main classifier ─────────────────────────────────────────────────────────

class IntentClassifier:

    def classify(self, text: str) -> IntentResult:
        text_clean = text.strip().lower()
        scores: dict[str, float] = {}

        for intent, patterns in INTENT_RULES.items():
            match_count = sum(
                1 for pattern in patterns
                if re.search(pattern, text_clean)
            )
            if match_count > 0:
                scores[intent] = min(float(match_count) / 3.0, 1.0)

        if not scores:
            return IntentResult(
                intent="general_question",
                confidence=0.5,
                entities={},
                raw_text=text
            )

        best_intent = max(scores, key=lambda k: scores[k])
        confidence  = scores[best_intent]

        # stop always wins
        if "stop" in scores:
            best_intent = "stop"
            confidence  = 1.0

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
        # Original tests
        "turn on the AC",
        "navigate to the airport",
        "play some relaxing music",
        "call mom",
        "stop",
        "what is the weather today",

        # New food ordering tests
        "order a frappuccino from Starbucks",
        "I want a caramel latte",
        "get me a coffee",
        "order from Subway",
        "I'd like an espresso",
        "buy me a cold brew from Blue Bottle",
        "order food",
        "I want a veggie delight from Subway",
    ]

    print("\n" + "="*60)
    print("  NOVA Layer 7 — Intent Classifier Test")
    print("="*60)

    for cmd in test_commands:
        result = classifier.classify(cmd)
        print(f"\n  Input    : {cmd}")
        print(f"  Intent   : {result.intent}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Entities : {result.entities}")
        print("  " + "-"*55)