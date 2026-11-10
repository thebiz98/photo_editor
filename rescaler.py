"""
rescaler.py - Resolution & Image Rescaling Domain Engine.
Handles deterministic CPU-based scaling, anti-aliased downsampling,
smart edge sharpening, and safety dimension ceilings.
Also provides offline ONNX Real-ESRGAN neural super-resolution (2x).
Zero Qt dependencies: 100% testable domain logic.
"""

from pathlib import Path
from typing import Tuple, Optional
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter

# Safety Constants
MIN_SCALE_PCT = 10         # Minimum downscale: 10%
MAX_SCALE_PCT = 400        # Maximum upscale per step: 400%
MAX_SAFE_IMAGE_DIM = 4096  # Hard pixel ceiling on width/height (~50 MP memory limit)
MAX_AI_INPUT_DIM = 1800    # Hard ceiling for AI input to prevent OOM / multi-GB tensor allocations

BASE_DIR = Path(__file__).resolve().parent
SUPERRES_MODEL_PATH = BASE_DIR / "models" / "superres" / "model.onnx"


def calculate_target_dimensions(orig_w: int, orig_h: int, scale_pct: float) -> Tuple[int, int]:
    """
    Calculates target width and height in pixels for a given scale percentage.
    Guarantees minimum dimension of 1x1 px.
    """
    factor = scale_pct / 100.0
    target_w = max(1, round(orig_w * factor))
    target_h = max(1, round(orig_h * factor))
    return (target_w, target_h)


def is_within_safe_limits(w: int, h: int, max_dim: int = MAX_SAFE_IMAGE_DIM) -> bool:
    """Returns True if both dimensions are within the safe hardware memory ceiling."""
    return max(w, h) <= max_dim


def rescale_image(
    img: Image.Image,
    scale_pct: float,
    max_dim: int = MAX_SAFE_IMAGE_DIM,
    smart_sharpen: bool = True
) -> Tuple[Image.Image, Tuple[int, int]]:
    """
    Rescales an image by percentage (10% to 400%).

    Behaviors:
    - If scale_pct == 100: returns a copy of img.
    - If scale_pct < 100: Anti-aliased downsampling via Image.Resampling.LANCZOS.
    - If scale_pct > 100: Upsampling via Image.Resampling.LANCZOS.
      If smart_sharpen is True and scale_pct >= 125, applies a subtle UnsharpMask
      (radius=1.2, percent=40, threshold=3) to restore perceptual edge crispness.
    - Raises ValueError if target width or height exceeds max_dim.

    Returns:
        Tuple[Image.Image, Tuple[int, int]]: (scaled_image, (new_w, new_h))
    """
    if scale_pct <= 0:
        raise ValueError(f"Scale percentage must be positive, got {scale_pct}%")

    orig_w, orig_h = img.size
    new_w, new_h = calculate_target_dimensions(orig_w, orig_h, scale_pct)

    if not is_within_safe_limits(new_w, new_h, max_dim):
        raise ValueError(
            f"Target size ({new_w}x{new_h} px) exceeds safe ceiling of {max_dim} px. "
            "Scaling aborted to protect system memory."
        )

    if scale_pct == 100:
        return img.copy(), (orig_w, orig_h)

    # Perform high-quality Lanczos resampling
    resampled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Apply smart subtle sharpening for substantial upscaling
    if smart_sharpen and scale_pct >= 125:
        resampled = resampled.filter(
            ImageFilter.UnsharpMask(radius=1.2, percent=40, threshold=3)
        )

    return resampled, (new_w, new_h)


class SuperResolutionEngine:
    """
    Offline ONNX Super-Resolution Engine (Real-ESRGAN 2x).
    Lazy-loads inference session with CPUExecutionProvider on Windows ARM64.
    """
    def __init__(self, model_path: Path = SUPERRES_MODEL_PATH):
        self.model_path = model_path
        self._session: Optional[ort.InferenceSession] = None

    def is_available(self) -> bool:
        """Returns True if local ONNX model file exists and is valid (> 5 MB)."""
        return self.model_path.exists() and self.model_path.stat().st_size > 5_000_000

    def _get_session(self) -> ort.InferenceSession:
        if self._session is None:
            if not self.is_available():
                raise FileNotFoundError(
                    f"Super-resolution model not found at {self.model_path}. "
                    "Run download_models.py to download."
                )
            self._session = ort.InferenceSession(
                str(self.model_path),
                providers=["CPUExecutionProvider"]
            )
        return self._session

    def enhance_2x(self, img: Image.Image) -> Image.Image:
        """
        Runs 2x neural super-resolution on a PIL Image.
        Raises ValueError if image dimensions exceed MAX_AI_INPUT_DIM.
        """
        w, h = img.size
        if max(w, h) > MAX_AI_INPUT_DIM:
            raise ValueError(
                f"Image dimensions ({w}x{h} px) exceed maximum AI input ceiling ({MAX_AI_INPUT_DIM} px). "
                "Use Scale % for manual adjustments."
            )

        rgb = img.convert("RGB")
        session = self._get_session()
        input_name = session.get_inputs()[0].name

        # Prepare float32 NCHW tensor in [0.0, 1.0] range
        img_np = np.array(rgb, dtype=np.float32) / 255.0
        tensor = np.transpose(img_np, (2, 0, 1))[np.newaxis, :, :, :]
        tensor = np.ascontiguousarray(tensor, dtype=np.float32)

        # Execute ONNX inference
        output = session.run(None, {input_name: tensor})[0][0]

        # Post-process: CHW [0.0, 1.0] -> HWC uint8 [0, 255]
        output = np.clip(output * 255.0, 0, 255).astype(np.uint8)
        output_hwc = np.transpose(output, (1, 2, 0))
        return Image.fromarray(output_hwc, mode="RGB")


# Global singleton instance for clean reuse across UI actions
GLOBAL_SUPERRES_ENGINE = SuperResolutionEngine()


if __name__ == "__main__":
    # Self-test block
    test_img = Image.new("RGB", (400, 500), (200, 100, 50))
    downscaled, dims = rescale_image(test_img, 50)
    assert dims == (200, 250), f"Downscale failed: {dims}"
    upscaled, dims = rescale_image(test_img, 200)
    assert dims == (800, 1000), f"Upscale failed: {dims}"
    print("rescaler.py compute tests passed successfully.")

    if GLOBAL_SUPERRES_ENGINE.is_available():
        small_test = Image.new("RGB", (80, 100), (100, 150, 200))
        ai_out = GLOBAL_SUPERRES_ENGINE.enhance_2x(small_test)
        assert ai_out.size == (160, 200), f"AI Enhance failed: {ai_out.size}"
        print("rescaler.py AI Super-Resolution test passed successfully.")
    else:
        print("AI Super-Resolution model not yet present.")
