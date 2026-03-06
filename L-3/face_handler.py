"""
face_handler.py
---------------
Handles Face ID fallback when both voice and PIN fail.

What it does:
  1. Activates webcam and captures a frame
  2. Extracts face embedding using DeepFace (Facenet model)
  3. Loads stored encrypted face embedding
  4. Compares embeddings using cosine similarity
  5. Returns pass/fail

Why this is the LAST fallback:
  - Slower than voice (~500ms vs 300ms)
  - Requires camera hardware
  - Only used when voice + PIN both fail
  - But more reliable in bad audio conditions

Face data privacy:
  - Face embedding is just numbers — cannot reconstruct the face
  - Stored encrypted with AES-256
  - Never sent to any server
"""

import sys
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from crypto_utils import load_array

DATA_DIR = Path(__file__).parent / "data"
FACE_DIR = DATA_DIR / "faces"
TEMP_DIR = DATA_DIR / "temp_face"

TEMP_DIR.mkdir(parents=True, exist_ok=True)

FACE_THRESHOLD = 0.70   # DeepFace Facenet threshold


# ══════════════════════════════════════════════════════════════════════════════
#  CAPTURE FACE FROM WEBCAM
# ══════════════════════════════════════════════════════════════════════════════

def capture_face(driver_id: str, verbose: bool = True) -> Path | None:
    """
    Activate webcam and capture a face photo.
    Returns path to saved temp image, or None if capture failed.
    """
    import cv2

    if verbose:
        print(f"  [face] Activating cabin camera...")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        if verbose:
            print(f"  [face] ❌ Camera not available.")
        return None

    # Allow camera to warm up
    time.sleep(1.0)

    if verbose:
        print(f"  [face] 📷 Capturing... look at camera")

    # Take 3 frames and use the last one (camera adjusts exposure)
    for _ in range(3):
        ret, frame = cap.read()
    cap.release()

    if not ret:
        if verbose:
            print(f"  [face] ❌ Failed to capture frame.")
        return None

    temp_path = TEMP_DIR / f"{driver_id}_live.jpg"
    cv2.imwrite(str(temp_path), frame)

    if verbose:
        print(f"  [face] Photo captured.")

    return temp_path


# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACT FACE EMBEDDING
# ══════════════════════════════════════════════════════════════════════════════

def extract_face_embedding(image_path: Path, verbose: bool = True) -> np.ndarray | None:
    """
    Extract face embedding from an image using DeepFace Facenet model.
    Returns numpy array of shape (128,), or None if no face detected.
    """
    from deepface import DeepFace

    try:
        result = DeepFace.represent(
            img_path=str(image_path),
            model_name="Facenet",
            enforce_detection=True
        )
        embedding = np.array(result[0]["embedding"], dtype=np.float32)

        # Normalize
        embedding = embedding / np.linalg.norm(embedding)

        if verbose:
            print(f"  [face] Embedding extracted (shape: {embedding.shape})")

        return embedding

    except Exception as e:
        if verbose:
            print(f"  [face] ❌ Face not detected: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  COMPARE EMBEDDINGS
# ══════════════════════════════════════════════════════════════════════════════

def compare_embeddings(live: np.ndarray, stored: np.ndarray) -> float:
    """
    Compare two face embeddings using cosine similarity.
    Both should already be normalized.
    Returns score 0.0 - 1.0
    """
    return float(np.dot(live, stored))


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN FACE VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def verify_face(driver_id: str, verbose: bool = True) -> dict:
    """
    Full face verification for a driver.

    Returns dict:
    {
        "passed":    True/False,
        "score":     0.0-1.0,
        "driver_id": "driver1",
        "error":     None
    }
    """
    start_time = time.time()

    if verbose:
        print(f"\n  [face] Level 3 fallback — Face ID")

    # Check enrollment exists
    stored_path = FACE_DIR / f"{driver_id}.enc"
    if not stored_path.exists():
        msg = f"Driver '{driver_id}' face not enrolled."
        if verbose:
            print(f"  [face] ❌ {msg}")
        return {"passed": False, "score": 0.0, "driver_id": driver_id, "error": msg}

    # Capture live face
    temp_path = capture_face(driver_id, verbose=verbose)
    if temp_path is None:
        return {
            "passed": False, "score": 0.0,
            "driver_id": driver_id,
            "error": "Camera not available or capture failed."
        }

    # Extract live embedding
    live_embedding = extract_face_embedding(temp_path, verbose=verbose)

    # Cleanup temp photo
    temp_path.unlink(missing_ok=True)

    if live_embedding is None:
        return {
            "passed": False, "score": 0.0,
            "driver_id": driver_id,
            "error": "No face detected in captured image."
        }

    # Load stored embedding (auto-decrypts)
    stored_embedding = load_array(stored_path)
    stored_embedding = stored_embedding / np.linalg.norm(stored_embedding)

    # Compare
    score = compare_embeddings(live_embedding, stored_embedding)
    passed = score >= FACE_THRESHOLD
    elapsed = int((time.time() - start_time) * 1000)

    if verbose:
        print(f"\n  [face] Score     : {score:.4f}")
        print(f"  [face] Threshold : {FACE_THRESHOLD}")
        print(f"  [face] Result    : {'✅ FACE MATCHED' if passed else '❌ FACE NOT MATCHED'}")
        print(f"  [face] Time      : {elapsed}ms\n")

    return {
        "passed":    passed,
        "score":     round(score, 4),
        "driver_id": driver_id,
        "error":     None
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NOVA Face ID Test")
    parser.add_argument("--driver", type=str, default="driver1")
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  NOVA — Face ID Fallback Test")
    print(f"  Driver: {args.driver}")
    print(f"{'='*50}\n")

    result = verify_face(args.driver)

    if result["passed"]:
        print(f"  ✅ Face matched. Access granted.")
    elif result.get("error"):
        print(f"  ❌ Error: {result['error']}")
    else:
        print(f"  ❌ Face not matched. Score: {result['score']}")
