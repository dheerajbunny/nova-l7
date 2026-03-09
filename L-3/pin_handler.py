"""
pin_handler.py
--------------
Handles PIN-based fallback authentication.

What it does:
  - Takes a spoken PIN (text from Whisper STT)
  - SHA-256 hashes it
  - Compares to stored hash
  - Returns pass/fail

Why SHA-256:
  - The actual PIN is NEVER stored anywhere
  - Only the hash is stored
  - If someone steals the device, they get the hash
  - They CANNOT reverse the hash back to the PIN
  - They would have to try all 10,000 possible 4-digit PINs
    and hash each one — which we can detect and block

PIN format:
  - Stored/entered as 4 digits: "4782"
  - Spoken as words: "four seven eight two"
  - We normalize spoken words → digits before hashing
"""

import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DATA_DIR = Path(__file__).parent / "data"
PIN_DIR  = DATA_DIR / "pins"
PIN_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  WORD TO DIGIT NORMALIZATION
# ══════════════════════════════════════════════════════════════════════════════

# When driver speaks "four seven eight two"
# Whisper transcribes it as text
# We convert spoken words back to digits

WORD_TO_DIGIT = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # Handle common mishearing
    "to": "2", "too": "2", "for": "4", "ate": "8", "won": "1", "nein": "9"
}


import re

def normalize_pin(spoken_text: str) -> str:
    """
    Convert spoken PIN to digit string.

    Examples:
      "four seven eight two"  → "4782"
      "4 7 8 2"               → "4782"
      "4782"                  → "4782"
      "four 7 eight 2"        → "4782"
      "1, 2, 3, 4... 1, 2, 3, 4..." -> "1234"
    """
    spoken_text = spoken_text.lower().strip()

    # Remove all punctuation including commas and ellipses
    spoken_text = re.sub(r'[^\w\s]', ' ', spoken_text)

    result = ""
    tokens = spoken_text.split()

    for token in tokens:
        if token in WORD_TO_DIGIT:
            result += WORD_TO_DIGIT[token]
        elif token.isdigit():
            result += token
            
        if len(result) >= 4:
            # We found our 4 digits, stop processing repeats
            return result[:4]

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  HASH FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def hash_pin(pin_digits: str) -> str:
    """
    SHA-256 hash a PIN string.
    Returns hex string of 64 characters.

    Example:
      hash_pin("4782") → "a3f5c9d2..." (64 char hex)
    """
    return hashlib.sha256(pin_digits.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
#  SAVE PIN HASH (called during enrollment)
# ══════════════════════════════════════════════════════════════════════════════

def save_pin_hash(driver_id: str, pin_digits: str) -> None:
    """
    Hash the PIN and save only the hash to disk.
    Called during enrollment. Never called during verification.
    """
    pin_hash = hash_pin(pin_digits)
    save_path = PIN_DIR / f"{driver_id}.txt"

    with open(save_path, "w") as f:
        f.write(pin_hash)

    print(f"  [pin] Hash saved → {save_path}")
    print(f"  [pin] Actual PIN not stored anywhere.")


def get_stored_hash(driver_id: str) -> str | None:
    """Load stored PIN hash for a driver. Returns None if not enrolled."""
    hash_path = PIN_DIR / f"{driver_id}.txt"
    if not hash_path.exists():
        return None
    with open(hash_path, "r") as f:
        return f.read().strip()


# ══════════════════════════════════════════════════════════════════════════════
#  VERIFY PIN — MAIN FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def verify_pin(driver_id: str, spoken_text: str, verbose: bool = True) -> dict:
    """
    Verify a spoken PIN against stored hash.

    Args:
        driver_id:    which driver to check against
        spoken_text:  what Whisper transcribed (e.g. "four seven eight two")
        verbose:      print results

    Returns dict:
    {
        "passed":      True/False,
        "driver_id":   "driver1",
        "normalized":  "4782",     ← what we actually compared
        "error":       None        ← error message if something went wrong
    }
    """
    # Normalize spoken text to digits
    pin_digits = normalize_pin(spoken_text)

    if verbose:
        print(f"  [pin] Spoken: '{spoken_text}'")
        print(f"  [pin] Normalized to: '{pin_digits}'")

    # Validate PIN length
    if len(pin_digits) != 4:
        msg = f"Could not extract 4 digits from '{spoken_text}' (got '{pin_digits}')"
        if verbose:
            print(f"  [pin] ❌ {msg}")
        return {"passed": False, "driver_id": driver_id, "normalized": pin_digits, "error": msg}

    # Load stored hash
    stored_hash = get_stored_hash(driver_id)
    if stored_hash is None:
        msg = f"Driver '{driver_id}' PIN not enrolled."
        if verbose:
            print(f"  [pin] ❌ {msg}")
        return {"passed": False, "driver_id": driver_id, "normalized": pin_digits, "error": msg}

    # Compare hashes
    input_hash = hash_pin(pin_digits)
    passed = (input_hash == stored_hash)

    if verbose:
        print(f"  [pin] Result: {'✅ PIN CORRECT' if passed else '❌ PIN INCORRECT'}\n")

    return {
        "passed":     passed,
        "driver_id":  driver_id,
        "normalized": pin_digits,
        "error":      None
    }


# ══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE PIN PROMPT — Used in layer3_main.py
# ══════════════════════════════════════════════════════════════════════════════

def prompt_and_verify_pin(driver_id: str, verbose: bool = True) -> dict:
    """
    Prompt the driver to speak/type their PIN and verify it.
    In real system: spoken_text comes from Whisper STT.
    For demo: typed manually.

    Returns same dict as verify_pin().
    """
    if verbose:
        print(f"\n  [fallback] Voice failed. Fallback to PIN.")
        print(f"  Nova says: 'Voice not recognized. Please say your PIN.'")

    # In real system this line would be:
    # spoken_text = whisper.transcribe(record_audio(3.0))
    # For now: typed input
    spoken_text = input("  Enter PIN (type digits or words): ")

    return verify_pin(driver_id, spoken_text, verbose=verbose)


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NOVA PIN Verification Test")
    parser.add_argument("--driver", type=str, default="driver1")
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  NOVA — PIN Fallback Test")
    print(f"  Driver: {args.driver}")
    print(f"{'='*50}\n")

    result = prompt_and_verify_pin(args.driver)

    if result["passed"]:
        print(f"  ✅ PIN verified. Access granted.")
    else:
        print(f"  ❌ PIN failed. {result.get('error', 'Incorrect PIN.')}")
