# engine.py - ONNX Segmentation & Deterministic Pillow Image Processing

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageEnhance, ImageFilter
from huggingface_hub import hf_hub_download

MODELS = {
    "MODNet (Portrait Specialist)": {
        "repo": "Xenova/modnet",
        "file": "onnx/model.onnx",
        "type": "modnet"
    },
    "RMBG-1.4 (General Objects)": {
        "repo": "briaai/RMBG-1.4",
        "file": "onnx/model.onnx",
        "type": "rmbg"
    }
}

LoadedSessions = {}

def get_session(model_choice: str):
    if model_choice not in LoadedSessions:
        cfg = MODELS[model_choice]
        print(f"Loading {cfg['repo']}...")
        model_path = hf_hub_download(repo_id=cfg["repo"], filename=cfg["file"])
        avail = ort.get_available_providers()
        providers = [p for p in ["QNNExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"] if p in avail]
        LoadedSessions[model_choice] = ort.InferenceSession(model_path, providers=providers)
    return LoadedSessions[model_choice], MODELS[model_choice]["type"]

def extract_alpha_mask(pil_img: Image.Image, model_choice: str) -> Image.Image:
    session, m_type = get_session(model_choice)
    orig_w, orig_h = pil_img.size

    if m_type == "modnet":
        ref_size = 512
        if max(orig_w, orig_h) < ref_size or min(orig_w, orig_h) > ref_size:
            if orig_w >= orig_h:
                im_rh = ref_size
                im_rw = int(orig_w / orig_h * ref_size)
            else:
                im_rw = ref_size
                im_rh = int(orig_h / orig_w * ref_size)
        else:
            im_rw, im_rh = orig_w, orig_h
        
        im_rw -= (im_rw % 32)
        im_rh -= (im_rh % 32)

        im_resized = pil_img.resize((im_rw, im_rh), Image.BILINEAR)
        im_np = (np.array(im_resized, dtype=np.float32) / 255.0 - 0.5) / 0.5
        im_tensor = np.transpose(im_np, (2, 0, 1))[np.newaxis, :, :, :]

        input_name = session.get_inputs()[0].name
        result = session.run(None, {input_name: im_tensor})[0]
        mask = np.squeeze(result)
    else:
        im_resized = pil_img.resize((1024, 1024), Image.BILINEAR)
        im_np = (np.array(im_resized, dtype=np.float32) / 255.0) - 0.5
        im_tensor = np.transpose(im_np, (2, 0, 1))[np.newaxis, :, :, :]

        input_name = session.get_inputs()[0].name
        result = session.run(None, {input_name: im_tensor})[0]
        mask = np.squeeze(result)
        mask = (mask - mask.min()) / (mask.max() - mask.min() + 1e-8)

    mask_pil = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8), mode="L")
    return mask_pil.resize((orig_w, orig_h), Image.BILINEAR)

def adjust_warmth(img: Image.Image, warmth: float) -> Image.Image:
    if warmth == 0.0:
        return img
    arr = np.array(img, dtype=np.float32)
    arr[:, :, 0] = np.clip(arr[:, :, 0] + warmth * 25, 0, 255)
    arr[:, :, 2] = np.clip(arr[:, :, 2] - warmth * 25, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), mode="RGB")

def apply_lighting(img: Image.Image, brightness, contrast, saturation, sharpness, warmth) -> Image.Image:
    out = img.copy()
    if brightness != 1.0:
        out = ImageEnhance.Brightness(out).enhance(brightness)
    if contrast != 1.0:
        out = ImageEnhance.Contrast(out).enhance(contrast)
    if saturation != 1.0:
        out = ImageEnhance.Color(out).enhance(saturation)
    if sharpness != 1.0:
        out = ImageEnhance.Sharpness(out).enhance(sharpness)
    if warmth != 0.0:
        out = adjust_warmth(out, warmth)
    return out

def apply_manual_brush_to_mask(base_mask: Image.Image, editor_data: dict) -> Image.Image:
    if base_mask is None or not editor_data or not editor_data.get("layers"):
        return base_mask

    mask_np = np.array(base_mask, dtype=np.float32)
    w, h = base_mask.size

    for layer in editor_data["layers"]:
        if layer is None:
            continue
        layer_rgba = layer.convert("RGBA").resize((w, h), Image.NEAREST)
        l_np = np.array(layer_rgba, dtype=np.float32)
        stroke_alpha = l_np[:, :, 3] / 255.0
        stroke_luma = 0.299 * l_np[:, :, 0] + 0.587 * l_np[:, :, 1] + 0.114 * l_np[:, :, 2]
        target_val = np.where(stroke_luma > 128, 255.0, 0.0)
        mask_np = mask_np * (1.0 - stroke_alpha) + target_val * stroke_alpha

    return Image.fromarray(np.clip(mask_np, 0, 255).astype(np.uint8), mode="L")

def get_target_dimensions(crop_mode: str, width_in: float, height_in: float):
    """Returns (aspect_ratio, width_inches, height_inches)."""
    preset_ratios = {
        "Original": (None, 1.5, 2.0),
        "1:1 Square": (1.0, 2.0, 2.0),
        "3:4 Passport Ratio": (3.0 / 4.0, 1.5, 2.0),
        "4:5 Portrait": (4.0 / 5.0, 1.6, 2.0),
        "Indian Passport / ID (1.5 x 2.0 in)": (1.5 / 2.0, 1.5, 2.0),
        "Indian Stamp Size (0.8 x 1.0 in)": (0.8 / 1.0, 0.8, 1.0),
        "US Visa (2.0 x 2.0 in)": (1.0, 2.0, 2.0),
        "Custom Inches (Specify Below)": (
            max(0.2, width_in) / max(0.2, height_in),
            max(0.2, width_in),
            max(0.2, height_in)
        )
    }
    return preset_ratios.get(crop_mode, (None, width_in, height_in))

def crop_and_resize_physical(img: Image.Image, crop_mode: str, width_in: float, height_in: float, dpi: int) -> Image.Image:
    if img is None or crop_mode == "Original":
        return img

    target_ratio, target_w_in, target_h_in = get_target_dimensions(crop_mode, width_in, height_in)
    w, h = img.size

    if (w / h) > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        cropped = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        cropped = img.crop((0, top, w, top + new_h))

    if crop_mode in ["Indian Passport / ID (1.5 x 2.0 in)", "Indian Stamp Size (0.8 x 1.0 in)", "US Visa (2.0 x 2.0 in)", "Custom Inches (Specify Below)"] and dpi > 0:
        px_w = int(round(target_w_in * dpi))
        px_h = int(round(target_h_in * dpi))
        cropped = cropped.resize((px_w, px_h), Image.LANCZOS)

    return cropped

def process_image(
    original_img: Image.Image,
    cached_mask: Image.Image,
    brush_data: dict,
    lighting_scope: str,
    bg_mode: str,
    custom_color: str,
    custom_bg_img: Image.Image,
    blur_strength: int,
    mask_threshold: float,
    feather_radius: float,
    brightness: float,
    contrast: float,
    saturation: float,
    sharpness: float,
    warmth: float,
    crop_mode: str,
    width_in: float,
    height_in: float,
    dpi: int
):
    if original_img is None:
        return None

    lit_img = apply_lighting(original_img, brightness, contrast, saturation, sharpness, warmth)

    if cached_mask is None or (bg_mode == "Original (No Cutout)" and lighting_scope == "Whole Image"):
        return crop_and_resize_physical(lit_img, crop_mode, width_in, height_in, dpi)

    mask_np = np.array(cached_mask, dtype=np.float32) / 255.0
    if mask_threshold != 0.0:
        mask_np = np.clip((mask_np - mask_threshold) / (1.0 - abs(mask_threshold) + 1e-5), 0.0, 1.0)
    working_mask = Image.fromarray((mask_np * 255).astype(np.uint8), mode="L")
    working_mask = apply_manual_brush_to_mask(working_mask, brush_data)

    if feather_radius > 0:
        working_mask = working_mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))

    base_for_bg = lit_img if lighting_scope == "Whole Image" else original_img
    w, h = original_img.size

    if bg_mode == "Original (No Cutout)":
        composite = Image.composite(lit_img, base_for_bg, working_mask)
    elif bg_mode == "Transparent PNG":
        composite = lit_img.convert("RGBA")
        composite.putalpha(working_mask)
    elif bg_mode == "View Raw Mask (Debug)":
        composite = working_mask.convert("RGB")
    else:
        if bg_mode == "White Studio":
            bg = Image.new("RGB", (w, h), "#FFFFFF")
        elif bg_mode == "Passport Grey":
            bg = Image.new("RGB", (w, h), "#E5E7EB")
        elif bg_mode == "Corporate Navy":
            bg = Image.new("RGB", (w, h), "#1E293B")
        elif bg_mode == "Custom Solid Color":
            bg = Image.new("RGB", (w, h), custom_color)
        elif bg_mode == "Blur Background":
            bg = base_for_bg.filter(ImageFilter.GaussianBlur(radius=blur_strength))
        elif bg_mode == "Custom Image" and custom_bg_img is not None:
            bg = custom_bg_img.convert("RGB").resize((w, h), Image.LANCZOS)
        else:
            bg = base_for_bg

        composite = Image.composite(lit_img, bg, working_mask)

    return crop_and_resize_physical(composite, crop_mode, width_in, height_in, dpi)