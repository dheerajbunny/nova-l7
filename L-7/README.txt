LAYER 3 SETUP & RUN GUIDE
=================================

STEP 1 — INSTALL LIBRARIES
---------------------------
Open terminal, activate your environment, then run:

  pip install speechbrain deepface opencv-python cryptography python-jose pyaudio soundfile

NOTE: SpeechBrain will download ECAPA-TDNN model (~80MB) on first run.
      Needs internet once. After that works offline.


STEP 2 — FOLDER STRUCTURE
--------------------------
Your layer3 folder should look like this:

  layer3/
  ├── data/
  │   ├── voiceprints/    ← encrypted fingerprints saved here
  │   ├── faces/          ← encrypted face embeddings
  │   ├── pins/           ← SHA-256 hashed PINs
  │   └── audit_log.json  ← tamper-proof event log
  ├── crypto_utils.py
  ├── enroll.py
  ├── verify.py
  ├── pin_handler.py
  ├── face_handler.py
  ├── session_manager.py
  ├── audit_log.py
  └── layer3_main.py


STEP 3 — TEST CRYPTO (30 seconds)
-----------------------------------
  python crypto_utils.py

  Expected output:
    [TEST 1] Raw bytes encrypt/decrypt → PASS 
    [TEST 2] Numpy array save/load     → PASS 


STEP 4 — ENROLL YOURSELF AS DRIVER
------------------------------------
  python enroll.py --driver driver1

  What happens:
  - Speaks 5 voice samples (3 sec each)
  - Captures face photo from webcam
  - Sets a 4-digit PIN
  - All saved encrypted to data/ folder

  If no webcam:
  python enroll.py --driver driver1 --skip-face


STEP 5 — TEST VOICE VERIFICATION
-----------------------------------
  python verify.py --driver driver1

  Expected output:
    Score     : 0.89
    Threshold : 0.85
    Result    : IDENTITY CONFIRMED
    Time      : 340ms


STEP 6 — TEST FULL AUTH FLOW
------------------------------
  python layer3_main.py --driver driver1

  This runs all 3 levels:
  - Voice → PIN fallback → Face fallback
  - Creates session token
  - Shows result


STEP 7 — TEST PAYMENT FLOW
----------------------------
  python layer3_main.py --driver driver1 --payment

  This runs:
  - Full auth flow
  - Voice OTP challenge
  - Payment confirmation
  - Shows audit log entry


STEP 8 — VIEW AUDIT LOG
-------------------------
  python layer3_main.py --driver driver1 --show-log

  Shows every auth event with hashes chained.


WHAT EACH FILE DOES (one line each)
-------------------------------------
  crypto_utils.py    → AES-256 encrypt/decrypt for all stored data
  enroll.py          → Register a new driver (voice + face + PIN)
  verify.py          → Check voice match against stored fingerprint
  pin_handler.py     → Check spoken PIN against stored hash
  face_handler.py    → Check live face against stored embedding
  session_manager.py → Create and validate 15-minute session tokens
  audit_log.py       → Write tamper-proof chained hash log
  layer3_main.py     → Ties everything together (what Layer 7 calls)


COMMON ERRORS AND FIXES
-------------------------

Error: "No module named pyaudio"
Fix:   pip install pyaudio
       On Windows if that fails: pip install pipwin && pipwin install pyaudio

Error: "No module named speechbrain"
Fix:   pip install speechbrain

Error: "Driver not enrolled"
Fix:   Run enroll.py first

Error: "Camera not available"
Fix:   Use --skip-face flag during enrollment

Error: "Score too low even for correct person"
Fix:   Re-enroll with more samples in different conditions
       python enroll.py --driver driver1  (choose y to re-enroll)
