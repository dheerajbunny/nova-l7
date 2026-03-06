"""
crypto_utils.py
---------------
Handles ALL encryption and decryption for Layer 3.
Uses AES-256 (via Fernet) to protect voiceprints and face embeddings.

Simple rule:
  - Before saving anything sensitive to disk  → encrypt it
  - Before using anything loaded from disk    → decrypt it
"""

import os
import json
from pathlib import Path
from cryptography.fernet import Fernet


# ── Key file location ──────────────────────────────────────────────────────────
# The encryption key is stored in a separate file.
# In production this would be in a hardware secure enclave.
# For now: a local key file that never gets committed to git.
KEY_FILE = Path(__file__).parent / "data" / ".secret.key"


# ══════════════════════════════════════════════════════════════════════════════
#  KEY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def load_or_create_key() -> bytes:
    """
    Load existing key from disk, or create a new one if it doesn't exist.
    Called once at startup. The key is reused for all encrypt/decrypt calls.
    """
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)

    if KEY_FILE.exists():
        # Key already exists — load it
        with open(KEY_FILE, "rb") as f:
            key = f.read()
        print("[crypto] Loaded existing encryption key.")
    else:
        # First time — generate a new key and save it
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        print("[crypto] Generated new encryption key and saved.")

    return key


def get_cipher() -> Fernet:
    """
    Returns a ready-to-use cipher object.
    Every encrypt/decrypt call uses this.
    """
    key = load_or_create_key()
    return Fernet(key)


# ══════════════════════════════════════════════════════════════════════════════
#  ENCRYPT / DECRYPT
# ══════════════════════════════════════════════════════════════════════════════

def encrypt_and_save(data: bytes, filepath: Path) -> None:
    """
    Encrypt raw bytes and save to a file.

    Use this when saving:
      - voice fingerprints (numpy arrays converted to bytes)
      - face embeddings (numpy arrays converted to bytes)

    Example:
        encrypt_and_save(fingerprint_bytes, Path("data/voiceprints/driver1.enc"))
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    cipher = get_cipher()
    encrypted = cipher.encrypt(data)
    with open(filepath, "wb") as f:
        f.write(encrypted)
    print(f"[crypto] Encrypted and saved → {filepath}")


def load_and_decrypt(filepath: Path) -> bytes:
    """
    Load an encrypted file and return the original raw bytes.

    Use this when loading:
      - voice fingerprints before comparison
      - face embeddings before face match

    Example:
        raw_bytes = load_and_decrypt(Path("data/voiceprints/driver1.enc"))
    """
    if not filepath.exists():
        raise FileNotFoundError(f"[crypto] File not found: {filepath}")

    cipher = get_cipher()
    with open(filepath, "rb") as f:
        encrypted = f.read()
    return cipher.decrypt(encrypted)


# ══════════════════════════════════════════════════════════════════════════════
#  CONVENIENCE WRAPPERS FOR NUMPY ARRAYS
# ══════════════════════════════════════════════════════════════════════════════

def save_array(array, filepath: Path) -> None:
    """
    Save a numpy array encrypted to disk.
    Converts array → bytes → encrypt → save.

    Used for: voice fingerprints, face embeddings
    """
    import numpy as np
    import io
    buffer = io.BytesIO()
    np.save(buffer, array)
    encrypt_and_save(buffer.getvalue(), filepath)


def load_array(filepath: Path):
    """
    Load an encrypted numpy array from disk.
    Loads file → decrypt → bytes → numpy array.

    Used for: voice fingerprints, face embeddings
    """
    import numpy as np
    import io
    raw = load_and_decrypt(filepath)
    buffer = io.BytesIO(raw)
    return np.load(buffer)


# ══════════════════════════════════════════════════════════════════════════════
#  QUICK TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import numpy as np

    print("\n" + "="*50)
    print("  crypto_utils.py — Self Test")
    print("="*50)

    # Test 1: encrypt and decrypt raw bytes
    original = b"Hello NOVA - this is a secret"
    path = Path("data/test_encrypt.enc")
    encrypt_and_save(original, path)
    recovered = load_and_decrypt(path)
    assert original == recovered, "FAIL: bytes mismatch"
    print("  [TEST 1] Raw bytes encrypt/decrypt → PASS ")

    # Test 2: save and load numpy array
    arr = np.random.rand(192).astype(np.float32)
    arr_path = Path("data/test_array.enc")
    save_array(arr, arr_path)
    loaded = load_array(arr_path)
    assert np.allclose(arr, loaded), "FAIL: array mismatch"
    print("  [TEST 2] Numpy array save/load     → PASS ")

    # Cleanup test files
    path.unlink(missing_ok=True)
    arr_path.unlink(missing_ok=True)

    print("\n  All tests passed. crypto_utils is ready.")
    print("="*50 + "\n")
