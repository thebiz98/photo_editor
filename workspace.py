"""
workspace.py - Isolated Per-Photo Workspace State & Undo History Management.
Encapsulates retouch parameters, crop/straighten settings, and undo snapshots
for each photo in the studio workspace so state never leaks across photos.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image


MAX_UNDO_HISTORY = 25


@dataclass
class RetouchState:
    """Per-photo AI background removal, lighting/color grading, and retouch scope state."""
    remove_bg: bool = False
    ai_model: str = "RMBG-1.4"
    backdrop: str = "Studio White"
    custom_color: Tuple[int, int, int] = (255, 255, 255)
    choke_px: int = 0
    feather_px: float = 0.0
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 1.0
    warmth: int = 0
    edit_inside_box: bool = False

    def reset_lighting(self) -> None:
        """Resets only the lighting and color grading sliders to neutral defaults."""
        self.brightness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.sharpness = 1.0
        self.warmth = 0

    def reset(self) -> None:
        """Resets all retouch controls (lighting, AI background removal, and box scope) to defaults."""
        self.remove_bg = False
        self.ai_model = "RMBG-1.4"
        self.backdrop = "Studio White"
        self.custom_color = (255, 255, 255)
        self.choke_px = 0
        self.feather_px = 0.0
        self.reset_lighting()
        self.edit_inside_box = False

    def to_engine_params(self, preset_name: str, custom_w_mm: float, custom_h_mm: float) -> Dict[str, Any]:
        """Builds the parameter dictionary expected by engine.process_image_pipeline."""
        return {
            "remove_bg": self.remove_bg,
            "ai_model": self.ai_model,
            "backdrop": self.backdrop,
            "custom_color": self.custom_color,
            "choke_px": self.choke_px,
            "feather_px": self.feather_px,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "sharpness": self.sharpness,
            "warmth": self.warmth,
            "preset_name": preset_name,
            "custom_w_mm": custom_w_mm,
            "custom_h_mm": custom_h_mm,
        }


@dataclass
class CropState:
    """Per-photo Crop & Straighten configuration and active canvas overlays."""
    crop_mode: str = "standard"  # "standard" or "perspective"
    preset_name: str = "Freeform / Original"
    unit: str = "mm"
    dim_w_mm: float = 35.0
    dim_h_mm: float = 45.0
    apply_size: bool = False
    roi: Optional[Tuple[int, int, int, int]] = None
    quad: Optional[List[Tuple[float, float]]] = None
    rescale_pct: int = 100


@dataclass
class UndoSnapshot:
    """Immutable point-in-time snapshot for per-photo undo operations."""
    baked: Image.Image
    orig: Image.Image
    roi: Optional[Tuple[int, int, int, int]]
    quad: Optional[List[Tuple[float, float]]]
    target_w_mm: Optional[float]
    target_h_mm: Optional[float]
    dim_w_mm: float
    dim_h_mm: float
    current_unit: str
    preset: str
    crop_mode: str
    apply_size: bool
    desc: str


@dataclass
class PhotoWorkspace:
    """Complete isolated workspace state for a single photo in the studio."""
    id: int
    name: str
    orig_initial: Image.Image
    orig: Image.Image
    baked: Image.Image
    processed: Image.Image
    target_w_mm: Optional[float] = None
    target_h_mm: Optional[float] = None
    retouch: RetouchState = field(default_factory=RetouchState)
    crop: CropState = field(default_factory=CropState)
    history: List[UndoSnapshot] = field(default_factory=list)

    @classmethod
    def create(cls, photo_id: int, img: Image.Image, name: str) -> "PhotoWorkspace":
        """Creates a new isolated photo workspace with clean default retouch and crop settings."""
        return cls(
            id=photo_id,
            name=name,
            orig_initial=img.copy(),
            orig=img.copy(),
            baked=img.copy(),
            processed=img.copy(),
        )

    def has_undo(self) -> bool:
        """Returns True if at least one undo snapshot is available."""
        return len(self.history) > 0

    def push_undo(self, desc: str) -> None:
        """Records a snapshot of the current baked image and crop state."""
        quad_copy = list(self.crop.quad) if self.crop.quad is not None else None
        snapshot = UndoSnapshot(
            baked=self.baked.copy(),
            orig=self.orig.copy(),
            roi=self.crop.roi,
            quad=quad_copy,
            target_w_mm=self.target_w_mm,
            target_h_mm=self.target_h_mm,
            dim_w_mm=self.crop.dim_w_mm,
            dim_h_mm=self.crop.dim_h_mm,
            current_unit=self.crop.unit,
            preset=self.crop.preset_name,
            crop_mode=self.crop.crop_mode,
            apply_size=self.crop.apply_size,
            desc=desc,
        )
        self.history.append(snapshot)
        if len(self.history) > MAX_UNDO_HISTORY:
            self.history.pop(0)

    def pop_undo(self) -> Optional[UndoSnapshot]:
        """Pops and restores the most recent undo snapshot, returning it if available."""
        if not self.history:
            return None
        snapshot = self.history.pop()
        self.baked = snapshot.baked
        self.orig = snapshot.orig
        self.crop.roi = snapshot.roi
        self.crop.quad = list(snapshot.quad) if snapshot.quad is not None else None
        self.target_w_mm = snapshot.target_w_mm
        self.target_h_mm = snapshot.target_h_mm
        self.crop.dim_w_mm = snapshot.dim_w_mm
        self.crop.dim_h_mm = snapshot.dim_h_mm
        self.crop.unit = snapshot.current_unit
        self.crop.preset_name = snapshot.preset
        self.crop.crop_mode = snapshot.crop_mode
        self.crop.apply_size = snapshot.apply_size
        return snapshot

    def commit_retouch(self) -> bool:
        """Bakes current processed image into baked base and resets all retouch controls."""
        if self.processed is None:
            return False
        self.push_undo("Commit Edits")
        self.baked = self.processed.copy()
        self.crop.roi = None
        self.retouch.reset()
        return True

    def revert_to_initial(self) -> None:
        """Restores the workspace back to its pristine initial image and neutral controls."""
        orig_init = self.orig_initial if self.orig_initial is not None else self.orig
        self.push_undo("Revert to Original")
        self.baked = orig_init.copy()
        self.orig = orig_init.copy()
        self.target_w_mm = None
        self.target_h_mm = None
        self.retouch.reset()
        self.crop.roi = None
        self.crop.quad = None
        self.crop.preset_name = "Freeform / Original"
        self.crop.crop_mode = "standard"
        self.crop.rescale_pct = 100
