"""
main.py - Native Windows 11 ARM64 Photo Studio & A4 Print Studio.
Pure PySide6 desktop application with 100% offline ONNX inference and 1:1 hardware printing.
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QImage, QPixmap, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QFileDialog, QColorDialog, QMessageBox,
    QFrame, QScrollArea,
)
from PIL import Image

import engine
import rescaler
import transforms
from canvas import InteractiveCanvas, pil_to_pixmap
from print_studio import PrintStudioTab
from ui.panels import (
    AiBackgroundPanel,
    CanvasToolbar,
    CropStraightenPanel,
    LightingPanel,
    RescalePanel,
    WorkspacePanel,
)
from ui.primitives import AppButton
from ui.theme import STUDIO_DARK_THEME, ThemeConfig, build_stylesheet, set_widget_props
from workspace import PhotoWorkspace, RetouchState, CropState


PRESET_MAP = {
    "Freeform / Original": None,
    "Standard Passport (35 x 45 mm)": (35.0, 45.0),
    "Indian Passport / US Visa (2 x 2 in)": (50.8, 50.8),
    "PAN / ID Portrait (25 x 35 mm)": (25.0, 35.0),
    "Indian Stamp Size (20 x 25 mm)": (20.0, 25.0),
    "Standard ID Card (85.6 x 54 mm)": (85.6, 54.0),
    "Custom Size": None,
}


class SuperResWorker(QThread):
    """Background worker for non-blocking neural super-resolution inference."""
    finished = Signal(object)  # Emits enhanced PIL.Image
    error = Signal(str)

    def __init__(self, img: Image.Image):
        super().__init__()
        self.img = img

    def run(self):
        try:
            enhanced = rescaler.GLOBAL_SUPERRES_ENGINE.enhance_2x(self.img)
            self.finished.emit(enhanced)
        except Exception as e:
            self.error.emit(str(e))


class PhotoStudioApp(QMainWindow):
    """Main window composing Photo Studio panels and the A4 Print Studio tab."""

    def __init__(self, theme: ThemeConfig = STUDIO_DARK_THEME):
        super().__init__()
        self.theme = theme
        self.setWindowTitle("Native Windows ARM64 Photo Studio & Print Engine")
        self.resize(*self.theme.layout.window_default_size)
        self.setMinimumSize(*self.theme.layout.window_min_size)

        # In-memory isolated per-photo workspaces
        self.workspace_photos: List[PhotoWorkspace] = []
        self.current_photo_idx: int = -1
        self._next_photo_id: int = 0
        self._block_signals: bool = False

        self._setup_ui()
        self._setup_shortcuts()
        self._apply_theme()
        self.statusBar().showMessage("Ready - 100% Offline Native Windows ARM64 Studio")

    def _setup_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 1: Photo Studio
        self.tab_studio = QWidget()
        self._build_studio_tab(self.tab_studio)
        self.tabs.addTab(self.tab_studio, "📸 Photo Studio")

        # Tab 2: A4 Print Studio
        self.tab_printer = PrintStudioTab(status_bar_callback=self.statusBar().showMessage)
        self.tabs.addTab(self.tab_printer, "🖨️ A4 Print Studio")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _build_studio_tab(self, parent_widget: QWidget):
        lt = self.theme.layout
        sp = self.theme.spacing

        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(sp.md, sp.md, sp.md, sp.md)
        layout.setSpacing(sp.md)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 1. Left Panel (Workspace & Crop/Straighten)
        left_zone = self.theme.get_zone_config("sidebar-left")
        left_panel = QWidget()
        set_widget_props(left_panel, repolish=False, zone="sidebar-left")
        left_panel.setMinimumWidth(lt.left_panel_range[0])
        left_panel.setMaximumWidth(lt.left_panel_range[1])
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(*left_zone.margins)
        left_layout.setSpacing(left_zone.spacing)

        self.workspace_panel = WorkspacePanel(theme=self.theme, parent=left_panel)
        self.workspace_panel.openFilesRequested.connect(self._on_open_files)
        self.workspace_panel.pasteRequested.connect(self._on_paste_clipboard)
        self.workspace_panel.photoSelected.connect(self._on_photo_selected)
        self.workspace_panel.removeRequested.connect(self._on_remove_photo)
        left_layout.addWidget(self.workspace_panel)

        self.crop_panel = CropStraightenPanel(
            preset_map=PRESET_MAP,
            px_per_mm=engine.PX_PER_MM,
            theme=self.theme,
            parent=left_panel,
        )
        self.crop_panel.modeChanged.connect(self._on_crop_mode_toggled)
        self.crop_panel.presetChanged.connect(self._on_preset_changed)
        self.crop_panel.unitChanged.connect(self._on_unit_changed)
        self.crop_panel.dimensionsChanged.connect(self._on_dimensions_changed)
        self.crop_panel.applyCropRequested.connect(self._on_apply_crop)
        self.crop_panel.resetPinsRequested.connect(self._on_reset_perspective_pins)
        self.crop_panel.applyExtractRequested.connect(self._on_apply_extract)
        left_layout.addWidget(self.crop_panel)
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # 2. Center Panel (Top Toolbar + Interactive Canvas)
        center_zone = self.theme.get_zone_config("center")
        center_panel = QWidget()
        set_widget_props(center_panel, repolish=False, zone="center")
        center_panel.setMinimumWidth(lt.center_panel_min_w)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(*center_zone.margins)
        center_layout.setSpacing(center_zone.spacing)

        self.toolbar = CanvasToolbar(theme=self.theme, parent=center_panel)
        self.toolbar.zoomInRequested.connect(lambda: self.canvas.zoom(1.2))
        self.toolbar.zoomOutRequested.connect(lambda: self.canvas.zoom(1 / 1.2))
        self.toolbar.fitRequested.connect(lambda: self.canvas.fit_image())
        self.toolbar.rotateRequested.connect(self._on_rotate_90)
        self.toolbar.resetRoiRequested.connect(self._on_reset_roi)
        self.toolbar.undoRequested.connect(self._on_undo)
        self.toolbar.revertRequested.connect(self._on_revert_to_original)
        self.toolbar.comparePressed.connect(self._on_compare_pressed)
        self.toolbar.compareReleased.connect(self._on_compare_released)
        self.toolbar.sendToPrintRequested.connect(self._on_send_to_print_queue)
        center_layout.addWidget(self.toolbar)

        self.canvas = InteractiveCanvas(
            overlay_tokens=self.theme.canvas,
            badge_font_family=self.theme.typography.font_family_raw,
        )
        self.canvas.roiChanged.connect(self._on_canvas_roi_changed)
        self.canvas.quadChanged.connect(self._on_canvas_quad_changed)
        self.canvas.filesDropped.connect(self._load_image_paths)
        center_layout.addWidget(self.canvas)

        splitter.addWidget(center_panel)

        # 3. Right Panel (AI Segmentation, Lighting, Resolution & Save)
        right_zone = self.theme.get_zone_config("inspector-right")
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setMinimumWidth(lt.right_panel_range[0])
        right_scroll.setMaximumWidth(lt.right_panel_range[1])

        right_panel = QWidget()
        set_widget_props(right_panel, repolish=False, zone="inspector-right")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(*right_zone.margins)
        right_layout.setSpacing(right_zone.spacing)

        self.ai_panel = AiBackgroundPanel(theme=self.theme, parent=right_panel)
        self.ai_panel.settingsChanged.connect(self._trigger_render)
        self.ai_panel.pickCustomColorRequested.connect(self._on_pick_custom_color)
        right_layout.addWidget(self.ai_panel)

        self.lighting_panel = LightingPanel(theme=self.theme, parent=right_panel)
        self.lighting_panel.lightingChanged.connect(self._trigger_render)
        self.lighting_panel.editInsideBoxToggled.connect(self._on_edit_inside_box_toggled)
        self.lighting_panel.resetRequested.connect(self._on_reset_lighting)
        self.lighting_panel.commitRequested.connect(self._on_bake_edit)
        right_layout.addWidget(self.lighting_panel)

        self.rescale_panel = RescalePanel(
            min_scale_pct=rescaler.MIN_SCALE_PCT,
            max_scale_pct=rescaler.MAX_SCALE_PCT,
            theme=self.theme,
            parent=right_panel,
        )
        self.rescale_panel.scalePercentageChanged.connect(self._on_rescale_pct_changed)
        self.rescale_panel.applyScaleRequested.connect(self._on_apply_rescale)
        self.rescale_panel.aiEnhanceRequested.connect(self._on_ai_enhance_clicked)
        right_layout.addWidget(self.rescale_panel)

        self.btn_save_photo = AppButton(
            "💾 Save Single Photo (PNG/JPG)",
            variant="default",
            ui_size="md",
            parent=right_panel,
        )
        self.btn_save_photo.clicked.connect(self._on_save_single_photo)
        right_layout.addWidget(self.btn_save_photo)

        right_layout.addStretch()
        right_scroll.setWidget(right_panel)
        splitter.addWidget(right_scroll)

        # Configure splitter behavior: fixed side panes, center expands
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes(list(lt.splitter_sizes))

    def _setup_shortcuts(self):
        paste_shortcut = QShortcut(QKeySequence.Paste, self)
        paste_shortcut.activated.connect(self._on_paste_clipboard)

        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)

    def _apply_theme(self):
        self.setStyleSheet(build_stylesheet(self.theme))

    # -------------------------------------------------------------------------
    # Workspace & Photo Management
    # -------------------------------------------------------------------------

    def _make_thumbnail_pixmap(self, img: Image.Image) -> QPixmap:
        px = self.theme.layout.workspace_thumb_px
        thumb = img.copy()
        thumb.thumbnail((px, px), Image.BILINEAR)
        return pil_to_pixmap(thumb)

    def _on_open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Open Image(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*.*)"
        )
        if files:
            self._load_image_paths(files)

    def _load_image_paths(self, paths: List[str]):
        new_indices = []
        for p in paths:
            try:
                img = Image.open(p).convert("RGB")
                filename = Path(p).name
                idx = self._add_photo_to_workspace(img, filename)
                new_indices.append(idx)
            except Exception as e:
                QMessageBox.warning(self, "Load Error", f"Could not load image:\n{p}\n\nError: {e}")

        if new_indices:
            self.workspace_panel.set_current_row(new_indices[-1])

    def _on_paste_clipboard(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if clipboard.image() and not clipboard.image().isNull():
            qimg = clipboard.image()
            buffer = qimg.convertToFormat(QImage.Format_RGB888)
            ptr = buffer.constBits()
            img = Image.frombuffer("RGB", (qimg.width(), qimg.height()), ptr, "raw", "RGB", 0, 1)
            idx = self._add_photo_to_workspace(img, f"Pasted_Photo_{len(self.workspace_photos) + 1}")
            self.workspace_panel.set_current_row(idx)
            self.statusBar().showMessage("Pasted image from clipboard", 3000)
            return

        if mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.toLocalFile()]
            if paths:
                self._load_image_paths(paths)

    def _current_workspace(self) -> Optional[PhotoWorkspace]:
        """Returns the active PhotoWorkspace, or None if no photo is selected."""
        if 0 <= self.current_photo_idx < len(self.workspace_photos):
            return self.workspace_photos[self.current_photo_idx]
        return None

    def _refresh_thumbnail(self, row: int, img: Image.Image) -> None:
        """Updates the workspace list icon for the given row."""
        self.workspace_panel.update_thumbnail(row, self._make_thumbnail_pixmap(img))

    def _add_photo_to_workspace(self, img: Image.Image, name: str) -> int:
        idx = len(self.workspace_photos)
        ws = PhotoWorkspace.create(self._next_photo_id, img, name)
        self._next_photo_id += 1
        self.workspace_photos.append(ws)
        self.workspace_panel.add_photo_item(self._make_thumbnail_pixmap(img), name)
        return idx

    def _on_remove_photo(self):
        row = self.workspace_panel.current_row()
        if 0 <= row < len(self.workspace_photos):
            # Invalidate current_photo_idx and suppress intermediate signals while mutating
            # QListWidget so the remaining item is always hydrated cleanly without leaking state.
            self.current_photo_idx = -1
            self.workspace_photos.pop(row)
            self.workspace_panel.remove_row(row)

            if self.workspace_photos:
                self._on_photo_selected(self.workspace_panel.current_row())
            else:
                self._reset_controls_to_defaults()
                self.canvas.set_pixmap(QPixmap())
                self._update_rescale_ui()
                self.toolbar.set_undo_enabled(False)
                self.crop_panel.set_extract_enabled(False)

    def _sync_ui_to_workspace(self, ws: PhotoWorkspace) -> None:
        """Persists live UI control values and canvas overlays into the given workspace."""
        ws.retouch = self._collect_retouch_state()
        ws.crop.crop_mode = self.canvas.crop_mode
        ws.crop.preset_name = self.crop_panel.preset_name()
        ws.crop.unit = self.crop_panel.current_unit()
        ws.crop.dim_w_mm, ws.crop.dim_h_mm = self.crop_panel.dimensions_mm()
        ws.crop.apply_size = self.crop_panel.apply_size_checked()
        ws.crop.rescale_pct = self.rescale_panel.scale_pct()
        if self.canvas.crop_mode == "perspective":
            ws.crop.quad = self.canvas.get_perspective_quad()
        else:
            ws.crop.roi = self.canvas.get_roi_box()

    def _load_retouch_to_ui(self, retouch: RetouchState) -> None:
        """Applies a RetouchState to AI and Lighting panels."""
        self.ai_panel.load_values(
            remove_bg=retouch.remove_bg,
            ai_model=retouch.ai_model,
            backdrop=retouch.backdrop,
            custom_color=retouch.custom_color,
            choke_px=retouch.choke_px,
            feather_px=retouch.feather_px,
        )
        self.lighting_panel.load_values(
            brightness=retouch.brightness,
            contrast=retouch.contrast,
            saturation=retouch.saturation,
            sharpness=retouch.sharpness,
            warmth=retouch.warmth,
            edit_inside_box=retouch.edit_inside_box,
        )

    def _load_crop_to_ui(self, crop: CropState, restore_pixmap: Optional[Image.Image] = None) -> None:
        """Applies a CropState to Crop/Straighten controls and canvas overlays."""
        self.crop_panel.load_crop_state(
            crop_mode=crop.crop_mode,
            preset_name=crop.preset_name,
            unit=crop.unit,
            dim_w_mm=crop.dim_w_mm,
            dim_h_mm=crop.dim_h_mm,
            apply_size=crop.apply_size,
        )
        self.rescale_panel.set_scale_pct(crop.rescale_pct, block_signals=True)

        if crop.preset_name == "Freeform / Original" or crop.dim_h_mm <= 0:
            self.canvas.set_aspect_ratio(None)
        else:
            self.canvas.set_aspect_ratio(crop.dim_w_mm / crop.dim_h_mm)

        if restore_pixmap is not None:
            # Keep crop_mode temporarily standard so set_pixmap does not spawn a throwaway quad
            self.canvas.crop_mode = "standard"
            self.canvas.set_pixmap(pil_to_pixmap(restore_pixmap), keep_roi=False)

        self.canvas.crop_mode = crop.crop_mode

        if crop.crop_mode == "perspective":
            if crop.quad:
                self.canvas.set_perspective_quad(crop.quad)
            elif self.canvas.pixmap_item and not self.canvas.quad_item:
                self.canvas.spawn_centered_quad()
        else:
            self.canvas.set_roi_box(crop.roi)

        self._update_crop_button_state()

    def _load_workspace_to_ui(self, ws: PhotoWorkspace) -> None:
        """Hydrates all studio UI panels and canvas overlays from a PhotoWorkspace."""
        self._block_signals = True
        try:
            self._load_retouch_to_ui(ws.retouch)
            self._load_crop_to_ui(ws.crop, restore_pixmap=ws.baked)
        finally:
            self._block_signals = False

    def _reset_controls_to_defaults(self) -> None:
        """Resets UI controls to fresh neutral defaults when workspace is empty."""
        self._block_signals = True
        try:
            self._load_retouch_to_ui(RetouchState())
            self._load_crop_to_ui(CropState(), restore_pixmap=None)
        finally:
            self._block_signals = False

    def _on_photo_selected(self, row: int):
        if 0 <= self.current_photo_idx < len(self.workspace_photos) and self.current_photo_idx != row:
            self._sync_ui_to_workspace(self.workspace_photos[self.current_photo_idx])

        if row < 0 or row >= len(self.workspace_photos):
            self.current_photo_idx = -1
            self._update_rescale_ui()
            self.crop_panel.set_extract_enabled(False)
            return

        self.current_photo_idx = row
        ws = self.workspace_photos[row]

        self._load_workspace_to_ui(ws)

        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.toolbar.set_undo_enabled(ws.has_undo())
        self.crop_panel.set_extract_enabled(True)

    def _on_undo(self):
        """Reverts the last crop, rotation, rescale, or commit operation for the current photo."""
        ws = self._current_workspace()
        if ws is None:
            return
        snapshot = ws.pop_undo()
        if snapshot is None:
            self.statusBar().showMessage("Nothing to undo for this photo.", 3000)
            self.toolbar.set_undo_enabled(False)
            return

        self._block_signals = True
        try:
            self._load_crop_to_ui(ws.crop, restore_pixmap=ws.baked)
        finally:
            self._block_signals = False

        self._refresh_thumbnail(self.current_photo_idx, ws.baked)
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.statusBar().showMessage(f"↩️ Undid: {snapshot.desc}", 4000)
        self.toolbar.set_undo_enabled(ws.has_undo())

    def _on_revert_to_original(self):
        """Restores the current photo back to its pristine, unedited initial state."""
        ws = self._current_workspace()
        if ws is None:
            return

        ws.revert_to_initial()
        self._load_workspace_to_ui(ws)

        self._refresh_thumbnail(self.current_photo_idx, ws.baked)
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.toolbar.set_undo_enabled(ws.has_undo())
        self.statusBar().showMessage("⏮️ Reverted photo to initial unedited state.", 5000)

    def _on_bake_edit(self):
        ws = self._current_workspace()
        if ws is None:
            return
        if ws.commit_retouch():
            self._block_signals = True
            try:
                self.canvas.set_roi_box(None)
                self._load_retouch_to_ui(ws.retouch)
                self._update_crop_button_state()
            finally:
                self._block_signals = False

            self._refresh_thumbnail(self.current_photo_idx, ws.baked)
            self._trigger_render()
            self._update_rescale_ui()
            self.toolbar.set_undo_enabled(ws.has_undo())
            self.statusBar().showMessage("✔️ Committed edits into base image and reset retouch controls.", 4000)

    # -------------------------------------------------------------------------
    # Resolution & Scaling Handlers (rescaler.py)
    # -------------------------------------------------------------------------

    def _on_rescale_pct_changed(self, pct: int):
        """Calculates live target pixel readout and validates against safety ceiling."""
        ws = self._current_workspace()
        if ws is None:
            self.rescale_panel.lbl_target_res.setText("Result: No photo selected")
            return
        orig_w, orig_h = ws.baked.size
        target_w, target_h = rescaler.calculate_target_dimensions(orig_w, orig_h, pct)
        within_limits = rescaler.is_within_safe_limits(target_w, target_h)
        self.rescale_panel.update_target_preview(
            target_w, target_h, within_limits, rescaler.MAX_SAFE_IMAGE_DIM
        )

    def _update_rescale_ui(self):
        """Refreshes the resolution readout and target calculation for active photo."""
        ws = self._current_workspace()
        if ws is not None:
            w, h = ws.baked.size
            self.rescale_panel.set_current_resolution(w, h)
            self._on_rescale_pct_changed(self.rescale_panel.scale_pct())

            if not rescaler.GLOBAL_SUPERRES_ENGINE.is_available():
                self.rescale_panel.set_ai_status(
                    False, "Super-resolution model not downloaded (check models/superres)"
                )
            elif max(w, h) > rescaler.MAX_AI_INPUT_DIM:
                self.rescale_panel.set_ai_status(
                    False, f"Image is already high resolution (>{rescaler.MAX_AI_INPUT_DIM}px)"
                )
            else:
                self.rescale_panel.set_ai_status(
                    True, "Reconstruct sharp details using 2x neural super-resolution"
                )
        else:
            self.rescale_panel.show_no_photo()

    def _on_apply_rescale(self, pct: Optional[int] = None):
        """Executes compute-based rescaling and registers snapshot to undo history."""
        ws = self._current_workspace()
        if ws is None:
            return
        pct = self.rescale_panel.scale_pct() if pct is None else pct
        if pct == 100:
            self.statusBar().showMessage("Scale is 100% (no changes applied).", 3000)
            return

        try:
            self._sync_ui_to_workspace(ws)
            ws.push_undo(f"Scale to {pct}%")

            scaled_img, (new_w, new_h) = rescaler.rescale_image(ws.baked, pct)
            ws.baked = scaled_img
            ws.orig = scaled_img
            ws.crop.roi = None
            ws.crop.quad = None
            ws.crop.rescale_pct = 100

            self._refresh_thumbnail(self.current_photo_idx, scaled_img)
            self.rescale_panel.set_scale_pct(100, block_signals=True)

            self.canvas.set_pixmap(pil_to_pixmap(scaled_img), keep_roi=False)
            self._trigger_render()
            self.canvas.fit_image()
            self._update_rescale_ui()
            self._update_crop_button_state()
            self.toolbar.set_undo_enabled(True)
            self.statusBar().showMessage(f"⚡ Rescaled to {pct}% ({new_w} x {new_h} px). Undo with Ctrl+Z.", 5000)

        except ValueError as e:
            QMessageBox.warning(self, "Scale Limit Exceeded", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Rescaling Error", f"Failed to rescale image:\n{e}")

    def _on_ai_enhance_clicked(self):
        """Launches non-blocking AI super-resolution in background thread."""
        ws = self._current_workspace()
        if ws is None:
            return

        w, h = ws.baked.size
        if max(w, h) > rescaler.MAX_AI_INPUT_DIM:
            QMessageBox.information(
                self, "Resolution Sufficient",
                f"Image is already {w}x{h} px. AI enhancement is designed for photos under {rescaler.MAX_AI_INPUT_DIM}px."
            )
            return

        self.rescale_panel.set_busy(True)
        self.statusBar().showMessage("🤖 Running AI Super-Resolution (2x)... Please wait.")

        self._ai_worker = SuperResWorker(ws.baked.copy())
        self._ai_worker.finished.connect(self._on_ai_enhance_finished)
        self._ai_worker.error.connect(self._on_ai_enhance_error)
        self._ai_worker.start()

    def _on_ai_enhance_finished(self, enhanced_img: Image.Image):
        """Callback when AI enhance completes successfully."""
        ws = self._current_workspace()
        if ws is None:
            return

        self._sync_ui_to_workspace(ws)
        ws.push_undo("AI Super-Resolution (2x)")

        ws.baked = enhanced_img
        ws.orig = enhanced_img
        ws.crop.roi = None
        ws.crop.quad = None

        self._refresh_thumbnail(self.current_photo_idx, enhanced_img)

        self.canvas.set_pixmap(pil_to_pixmap(enhanced_img), keep_roi=False)
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self._update_crop_button_state()
        self.toolbar.set_undo_enabled(True)

        w, h = enhanced_img.size
        self.statusBar().showMessage(f"✨ AI Super-Resolution complete! New size: {w} x {h} px. Undo with Ctrl+Z.", 5000)

    def _on_ai_enhance_error(self, err_msg: str):
        """Callback if AI inference fails."""
        self._update_rescale_ui()
        self.statusBar().showMessage("AI enhancement failed.", 4000)
        QMessageBox.warning(self, "AI Enhance Failed", f"Could not enhance image:\n{err_msg}")

    # -------------------------------------------------------------------------
    # Canvas Actions & Geometry
    # -------------------------------------------------------------------------

    def _on_canvas_roi_changed(self, box):
        if self._block_signals:
            return
        ws = self._current_workspace()
        if ws is not None:
            ws.crop.roi = box
        self._update_crop_button_state()
        self._trigger_render()

    def _on_canvas_quad_changed(self, points):
        if self._block_signals:
            return
        ws = self._current_workspace()
        if ws is not None and self.canvas.crop_mode == "perspective":
            ws.crop.quad = list(points)

    def _on_reset_roi(self):
        ws = self._current_workspace()
        if self.canvas.crop_mode == "perspective":
            self.canvas.reset_perspective_quad()
            if ws is not None:
                ws.crop.quad = self.canvas.get_perspective_quad()
            self.statusBar().showMessage("Reset 4 perspective pins to center.", 3000)
        else:
            self.canvas.set_roi_box(None)
            if ws is not None:
                ws.crop.roi = None
            self._update_crop_button_state()
            self._trigger_render()

    def _update_crop_button_state(self):
        """Updates Apply Crop button availability based on active photo, preset, and ROI box."""
        if self._current_workspace() is None:
            self.crop_panel.set_apply_crop_enabled(False)
        elif self.crop_panel.preset_name() == "Freeform / Original":
            self.crop_panel.set_apply_crop_enabled(self.canvas.get_roi_box() is not None)
        else:
            self.crop_panel.set_apply_crop_enabled(True)

    def _switch_to_crop_mode(self, auto_spawn_box: bool = True):
        """Activates standard Crop UI and canvas mode."""
        self.crop_panel.set_mode_containers("standard")
        self.canvas.set_crop_mode("standard")

        preset = self.crop_panel.preset_name()
        if preset == "Freeform / Original":
            self.canvas.set_aspect_ratio(None)
        else:
            w_mm, h_mm = self.crop_panel.dimensions_mm()
            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if auto_spawn_box and not self.canvas.get_roi_box() and self.current_photo_idx >= 0:
                self.canvas.spawn_centered_box(aspect_ratio=aspect)
        self._update_crop_button_state()

    def _on_crop_mode_toggled(self, mode: str):
        ws = self._current_workspace()
        if mode == "perspective":
            self.crop_panel.set_mode_containers("perspective")
            self.canvas.set_crop_mode("perspective")
            if ws is not None:
                ws.crop.crop_mode = "perspective"
                ws.crop.quad = self.canvas.get_perspective_quad()
            self.crop_panel.set_extract_enabled(self.current_photo_idx >= 0)
            self.statusBar().showMessage("Straighten mode: Drag the 4 corner pins (amber TOP = Width).", 4000)
        else:
            self._switch_to_crop_mode(auto_spawn_box=True)
            if ws is not None:
                ws.crop.crop_mode = "standard"
            self.statusBar().showMessage("Crop mode active.", 3000)

    def _on_reset_perspective_pins(self):
        if self.canvas.crop_mode == "perspective":
            self.canvas.reset_perspective_quad()
            ws = self._current_workspace()
            if ws is not None:
                ws.crop.quad = self.canvas.get_perspective_quad()
            self.statusBar().showMessage("Reset 4 perspective pins to center.", 3000)

    def _finalize_geometry_edit(self, ws: PhotoWorkspace):
        """Refreshes workspace thumbnail, clears canvas overlays, re-renders, and updates rescale UI."""
        self._refresh_thumbnail(self.current_photo_idx, ws.baked)

        self._block_signals = True
        try:
            self.canvas.set_perspective_quad(None)
            self.canvas.set_roi_box(None)
            ws.crop.roi = None
            ws.crop.quad = None
            self._update_crop_button_state()
        finally:
            self._block_signals = False

        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.toolbar.set_undo_enabled(ws.has_undo())

    def _on_apply_extract(self):
        ws = self._current_workspace()
        if ws is None:
            QMessageBox.information(self, "No Photo", "Please add or select a photo first.")
            return

        quad = self.canvas.get_perspective_quad()
        if not quad or len(quad) != 4:
            QMessageBox.warning(self, "Invalid Selection", "Please position the 4 corner pins around the card or document.")
            return

        target_px = None
        w_mm = None
        h_mm = None

        if self.crop_panel.apply_size_checked():
            target_px, w_mm, h_mm = self.crop_panel.target_dimensions_px_and_mm()
            if not target_px:
                QMessageBox.warning(self, "Invalid Size", "Width and Height must be greater than zero.")
                return

        w_nat, h_nat = transforms.calculate_natural_quad_dimensions(quad)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._sync_ui_to_workspace(ws)
            desc = (
                f"Extract & Fit ({target_px[0]}x{target_px[1]} px)"
                if target_px else
                f"Straighten & Extract ({w_nat}x{h_nat} px)"
            )
            ws.push_undo(desc)
            ws.baked = engine.extract_perspective_quad(ws.baked, quad, target_size=target_px)
            ws.orig = engine.extract_perspective_quad(ws.orig, quad, target_size=target_px)
            ws.target_w_mm = w_mm if target_px else None
            ws.target_h_mm = h_mm if target_px else None
            ws.crop.roi = None
            ws.crop.quad = None

            self._finalize_geometry_edit(ws)

            self._switch_to_crop_mode(auto_spawn_box=False)
            ws.crop.crop_mode = "standard"

            if target_px:
                msg = f"🪄 Extracted & fitted to {ws.baked.width} x {ws.baked.height} px ({w_mm:.1f} x {h_mm:.1f} mm)"
            else:
                msg = f"🪄 Extracted & straightened to {ws.baked.width} x {ws.baked.height} px (natural)"
            self.statusBar().showMessage(msg, 6000)
        except Exception as e:
            QMessageBox.critical(self, "Extraction Error", f"Failed to straighten and extract image:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _on_rotate_90(self):
        ws = self._current_workspace()
        if ws is None:
            return
        self._sync_ui_to_workspace(ws)
        ws.push_undo("Rotate 90°")
        ws.baked = ws.baked.rotate(-90, expand=True)
        ws.crop.roi = None
        ws.crop.quad = None
        self._refresh_thumbnail(self.current_photo_idx, ws.baked)
        self.canvas.set_pixmap(pil_to_pixmap(ws.baked), keep_roi=False)
        self._update_crop_button_state()
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.toolbar.set_undo_enabled(ws.has_undo())

    def _on_compare_pressed(self):
        ws = self._current_workspace()
        if ws is not None:
            self.canvas.set_pixmap(pil_to_pixmap(ws.orig), keep_roi=False)

    def _on_compare_released(self):
        ws = self._current_workspace()
        if ws is not None and ws.processed:
            self.canvas.set_pixmap(pil_to_pixmap(ws.processed), keep_roi=True)

    # -------------------------------------------------------------------------
    # Presets, Units, Dimensions & Box Scope Handlers
    # -------------------------------------------------------------------------

    def _on_unit_changed(self, new_unit: str):
        if self._block_signals:
            return
        ws = self._current_workspace()
        if ws is not None:
            ws.crop.unit = new_unit

    def _on_preset_changed(self, text: str):
        if self._block_signals:
            return

        ws = self._current_workspace()
        dims_mm = PRESET_MAP.get(text)
        if dims_mm is not None:
            w_mm, h_mm = dims_mm
            if ws is not None:
                ws.crop.preset_name = text
                ws.crop.dim_w_mm = w_mm
                ws.crop.dim_h_mm = h_mm

            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)
            self._update_crop_button_state()
            self.statusBar().showMessage(
                f"Preset loaded: {text} ({w_mm:.1f} x {h_mm:.1f} mm). Frame with box, then click Apply Crop.",
                5000
            )
        elif text == "Freeform / Original":
            if ws is not None:
                ws.crop.preset_name = text
            self.canvas.set_aspect_ratio(None)
            self._update_crop_button_state()
            self.statusBar().showMessage("Freeform: Drag any box freely or leave full image.", 3000)
        elif text == "Custom Size":
            if ws is not None:
                ws.crop.preset_name = text
            w_mm, h_mm = self.crop_panel.dimensions_mm()
            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)
            self._update_crop_button_state()

    def _on_dimensions_changed(self, w_mm: float, h_mm: float):
        if self._block_signals:
            return

        ws = self._current_workspace()
        if ws is not None:
            ws.crop.dim_w_mm = w_mm
            ws.crop.dim_h_mm = h_mm
            ws.crop.preset_name = "Custom Size"

        if self.canvas.crop_mode != "standard":
            return

        self._update_crop_button_state()
        if w_mm > 0 and h_mm > 0:
            aspect = w_mm / h_mm
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)

    def _on_edit_inside_box_toggled(self, checked: bool):
        if self._block_signals:
            return

        if checked:
            if self.canvas.crop_mode == "perspective":
                self._block_signals = True
                try:
                    self._switch_to_crop_mode(auto_spawn_box=False)
                finally:
                    self._block_signals = False
                ws = self._current_workspace()
                if ws is not None:
                    ws.crop.crop_mode = "standard"
                self.statusBar().showMessage("Switched to Crop mode for boxed retouching.", 4000)

            if not self.canvas.get_roi_box():
                if self.canvas.spawn_centered_box(aspect_ratio=None) is not None:
                    return
            self._update_crop_button_state()
            self._trigger_render()
        else:
            self.canvas.set_roi_box(None)
            ws = self._current_workspace()
            if ws is not None:
                ws.crop.roi = None
            self._update_crop_button_state()
            self._trigger_render()

    def _on_apply_crop(self):
        ws = self._current_workspace()
        if ws is None:
            QMessageBox.information(self, "No Photo", "Please add or select a photo first.")
            return

        roi_box = self.canvas.get_roi_box()
        if not roi_box:
            w, h = ws.baked.size
            roi_box = (0, 0, w, h)

        preset = self.crop_panel.preset_name()
        target_px = None
        w_mm = 0.0
        h_mm = 0.0
        if preset != "Freeform / Original":
            target_px, w_mm, h_mm = self.crop_panel.target_dimensions_px_and_mm()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._sync_ui_to_workspace(ws)
            desc = f"Crop to {w_mm:.1f}x{h_mm:.1f} mm" if target_px else "Crop to Selection"
            ws.push_undo(desc)
            ws.baked = engine.crop_and_resize(ws.baked, roi_box, target_px)
            ws.orig = engine.crop_and_resize(ws.orig, roi_box, target_px)
            ws.target_w_mm = w_mm if target_px else None
            ws.target_h_mm = h_mm if target_px else None
            ws.crop.roi = None

            self._finalize_geometry_edit(ws)

            dim_text = f" ({w_mm:.1f} x {h_mm:.1f} mm)" if target_px else ""
            self.statusBar().showMessage(
                f"✂️ Cropped photo to {ws.baked.width} x {ws.baked.height} px{dim_text} with zero distortion",
                5000
            )
        except Exception as e:
            QMessageBox.critical(self, "Crop Error", f"Failed to crop image:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _on_pick_custom_color(self):
        curr = self.ai_panel.custom_color()
        qcolor = QColorDialog.getColor(QColor(*curr), self, "Select Backdrop Color")
        if qcolor.isValid():
            rgb = (qcolor.red(), qcolor.green(), qcolor.blue())
            self.ai_panel.set_custom_color(rgb)
            ws = self._current_workspace()
            if ws is not None:
                ws.retouch.custom_color = rgb
            self._trigger_render()

    def _on_reset_lighting(self):
        self.lighting_panel.reset_sliders()
        ws = self._current_workspace()
        if ws is not None:
            ws.retouch.reset_lighting()
        self._trigger_render()

    def _collect_retouch_state(self) -> RetouchState:
        """Reads current AI, lighting, and box-scope controls into a RetouchState."""
        merged: Dict[str, Any] = {}
        merged.update(self.ai_panel.values())
        merged.update(self.lighting_panel.values())
        return RetouchState(**merged)

    # -------------------------------------------------------------------------
    # Core Synchronous Rendering Pipeline
    # -------------------------------------------------------------------------

    def _trigger_render(self):
        if self._block_signals:
            return
        ws = self._current_workspace()
        if ws is None:
            return

        retouch = self._collect_retouch_state()
        ws.retouch = retouch
        w_mm, h_mm = self.crop_panel.dimensions_mm()
        params = retouch.to_engine_params(self.crop_panel.preset_name(), w_mm, h_mm)
        roi_box = self.canvas.get_roi_box()
        mode_str = "patch" if retouch.edit_inside_box else "whole"

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = engine.process_image_pipeline(
                full_img=ws.baked,
                roi_box=roi_box,
                roi_mode=mode_str,
                params=params,
                seg_engine=engine.GLOBAL_SEGMENTATION_ENGINE
            )
            ws.processed = result
            if self.canvas.crop_mode == "standard":
                ws.crop.roi = roi_box

            self.canvas.set_pixmap(pil_to_pixmap(result), keep_roi=True)
        except Exception as e:
            self.statusBar().showMessage(f"Processing Error: {e}", 5000)
        finally:
            QApplication.restoreOverrideCursor()

    # -------------------------------------------------------------------------
    # Save & Queue Actions
    # -------------------------------------------------------------------------

    def _on_save_single_photo(self):
        ws = self._current_workspace()
        if ws is None:
            return
        proc = ws.processed
        if not proc:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Processed Photo", "photo_studio_export.png",
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*.*)"
        )
        if filepath:
            try:
                proc.save(filepath, dpi=(engine.DPI, engine.DPI))
                self.statusBar().showMessage(f"Saved: {filepath}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed saving image:\n{e}")

    def _on_send_to_print_queue(self):
        ws = self._current_workspace()
        if ws is None:
            QMessageBox.information(self, "No Photo", "Please select a photo to send to print queue.")
            return
        proc = ws.processed if ws.processed else ws.baked

        if ws.target_w_mm and ws.target_h_mm:
            w_mm = ws.target_w_mm
            h_mm = ws.target_h_mm
        else:
            preset = self.crop_panel.preset_name()
            dims_mm = PRESET_MAP.get(preset)
            if dims_mm is not None:
                w_mm, h_mm = dims_mm
            else:
                w_mm, h_mm = self.crop_panel.dimensions_mm()
                if preset == "Freeform / Original":
                    w_mm = round(proc.width / engine.PX_PER_MM, 1)
                    h_mm = round(proc.height / engine.PX_PER_MM, 1)

        self.tab_printer.add_photo(proc, w_mm, h_mm, copies=4, label=ws.name)
        self.statusBar().showMessage(f"Added to A4 Queue: {ws.name} ({w_mm:.1f} x {h_mm:.1f} mm)", 4000)

    # -------------------------------------------------------------------------
    # A4 Print Studio Handlers
    # -------------------------------------------------------------------------

    def _on_tab_changed(self, idx: int):
        if idx == 1:
            self.tab_printer.refresh_preview()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PhotoStudioNative")

    window = PhotoStudioApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
