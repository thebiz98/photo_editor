"""
rescaler.py - Resolution & Image Rescaling Domain Engine.
Handles deterministic CPU-based scaling, anti-aliased downsampling,
smart edge sharpening, and safety dimension ceilings.
Zero Qt dependencies: 100% testable domain logic.
"""

from typing import Tuple
from PIL import Image, ImageFilter

# Safety Constants
MIN_SCALE_PCT = 10         # Minimum downscale: 10%
MAX_SCALE_PCT = 400        # Maximum upscale per step: 400%
MAX_SAFE_IMAGE_DIM = 4096  # Hard pixel ceiling on width/height (~50 MP memory limit)


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


if __name__ == "__main__":
    # Self-test block
    test_img = Image.new("RGB", (400, 500), (200, 100, 50))
    downscaled, dims = rescale_image(test_img, 50)
    assert dims == (200, 250), f"Downscale failed: {dims}"
    upscaled, dims = rescale_image(test_img, 200)
    assert dims == (800, 1000), f"Upscale failed: {dims}"
    print("rescaler.py unit tests passed successfully.")
