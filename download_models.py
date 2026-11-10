"""
download_models.py - One-time model downloader and bundler.
Ensures ONNX models exist locally in ./models/ for 100% offline runtime.
"""

import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
RMBG_DIR = MODELS_DIR / "rmbg14"
MODNET_DIR = MODELS_DIR / "modnet"
SUPERRES_DIR = MODELS_DIR / "superres"

RMBG_FILE = RMBG_DIR / "model.onnx"
MODNET_FILE = MODNET_DIR / "model.onnx"
SUPERRES_FILE = SUPERRES_DIR / "model.onnx"

MIN_SIZE_BYTES = 10_000_000  # 10 MB threshold

def download_direct_url(url: str, target_file: Path) -> bool:
    import urllib.request
    try:
        print(f"[STREAM] Downloading directly from {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(target_file, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = (downloaded / total) * 100
                    print(f"\r  Progress: {downloaded / (1024*1024):.1f}/{total / (1024*1024):.1f} MB ({pct:.0f}%)", end="", flush=True)
            print()
        print(f"[SUCCESS] Saved to {target_file} ({target_file.stat().st_size / (1024*1024):.2f} MB)")
        return True
    except Exception as e:
        print(f"[ERROR] Direct download failed: {e}")
        if target_file.exists():
            target_file.unlink()
        return False


def ensure_model(target_file: Path, repo_id: str, filename: str, fallback_repo: str = None):
    target_file.parent.mkdir(parents=True, exist_ok=True)
    
    if target_file.exists() and target_file.stat().st_size > MIN_SIZE_BYTES:
        print(f"[OK] Model already present: {target_file} ({target_file.stat().st_size / (1024*1024):.2f} MB)")
        return True

    print(f"[DOWNLOADING] Fetching {repo_id}/{filename} -> {target_file}...")
    try:
        from huggingface_hub import hf_hub_download
        cached_path = hf_hub_download(repo_id=repo_id, filename=filename)
        shutil.copyfile(cached_path, target_file)
        print(f"[SUCCESS] Saved to {target_file} ({target_file.stat().st_size / (1024*1024):.2f} MB)")
        return True
    except Exception as e:
        print(f"[WARN] Failed fetching from {repo_id}: {e}")
        # Try direct URL fallback
        direct_url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
        if download_direct_url(direct_url, target_file):
            return True
        if fallback_repo:
            print(f"[FALLBACK] Trying {fallback_repo}/{filename}...")
            try:
                from huggingface_hub import hf_hub_download
                cached_path = hf_hub_download(repo_id=fallback_repo, filename=filename)
                shutil.copyfile(cached_path, target_file)
                print(f"[SUCCESS] Saved to {target_file} ({target_file.stat().st_size / (1024*1024):.2f} MB)")
                return True
            except Exception as e2:
                print(f"[ERROR] Fallback failed: {e2}")
        return False

def main():
    print("=" * 60)
    print("Photo Studio - Offline ONNX Model Verification & Setup")
    print("=" * 60)
    
    ok_rmbg = ensure_model(
        target_file=RMBG_FILE,
        repo_id="briaai/RMBG-1.4",
        filename="onnx/model.onnx"
    )
    
    ok_modnet = ensure_model(
        target_file=MODNET_FILE,
        repo_id="Xenova/modnet",
        filename="onnx/model.onnx",
        fallback_repo="gradio/modnet"
    )

    ok_superres = ensure_model(
        target_file=SUPERRES_FILE,
        repo_id="JoPmt/Real_Esrgan_x2_Onnx_Tflite_Tfjs",
        filename="model.onnx"
    )

    if ok_rmbg and ok_modnet and ok_superres:
        print("\nAll required ONNX models are present and ready for offline use.")
        return 0
    else:
        print("\n[ERROR] One or more models failed to download.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
