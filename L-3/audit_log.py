"""
audit_log.py
------------
Tamper-proof audit log using chained hashing (blockchain principle).

What it does:
  - Every auth event is written to a log file
  - Each entry includes a hash of the PREVIOUS entry
  - This creates a chain — like links in a chain
  - If anyone deletes or changes any entry, the chain breaks
  - The break is immediately detectable

Why this matters:
  - Driver says "I never authorized that payment"
  - We can show the log: "Voice verified at 10:05, score 0.91,
    payment Rs 180 confirmed at 10:06, OTP matched"
  - The log is cryptographically tamper-proof
  - This is legally defensible evidence

Events logged:
  - ENROLL        → driver registered
  - VOICE_PASS    → voice verification succeeded
  - VOICE_FAIL    → voice verification failed
  - PIN_PASS      → PIN fallback succeeded
  - PIN_FAIL      → PIN fallback failed
  - FACE_PASS     → face ID succeeded
  - FACE_FAIL     → face ID failed
  - SESSION_START → session token created
  - SESSION_END   → session expired or revoked
  - LOCKOUT       → all auth levels failed
  - OTP_PASS      → Voice OTP matched
  - OTP_FAIL      → Voice OTP failed
  - PAYMENT_AUTH  → payment authorized
  - PAYMENT_DENY  → payment denied
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Optional

DATA_DIR  = Path(__file__).parent / "data"
LOG_FILE  = DATA_DIR / "audit_log.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  CORE CHAIN FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _hash_entry(entry: dict) -> str:
    """
    SHA-256 hash of an entry.
    The entry is serialized to JSON (sorted keys) before hashing.
    Sorted keys ensure same dict always produces same hash.
    """
    entry_str = json.dumps(entry, sort_keys=True)
    return hashlib.sha256(entry_str.encode()).hexdigest()


def _load_log() -> list:
    """Load existing log entries from file. Returns empty list if file doesn't exist."""
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_log(entries: list) -> None:
    """Save all log entries to file."""
    with open(LOG_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def _get_last_hash() -> str:
    """
    Get the hash of the last entry in the log.
    If log is empty, use a genesis hash (like blockchain's genesis block).
    """
    entries = _load_log()
    if not entries:
        return hashlib.sha256(b"NOVA_GENESIS_BLOCK").hexdigest()
    return entries[-1]["hash"]


# ══════════════════════════════════════════════════════════════════════════════
#  WRITE LOG ENTRY
# ══════════════════════════════════════════════════════════════════════════════

def log_event(
    event_type:  str,
    driver_id:   str,
    passed:      bool,
    details:     Optional[dict] = None
) -> str:
    """
    Write an auth event to the tamper-proof log.

    Args:
        event_type: one of VOICE_PASS, VOICE_FAIL, PIN_PASS, etc.
        driver_id:  which driver this event is for
        passed:     True if auth succeeded, False if failed
        details:    optional extra info (score, amount, etc.)

    Returns:
        hash of this entry (for chaining to next entry)

    Example:
        log_event("VOICE_PASS", "driver1", True, {"score": 0.91})
        log_event("PAYMENT_AUTH", "driver1", True, {"amount": 180, "merchant": "Starbucks"})
    """
    import datetime

    prev_hash = _get_last_hash()

    entry_data = {
        "timestamp":  time.time(),
        "datetime":   datetime.datetime.now().isoformat(),
        "event_type": event_type,
        "driver_id":  driver_id,
        "passed":     passed,
        "details":    details or {},
        "prev_hash":  prev_hash
    }

    # Hash this entry
    current_hash = _hash_entry(entry_data)

    # Full entry includes its own hash
    full_entry = {**entry_data, "hash": current_hash}

    # Append to log
    entries = _load_log()
    entries.append(full_entry)
    _save_log(entries)

    return current_hash


# ══════════════════════════════════════════════════════════════════════════════
#  VERIFY LOG INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════

def verify_log_integrity() -> dict:
    """
    Verify the entire log chain is intact.
    Check each entry's hash matches what's stored,
    and that each entry's prev_hash matches the previous entry's hash.

    Returns:
    {
        "intact":        True/False,
        "total_entries": 42,
        "broken_at":     None  ← entry index where chain broke (if broken)
        "message":       "Log integrity verified" or "Tampering detected at entry 5"
    }
    """
    entries = _load_log()

    if not entries:
        return {"intact": True, "total_entries": 0, "broken_at": None,
                "message": "Log is empty (no entries yet)"}

    genesis_hash = hashlib.sha256(b"NOVA_GENESIS_BLOCK").hexdigest()

    for i, entry in enumerate(entries):
        # Rebuild entry without hash field
        entry_data = {k: v for k, v in entry.items() if k != "hash"}

        # Recompute hash
        expected_hash = _hash_entry(entry_data)

        # Check stored hash matches
        if entry["hash"] != expected_hash:
            return {
                "intact": False,
                "total_entries": len(entries),
                "broken_at": i,
                "message": f"❌ Tampering detected at entry {i} — hash mismatch"
            }

        # Check prev_hash chain
        if i == 0:
            expected_prev = genesis_hash
        else:
            expected_prev = entries[i-1]["hash"]

        if entry["prev_hash"] != expected_prev:
            return {
                "intact": False,
                "total_entries": len(entries),
                "broken_at": i,
                "message": f"❌ Tampering detected at entry {i} — chain broken"
            }

    return {
        "intact": True,
        "total_entries": len(entries),
        "broken_at": None,
        "message": f"✅ Log integrity verified — {len(entries)} entries, all intact"
    }


# ══════════════════════════════════════════════════════════════════════════════
#  READ LOG — For displaying to manager
# ══════════════════════════════════════════════════════════════════════════════

def print_log(driver_id: Optional[str] = None, last_n: int = 20) -> None:
    """
    Print the audit log in a readable format.
    Filter by driver_id if provided.
    Shows last_n entries.
    """
    entries = _load_log()

    if driver_id:
        entries = [e for e in entries if e["driver_id"] == driver_id]

    entries = entries[-last_n:]

    print(f"\n{'='*65}")
    print(f"  NOVA AUDIT LOG{f' — {driver_id}' if driver_id else ''}")
    print(f"{'='*65}")

    if not entries:
        print("  No log entries found.")
        return

    for e in entries:
        status = "✅" if e["passed"] else "❌"
        details_str = ""
        if e["details"]:
            details_str = " | " + ", ".join(f"{k}={v}" for k, v in e["details"].items())

        print(f"  {status} {e['datetime'][:19]} | {e['event_type']:<15} | "
              f"{e['driver_id']:<10}{details_str}")
        print(f"     hash: {e['hash'][:20]}... ← prev: {e['prev_hash'][:20]}...")

    print(f"\n  Total: {len(entries)} entries")

    # Show integrity check
    integrity = verify_log_integrity()
    print(f"  Integrity: {integrity['message']}")
    print(f"{'='*65}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  NOVA — Audit Log Test")
    print(f"{'='*50}\n")

    print("  Writing test events...")

    log_event("VOICE_FAIL",   "driver1", False, {"score": 0.43, "threshold": 0.85})
    log_event("VOICE_FAIL",   "driver1", False, {"score": 0.51, "threshold": 0.85})
    log_event("PIN_PASS",     "driver1", True,  {"method": "spoken"})
    log_event("SESSION_START","driver1", True,  {"duration": 900})
    log_event("PAYMENT_AUTH", "driver1", True,  {"amount": 180, "merchant": "Starbucks"})

    print_log()

    # Test integrity
    integrity = verify_log_integrity()
    print(f"  Integrity check: {integrity['message']}\n")
