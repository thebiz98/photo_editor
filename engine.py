"""
engine.py - Core Image, ROI Patching, Edge Refinement & ONNX Segmentation Engine.
Zero-network, 100% offline runtime using PySide6-friendly Pillow and ONNXRuntime.
"""

import hashlib
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# Base print resolution constants
DPI = 300
PX_PER_MM = 300.0 / 25.4  # ~11.8110236 px/mm

# Preset physical sizes: (width_mm, height_mm, width_px, height_px)
PRESET_SIZES = {
    "Freeform / Original": (None, None, None, None),
    "Standard Passport (35 x 45 mm)": (35.0, 45.0, 413, 531),
    "Indian Passport / US Visa (2 x 2 in / 51 x 51 mm)": (50.8, 50.8, 600, 600),
    "PAN / Official ID Portrait (25 x 35 mm)": (25.0, 35.0, 295, 413),
    "Indian Stamp Size (20 x 25 mm)": (20.0, 25.0, 236, 295),
    "Standard ID Card Full (85.6 x 54.0 mm)": (85.6, 54.0, 1011, 638),
    "Custom Size (mm)": (None, None, None, None),
}

BACKDROP_COLORS = {
    "Studio White": (255, 255, 255),
    "Passport Grey": (230, 230, 230),
    "Standard Blue": (0, 82, 180),
    "Corporate Navy": (27, 54, 93),
}

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
MODEL_PATHS = {
    "RMBG-1.4": MODELS_DIR / "rmbg14" / "model.onnx",
    "MODNet": MODELS_DIR / "modnet" / "model.onnx",
}


def compute_image_hash(img: Image.Image) -> str:
    """Fast hash for caching ONNX segmentations based on image dimensions and bytes."""
    h = hashlib.sha256()
    h.update(f"{img.width}x{img.height}_{img.mode}".encode("utf-8"))
    h.update(img.tobytes())
    return h.hexdigest()


class SegmentationEngine:
    """Lazy-loading ONNX inference engine with in-memory alpha matte caching."""

    def __init__(self):
        self._sessions: Dict[str, ort.InferenceSession] = {}
        self._alpha_cache: Dict[Tuple[str, str], Image.Image] = {}

    def _get_session(self, model_key: str) -> ort.InferenceSession:
        if model_key not in self._sessions:
            model_path = MODEL_PATHS.get(model_key)
            if not model_path or not model_path.exists():
                raise FileNotFoundError(f"Model file not found at: {model_path}")
            
            # Using CPUExecutionProvider for universal stability on Windows ARM64
            session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"]
            )
            self._sessions[model_key] = session
        return self._sessions[model_key]

    def get_alpha(self, pil_img: Image.Image, model_choice: str = "RMBG-1.4") -> Image.Image:
        """
        Extract alpha matte as a grayscale PIL Image (mode 'L').
        Uses in-memory cache to guarantee zero redundant inference.
        """
        img_rgb = pil_img.convert("RGB")
        img_hash = compute_image_hash(img_rgb)
        
        # Standardize model_choice key
        model_key = "RMBG-1.4" if "RMBG" in model_choice else "MODNet"
        cache_key = (img_hash, model_key)
        
        if cache_key in self._alpha_cache:
            return self._alpha_cache[cache_key].copy()

        session = self._get_session(model_key)
        orig_w, orig_h = img_rgb.size
        input_name = session.get_inputs()[0].name

        if model_key == "RMBG-1.4":
            # 1024x1024 input
            resized = img_rgb.resize((1024, 1024), Image.BILINEAR)
            img_np = np.array(resized, dtype=np.float32) / 255.0
            tensor = (img_np - 0.5) / 1.0
            tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis, :, :, :]
            tensor = np.ascontiguousarray(tensor, dtype=np.float32)

            pred = session.run(None, {input_name: tensor})[0][0][0]
            matte = (pred - pred.min()) / (pred.max() - pred.min() + 1e-8)
            matte_uint8 = (matte * 255.0).clip(0, 255).astype(np.uint8)
            alpha_img = Image.fromarray(matte_uint8, mode="L").resize((orig_w, orig_h), Image.LANCZOS)
        else:
            # MODNet: 512x512 input
            resized = img_rgb.resize((512, 512), Image.BILINEAR)
            img_np = np.array(resized, dtype=np.float32) / 255.0
            tensor = (img_np - 0.5) / 0.5
            tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis, :, :, :]
            tensor = np.ascontiguousarray(tensor, dtype=np.float32)

            pred = session.run(None, {input_name: tensor})[0][0][0]
            matte = np.clip(pred, 0.0, 1.0)
            matte_uint8 = (matte * 255.0).clip(0, 255).astype(np.uint8)
            alpha_img = Image.fromarray(matte_uint8, mode="L").resize((orig_w, orig_h), Image.LANCZOS)

        self._alpha_cache[cache_key] = alpha_img
        return alpha_img.copy()

    def clear_cache(self):
        """Clears cached alpha mattes."""
        self._alpha_cache.clear()


# Global singleton instance for clean reuse across UI actions
GLOBAL_SEGMENTATION_ENGINE = SegmentationEngine()


def refine_alpha(alpha_img: Image.Image, choke_px: int = 0, feather_px: float = 0.0) -> Image.Image:
    """
    Morphological edge refinement:
    - choke_px: MinFilter (erosion) eliminates background halos (0 to 5 px).
    - feather_px: GaussianBlur smooths cut edges (0.0 to 5.0 px).
    """
    refined = alpha_img.copy()
    if choke_px > 0:
        kernel_size = choke_px * 2 + 1
        refined = refined.filter(ImageFilter.MinFilter(size=kernel_size))
    if feather_px > 0.0:
        refined = refined.filter(ImageFilter.GaussianBlur(radius=feather_px))
    return refined


def apply_lighting(pil_img: Image.Image, params: Dict[str, Any]) -> Image.Image:
    """
    Applies deterministic brightness, contrast, saturation, sharpness, and warmth adjustments.
    """
    img = pil_img.convert("RGB")
    
    brightness = params.get("brightness", 1.0)
    contrast = params.get("contrast", 1.0)
    saturation = params.get("saturation", 1.0)
    sharpness = params.get("sharpness", 1.0)
    warmth = params.get("warmth", 0)

    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(saturation)
    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
    if warmth != 0:
        arr = np.array(img, dtype=np.int16)
        arr[:, :, 0] += int(warmth)
        arr[:, :, 2] -= int(warmth)
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, mode="RGB")
        
    return img


def composite_backdrop(
    fg_rgb: Image.Image,
    orig_rgb: Image.Image,
    refined_alpha: Image.Image,
    backdrop_mode: str = "Studio White",
    custom_color_rgb: Tuple[int, int, int] = (255, 255, 255)
) -> Image.Image:
    """
    Composites foreground image over selected background mode using refined alpha matte.
    """
    w, h = fg_rgb.size
    
    if backdrop_mode in BACKDROP_COLORS:
        bg_color = BACKDROP_COLORS[backdrop_mode]
        bg_img = Image.new("RGB", (w, h), bg_color)
    elif backdrop_mode == "Soft Blur":
        bg_img = orig_rgb.filter(ImageFilter.GaussianBlur(radius=15))
    elif backdrop_mode in ("Custom Color", "Custom Solid Color..."):
        bg_img = Image.new("RGB", (w, h), custom_color_rgb)
    else:
        bg_img = Image.new("RGB", (w, h), (255, 255, 255))

    return Image.composite(fg_rgb, bg_img, refined_alpha)


def process_image_pipeline(
    full_img: Image.Image,
    roi_box: Optional[Tuple[int, int, int, int]],
    roi_mode: str,
    params: Dict[str, Any],
    seg_engine: Optional[SegmentationEngine] = None
) -> Image.Image:
    """
    Main image processing pipeline:
    - roi_mode:
        - "Whole Image (Ignore Box)" (or "whole")
        - "Edit Inside Box Only (Patch ID / Document)" (or "patch")
        - "Crop to Box (Extract Standalone Photo)" (or "crop")
    - params dictionary containing:
        - remove_bg (bool)
        - ai_model (str: "RMBG-1.4" | "MODNet")
        - backdrop (str)
        - custom_color (Tuple[int, int, int])
        - choke_px (int 0..5)
        - feather_px (float 0.0..5.0)
        - brightness (float 0.5..1.5)
        - contrast (float 0.5..1.5)
        - saturation (float 0.0..2.0)
        - sharpness (float 0.0..3.0)
        - warmth (int -30..30)
        - preset_name (str)
        - custom_w_mm (float)
        - custom_h_mm (float)
    """
    if seg_engine is None:
        seg_engine = GLOBAL_SEGMENTATION_ENGINE

    img = full_img.convert("RGB")
    w, h = img.size

    # Validate and normalize ROI box (x1, y1, x2, y2)
    if roi_box is not None:
        x1, y1, x2, y2 = roi_box
        x1 = max(0, min(int(round(min(x1, x2))), w - 1))
        y1 = max(0, min(int(round(min(y1, y2))), h - 1))
        x2 = max(x1 + 1, min(int(round(max(x1, x2))), w))
        y2 = max(y1 + 1, min(int(round(max(y1, y2))), h))
        roi_box = (x1, y1, x2, y2)
    else:
        roi_box = (0, 0, w, h)

    remove_bg = params.get("remove_bg", False)
    ai_model = params.get("ai_model", "RMBG-1.4")
    backdrop = params.get("backdrop", "Studio White")
    custom_color = params.get("custom_color", (255, 255, 255))
    choke_px = int(params.get("choke_px", 0))
    feather_px = float(params.get("feather_px", 0.0))

    preset_name = params.get("preset_name", "Freeform / Original")
    custom_w_mm = params.get("custom_w_mm", 35.0)
    custom_h_mm = params.get("custom_h_mm", 45.0)

    target_px: Optional[Tuple[int, int]] = None
    if preset_name == "Custom Size (mm)":
        if custom_w_mm and custom_h_mm:
            target_px = (round(custom_w_mm * PX_PER_MM), round(custom_h_mm * PX_PER_MM))
    elif preset_name in PRESET_SIZES:
        _, _, pw, ph = PRESET_SIZES[preset_name]
        if pw and ph:
            target_px = (pw, ph)

    norm_mode = "whole"
    if "Patch" in roi_mode or roi_mode == "patch":
        norm_mode = "patch"
    elif "Crop" in roi_mode or roi_mode == "crop":
        norm_mode = "crop"

    if norm_mode == "patch":
        # Mode 1: Edit Inside Box Only (Patch Document/ID)
        x1, y1, x2, y2 = roi_box
        sub_patch = img.crop((x1, y1, x2, y2))
        lit_patch = apply_lighting(sub_patch, params)

        if remove_bg:
            alpha = seg_engine.get_alpha(sub_patch, ai_model)
            refined_alpha = refine_alpha(alpha, choke_px, feather_px)
            processed_patch = composite_backdrop(lit_patch, sub_patch, refined_alpha, backdrop, custom_color)
        else:
            processed_patch = lit_patch

        result = img.copy()
        result.paste(processed_patch, (x1, y1))
        return result

    elif norm_mode == "crop":
        # Mode 2: Crop to Box (Extract Standalone Photo)
        x1, y1, x2, y2 = roi_box
        cropped = img.crop((x1, y1, x2, y2))
        lit_crop = apply_lighting(cropped, params)

        if remove_bg:
            alpha = seg_engine.get_alpha(cropped, ai_model)
            refined_alpha = refine_alpha(alpha, choke_px, feather_px)
            processed_crop = composite_backdrop(lit_crop, cropped, refined_alpha, backdrop, custom_color)
        else:
            processed_crop = lit_crop

        if target_px is not None:
            processed_crop = ImageOps.fit(processed_crop, target_px, method=Image.LANCZOS)

        return processed_crop

    else:
        # Mode 0: Whole Image
        lit_full = apply_lighting(img, params)

        if remove_bg:
            alpha = seg_engine.get_alpha(img, ai_model)
            refined_alpha = refine_alpha(alpha, choke_px, feather_px)
            result = composite_backdrop(lit_full, img, refined_alpha, backdrop, custom_color)
        else:
            result = lit_full

        if target_px is not None:
            result = ImageOps.fit(result, target_px, method=Image.LANCZOS)

        return result
