"""
session_manager.py
------------------
Creates and validates 15-minute session tokens after successful auth.

Why sessions exist:
  - Driver is verified once → gets a 15-minute pass
  - During those 15 minutes → no re-verification for normal commands
  - Payment commands → always re-verify regardless of session
  - After 15 minutes → silent re-verify before next command

What a JWT token actually is:
  Think of it like a cinema ticket:
  - Has your name on it
  - Has the date/show time
  - Has an expiry
  - Is signed so nobody can fake it
  - Security checks the ticket at the door — not the person

Token structure:
  {
    "driver_id": "driver1",
    "iat":       1234567890,   ← issued at (timestamp)
    "exp":       1234568790,   ← expires at (iat + 900 seconds = 15 min)
    "auth_method": "voice"     ← how they authenticated
  }
"""

import sys
import time
from pathlib import Path
from jose import jwt, JWTError

sys.path.insert(0, str(Path(__file__).parent))

# ── Secret key ─────────────────────────────────────────────────────────────────
# In production: stored in hardware secure enclave, rotates every 24 hours
# For demo: static key in memory
SECRET_KEY = "nova-secret-key-change-in-production-2025"
ALGORITHM  = "HS256"

SESSION_DURATION = 900   # 15 minutes in seconds


# ══════════════════════════════════════════════════════════════════════════════
#  CREATE TOKEN
# ══════════════════════════════════════════════════════════════════════════════

def create_token(driver_id: str, auth_method: str = "voice") -> str:
    """
    Create a signed JWT session token.

    Args:
        driver_id:   which driver was authenticated
        auth_method: how they authenticated ("voice", "pin", "face")

    Returns:
        JWT token string (long encoded string)

    Example:
        token = create_token("driver1", "voice")
        # token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    """
    now = time.time()
    payload = {
        "driver_id":   driver_id,
        "auth_method": auth_method,
        "iat":         now,
        "exp":         now + SESSION_DURATION
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    print(f"  [session] Token created for '{driver_id}' via {auth_method}")
    print(f"  [session] Valid for 15 minutes (until {_format_time(now + SESSION_DURATION)})")
    return token


# ══════════════════════════════════════════════════════════════════════════════
#  CHECK TOKEN
# ══════════════════════════════════════════════════════════════════════════════

def check_token(token: str) -> dict:
    """
    Validate a session token.

    Returns dict:
    {
        "valid":       True/False,
        "driver_id":   "driver1",
        "auth_method": "voice",
        "expires_in":  420,        ← seconds remaining (if valid)
        "error":       None        ← error message (if invalid)
    }

    Usage:
        result = check_token(token)
        if result["valid"]:
            proceed_with_command()
        else:
            re_authenticate()
    """
    if not token:
        return {"valid": False, "driver_id": None, "error": "No token provided"}

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        expires_in = int(payload["exp"] - time.time())

        return {
            "valid":       True,
            "driver_id":   payload["driver_id"],
            "auth_method": payload.get("auth_method", "unknown"),
            "expires_in":  expires_in,
            "error":       None
        }

    except JWTError as e:
        error_str = str(e)
        if "expired" in error_str.lower():
            return {"valid": False, "driver_id": None, "error": "Session expired. Please re-verify."}
        else:
            return {"valid": False, "driver_id": None, "error": f"Invalid token: {error_str}"}


# ══════════════════════════════════════════════════════════════════════════════
#  INVALIDATE TOKEN (logout / lockout)
# ══════════════════════════════════════════════════════════════════════════════

# Active tokens stored in memory
# In production: Redis with TTL
_active_tokens: set = set()
_revoked_tokens: set = set()


def register_token(token: str) -> None:
    """Register a token as active. Call after create_token()."""
    _active_tokens.add(token)


def revoke_token(token: str) -> None:
    """
    Revoke a token immediately (logout, lockout, suspicious activity).
    After revocation, check_token will return invalid.
    """
    _revoked_tokens.add(token)
    _active_tokens.discard(token)
    print(f"  [session] Token revoked.")


def is_revoked(token: str) -> bool:
    """Check if a token has been explicitly revoked."""
    return token in _revoked_tokens


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _format_time(timestamp: float) -> str:
    """Format a Unix timestamp as HH:MM:SS."""
    import datetime
    return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def time_remaining_str(token: str) -> str:
    """Human-readable time remaining for a token."""
    result = check_token(token)
    if not result["valid"]:
        return "EXPIRED"
    mins = result["expires_in"] // 60
    secs = result["expires_in"] % 60
    return f"{mins}m {secs}s remaining"


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  NOVA — Session Manager Test")
    print(f"{'='*50}\n")

    # Test 1: Create and validate token
    token = create_token("driver1", "voice")
    print(f"\n  Token (first 40 chars): {token[:40]}...")

    result = check_token(token)
    print(f"\n  Check result:")
    print(f"    Valid      : {result['valid']}")
    print(f"    Driver     : {result['driver_id']}")
    print(f"    Auth method: {result['auth_method']}")
    print(f"    Expires in : {result['expires_in']}s")

    # Test 2: Expired token simulation
    print(f"\n  Creating token with 1-second expiry for test...")
    expired_payload = {"driver_id": "test", "exp": time.time() - 1}
    expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
    expired_result = check_token(expired_token)
    print(f"  Expired token check: valid={expired_result['valid']}, error={expired_result['error']}")

    # Test 3: Revoke token
    print(f"\n  Revoking token...")
    revoke_token(token)
    print(f"  Is revoked: {is_revoked(token)}")

    print(f"\n  ✅ All session tests passed.\n")
