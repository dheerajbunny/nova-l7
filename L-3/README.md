# NOVA — Layer 3: Voice Biometric Authentication

## What This Layer Does
Layer 3 handles all identity verification for NOVA.
Before any sensitive command (payment, email, tool access) is executed —
Layer 3 confirms the driver is who they claim to be.

---

## Files
```
L-3/
├── layer3_main.py      — main entry point, authenticate() function
├── verify.py           — voice biometric verification (ECAPA-TDNN)
├── enroll.py           — one-time driver enrollment
├── crypto_utils.py     — AES-256 encryption / decryption
├── pin_handler.py      — PIN fallback (SHA-256 hashed)
├── face_handler.py     — Face ID fallback (Facenet)
├── session_manager.py  — JWT session token management
├── audit_log.py        — tamper-proof chained hash audit log
└── README.md           — this file
```

---

## How It Works

### 3-Level Authentication
```
Level 1 — Voice Biometric (ECAPA-TDNN)
  Score >= 0.55 (laptop) / 0.85 (production mic) → PASS

Level 2 — PIN Fallback (if voice fails 3x)
  4-digit PIN → SHA-256 hashed → compared

Level 3 — Face ID Fallback (if PIN fails)
  Webcam capture → Facenet embedding → compared

All levels fail → LOCKOUT
```

### Session Token
- On pass → JWT token created, valid 15 minutes
- Token returned to Layer 7
- Layer 7 stores token, checks validity on each sensitive command

### Voice OTP (Payment only)
- Random 4-digit code spoken by Nova
- Driver repeats it back
- Unique per transaction — replay attacks impossible

---

## Setup — First Time

### 1. Install Dependencies
```bash
pip install speechbrain deepface opencv-python cryptography python-jose pyaudio soundfile "numpy<2"
```

### 2. Run as Administrator (Windows)
SpeechBrain requires symlink permissions on Windows.
Always open PowerShell as Administrator before running.

### 3. Enroll Yourself
```bash
python enroll.py --driver driver1
```
This will:
- Record 5 voice samples → create encrypted voice fingerprint
- Capture face photo → create face embedding
- Ask you to set a 4-digit PIN

### 4. Test Encryption
```bash
python crypto_utils.py
```
Expected: Both AES-256 tests passed.

### 5. Test Voice Verification
```bash
python verify.py --driver driver1
```
Speak clearly. Score should be 0.55+ on laptop.

### 6. Test Full Flow
```bash
python layer3_main.py --driver driver1
```

### 7. Test Payment Flow
```bash
python layer3_main.py --driver driver1 --payment --show-log
```

---

## Important Notes

### Threshold
```
Laptop mic (demo)    : 0.55  ← adjusted for demo
Production mic array : 0.85  ← 4-mic Jetson array
```

### Data Folder
```
data/
├── voiceprints/driver1.enc  ← AES-256 encrypted voice fingerprint
├── pins/driver1.txt         ← SHA-256 hashed PIN (not reversible)
└── .secret.key              ← AES-256 key (keep private)
```
**This folder is in .gitignore — never pushed to GitHub.**
**Each developer must enroll themselves after cloning.**

### Models
ECAPA-TDNN model (~80MB) downloads automatically from HuggingFace
on first run. Internet required for first run only.

---

## Connected To
- **Layer 7** calls `authenticate(driver_id)` from `layer3_main.py`
- Returns JWT session token on success, None on failure
- Layer 7 stores token and checks `check_session(token)` validity

---

## Cryptography Stack

| What | Method | Why |
|------|--------|-----|
| Voice fingerprint | AES-256 | Two-way — need to decrypt for comparison |
| Face embedding | AES-256 | Two-way — need to decrypt for comparison |
| PIN | SHA-256 | One-way — never need original PIN back |
| Session token | JWT HS256 | Signed — tamper proof, 15 min expiry |
| Audit log | Chained SHA-256 | Tamper detection — blockchain principle |

---

## Troubleshooting

**WinError 1314 — symlink error**
Run PowerShell as Administrator.

**Score too low (below 0.55)**
Re-enroll with 8 samples: `python enroll.py --driver driver1 --samples 8`
Speak clearly in a quiet environment.

**Model download fails**
Check internet connection. Model downloads from HuggingFace on first run.
After first run — works offline.