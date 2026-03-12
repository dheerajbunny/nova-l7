"""
enroll.py
---------
Registers a new driver into the NOVA system.

What it does:
  1. Asks for driver's name (for personalized greeting)
  2. Records 5 voice samples from the driver
  3. Extracts voice fingerprint using ECAPA-TDNN (SpeechBrain)
  4. Averages 5 fingerprints into 1 master fingerprint
  5. Encrypts and saves the fingerprint (AES-256)
  6. Captures a face photo from webcam
  7. Extracts face embedding and saves encrypted
  8. Takes a PIN and saves it as SHA-256 hash
  9. Saves driver profile to profiles.json (name, preferences)

Run this ONCE per driver:
  python enroll.py --driver driver1
"""

import os
import sys
import time
import json
import hashlib
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

# ── Local imports ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from crypto_utils import save_array, encrypt_and_save

# ── Data folders ──────────────────────────────────────────────────────────────
DATA_DIR       = Path(__file__).parent / "data"
VOICEPRINT_DIR = DATA_DIR / "voiceprints"
FACE_DIR       = DATA_DIR / "faces"
PIN_DIR        = DATA_DIR / "pins"
PROFILES_PATH  = DATA_DIR / "profiles.json"

for d in [VOICEPRINT_DIR, FACE_DIR, PIN_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def load_profiles() -> dict:
    """Load all driver profiles from profiles.json."""
    if PROFILES_PATH.exists():
        with open(PROFILES_PATH, "r") as f:
            return json.load(f)
    return {}


def save_profiles(profiles: dict) -> None:
    """Save all driver profiles to profiles.json."""
    with open(PROFILES_PATH, "w") as f:
        json.dump(profiles, f, indent=2)


def save_driver_profile(driver_id: str, name: str) -> None:
    """Save or update a driver's profile."""
    profiles = load_profiles()
    profiles[driver_id] = {
        "name":                name,
        "preferred_merchants": [],
        "payment_method":      "Nova Pay •••• 4242",
        "enrolled_at":         datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_seen":           None,
        "total_orders":        0,
    }
    save_profiles(profiles)
    print(f"  ✅  Profile saved → {PROFILES_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 0 — ASK FOR NAME
# ══════════════════════════════════════════════════════════════════════════════

def enroll_name(driver_id: str) -> str:
    """Ask driver for their name to use in personalized greetings."""
    print(f"\n{'='*55}")
    print(f"  PROFILE SETUP — {driver_id}")
    print(f"{'='*55}")
    print(f"  Nova will use your name for personalized greetings.")
    print(f"  Example: 'Hey Pavan! Welcome back.'")
    print(f"{'='*55}\n")

    while True:
        name = input("  What should Nova call you? (e.g. Pavan): ").strip()
        if name:
            confirm = input(f"  Nova will greet you as '{name}'. Correct? (y/n): ")
            if confirm.lower() == 'y':
                print(f"\n  ✅  Name saved: {name}\n")
                return name
        else:
            print("  ❌  Name cannot be empty. Try again.")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — RECORD VOICE SAMPLES
# ══════════════════════════════════════════════════════════════════════════════

def record_audio(duration: float = 3.0, sample_rate: int = 16000) -> np.ndarray:
    import pyaudio
    CHUNK = 1024
    FORMAT = pyaudio.paFloat32
    CHANNELS = 1
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=sample_rate,
                    input=True, frames_per_buffer=CHUNK)
    frames = []
    total_chunks = int(sample_rate / CHUNK * duration)
    for i in range(total_chunks):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(np.frombuffer(data, dtype=np.float32))
    stream.stop_stream()
    stream.close()
    p.terminate()
    return np.concatenate(frames)


def save_wav(audio: np.ndarray, filepath: Path, sample_rate: int = 16000) -> None:
    import soundfile as sf
    sf.write(str(filepath), audio, sample_rate)


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — EXTRACT VOICE FINGERPRINT
# ══════════════════════════════════════════════════════════════════════════════

def extract_fingerprint(wav_path: Path) -> np.ndarray:
    from speechbrain.inference.speaker import EncoderClassifier
    import torch
    import torchaudio

    print("    [fingerprint] Loading ECAPA-TDNN model...")
    model = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="pretrained_models/spkrec-ecapa-voxceleb",
        run_opts={"device": "cpu"}
    )
    waveform, sr = torchaudio.load(str(wav_path))
    if sr != 16000:
        resampler = torchaudio.transforms.Resample(sr, 16000)
        waveform = resampler(waveform)
    with torch.no_grad():
        embedding = model.encode_batch(waveform)
    return embedding.squeeze().numpy()


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — ENROLL VOICE
# ══════════════════════════════════════════════════════════════════════════════

def enroll_voice(driver_id: str, num_samples: int = 5) -> bool:
    print(f"\n{'='*55}")
    print(f"  VOICE ENROLLMENT — {driver_id}")
    print(f"{'='*55}")
    print(f"  We will record {num_samples} voice samples.")
    print(f"  Speak naturally for 3 seconds each time.")
    print(f"  Tip: vary slightly — normal, morning voice, relaxed")
    print(f"{'='*55}\n")

    temp_dir = DATA_DIR / "temp_enrollment"
    temp_dir.mkdir(exist_ok=True)
    fingerprints = []

    for i in range(1, num_samples + 1):
        input(f"  Sample {i}/{num_samples} — Press ENTER then speak for 3 seconds...")
        print(f"  🎙️  Recording... speak now")
        audio = record_audio(duration=3.0)
        wav_path = temp_dir / f"{driver_id}_sample_{i}.wav"
        save_wav(audio, wav_path)
        print(f"  ✅  Recorded. Extracting fingerprint...")
        try:
            fp = extract_fingerprint(wav_path)
            fingerprints.append(fp)
            print(f"  📊  Fingerprint extracted (shape: {fp.shape})")
        except Exception as e:
            print(f"  ❌  Error extracting fingerprint: {e}")
            return False

    master_fingerprint = np.mean(fingerprints, axis=0)
    master_fingerprint = master_fingerprint / np.linalg.norm(master_fingerprint)
    save_path = VOICEPRINT_DIR / f"{driver_id}.enc"
    save_array(master_fingerprint, save_path)
    print(f"  🔒  Encrypted voiceprint saved → {save_path}")
    print(f"  ✅  Voice enrollment complete!\n")

    for f in temp_dir.glob(f"{driver_id}_*.wav"):
        f.unlink()
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — ENROLL FACE
# ══════════════════════════════════════════════════════════════════════════════

def enroll_face(driver_id: str) -> bool:
    import cv2
    print(f"\n{'='*55}")
    print(f"  FACE ENROLLMENT — {driver_id}")
    print(f"{'='*55}\n")
    input("  Press ENTER to activate webcam. Look directly at camera...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("  ❌  Webcam not found. Skipping face enrollment.")
        return False
    print("  📷  Webcam active. Capturing in 3 seconds...")
    time.sleep(3)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("  ❌  Failed to capture frame.")
        return False
    temp_path = DATA_DIR / f"temp_{driver_id}_face.jpg"
    cv2.imwrite(str(temp_path), frame)
    try:
        from deepface import DeepFace
        print("  🔄  Extracting face embedding...")
        result = DeepFace.represent(img_path=str(temp_path),
                                    model_name="Facenet", enforce_detection=True)
        embedding = np.array(result[0]["embedding"], dtype=np.float32)
        save_path = FACE_DIR / f"{driver_id}.enc"
        save_array(embedding, save_path)
        print(f"  🔒  Encrypted face embedding saved → {save_path}")
        print(f"  ✅  Face enrollment complete!\n")
    except Exception as e:
        print(f"  ❌  Face extraction failed: {e}")
        temp_path.unlink(missing_ok=True)
        return False
    temp_path.unlink(missing_ok=True)
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 5 — ENROLL PIN
# ══════════════════════════════════════════════════════════════════════════════

def enroll_pin(driver_id: str) -> bool:
    import getpass
    print(f"\n{'='*55}")
    print(f"  PIN ENROLLMENT — {driver_id}")
    print(f"{'='*55}")
    print(f"  Set a 4-digit PIN as fallback if voice fails.")
    print(f"  The PIN is NEVER stored — only a hash of it.")
    print(f"{'='*55}\n")
    while True:
        pin = getpass.getpass("  Enter 4-digit PIN (hidden): ")
        if not pin.isdigit() or len(pin) != 4:
            print("  ❌  PIN must be exactly 4 digits. Try again.")
            continue
        confirm = getpass.getpass("  Confirm PIN: ")
        if pin != confirm:
            print("  ❌  PINs don't match. Try again.")
            continue
        break
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    save_path = PIN_DIR / f"{driver_id}.txt"
    with open(save_path, "w") as f:
        f.write(pin_hash)
    print(f"\n  🔒  PIN hash saved → {save_path}")
    print(f"  ✅  PIN enrollment complete!\n")
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ENROLLMENT FLOW
# ══════════════════════════════════════════════════════════════════════════════

def enroll_driver(driver_id: str, skip_face: bool = False) -> None:
    print(f"\n{'#'*55}")
    print(f"#  NOVA — DRIVER ENROLLMENT")
    print(f"#  Driver ID: {driver_id}")
    print(f"{'#'*55}")

    voice_path = VOICEPRINT_DIR / f"{driver_id}.enc"
    if voice_path.exists():
        overwrite = input(f"\n  ⚠️  Driver '{driver_id}' already enrolled. Re-enroll? (y/n): ")
        if overwrite.lower() != 'y':
            print("  Enrollment cancelled.")
            return

    results = {}

    # 0. Name
    name = enroll_name(driver_id)

    # 1. Voice
    results["voice"] = enroll_voice(driver_id)

    # 2. Face
    if not skip_face:
        results["face"] = enroll_face(driver_id)
    else:
        print("\n  [Face enrollment skipped]")
        results["face"] = False

    # 3. PIN
    results["pin"] = enroll_pin(driver_id)

    # 4. Save profile
    if results["voice"] and results["pin"]:
        save_driver_profile(driver_id, name)

    # Summary
    print(f"\n{'='*55}")
    print(f"  ENROLLMENT SUMMARY — {driver_id}")
    print(f"{'='*55}")
    print(f"  Name              : {name}")
    print(f"  Voice fingerprint : {'✅ Done' if results['voice'] else '❌ Failed'}")
    print(f"  Face ID           : {'✅ Done' if results['face'] else '⚠️  Skipped/Failed'}")
    print(f"  PIN               : {'✅ Done' if results['pin'] else '❌ Failed'}")
    print(f"  Profile saved     : ✅ {PROFILES_PATH}")
    print(f"{'='*55}")

    if results["voice"] and results["pin"]:
        print(f"\n  🎉  Driver '{driver_id}' enrolled successfully!")
        print(f"  Nova will now greet you as '{name}'.")
        print(f"  Run verify.py to test identity verification.\n")
    else:
        print(f"\n  ⚠️  Enrollment incomplete. Voice and PIN are required.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NOVA Driver Enrollment")
    parser.add_argument("--driver", type=str, default="driver1")
    parser.add_argument("--skip-face", action="store_true")
    args = parser.parse_args()
    enroll_driver(args.driver, skip_face=args.skip_face)