"""
print_studio.py - Self-Contained A4 Print Studio Tab for Windows 11 Photo Studio.
Manages 2D shelf bin-packing queue, millimeter page margins/gaps, 1:1 hardware printing, and 300-DPI PNG/PDF export.
"""

from typing import List, Dict, Any, Optional
from PIL import Image

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QMessageBox, QLayout,
)

from canvas import InteractiveCanvas, pil_to_pixmap
import printer
from ui.primitives import (
    AppButton,
    AppLabel,
    FormRow,
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
    SectionBox,
)
from ui.theme import STUDIO_DARK_THEME, ThemeConfig, set_widget_props


class PrintStudioTab(QWidget):
    """Self-contained A4 Print Studio tab component."""

    def __init__(
        self,
        parent=None,
        status_bar_callback=None,
        theme: ThemeConfig = STUDIO_DARK_THEME,
    ):
        super().__init__(parent)
        self.theme = theme
        self.status_bar_callback = status_bar_callback
        self.print_queue: List[Dict[str, Any]] = []
        self._cached_a4_sheet: Optional[Image.Image] = None

        self._setup_ui()

    def _notify(self, message: str, timeout: int = 4000):
        if self.status_bar_callback:
            self.status_bar_callback(message, timeout)

    def _setup_ui(self):
        lt = self.theme.layout
        sp = self.theme.spacing
        print_zone = self.theme.get_zone_config("print-sidebar")
        preview_zone = self.theme.get_zone_config("print-preview")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(sp.md, sp.md, sp.md, sp.md)
        layout.setSpacing(sp.md)

        # Left: Queue & Layout settings in scroll area
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(lt.print_sidebar_range[0])
        left_scroll.setMaximumWidth(lt.print_sidebar_range[1])
        left_scroll.verticalScrollBar().setSingleStep(25)

        left_panel = QWidget()
        set_widget_props(left_panel, repolish=False, zone="print-sidebar")
        left_panel.setMinimumHeight(lt.print_sidebar_min_h)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSizeConstraint(QLayout.SetMinimumSize)
        left_layout.setContentsMargins(*print_zone.margins)
        left_layout.setSpacing(print_zone.spacing)

        # 1. Queue Table Group
        grp_queue = SectionBox(
            "📋 A4 Print Queue",
            section_id="print_queue",
            zone_id="print-sidebar",
            theme=self.theme,
            parent=left_panel,
        )

        self.tbl_queue = QTableWidget(0, 4)
        self.tbl_queue.setHorizontalHeaderLabels(["Preview", "Size (mm)", "Copies", "Action"])
        self.tbl_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_queue.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_queue.setMinimumHeight(lt.print_table_h[0])
        self.tbl_queue.setMaximumHeight(lt.print_table_h[1])
        grp_queue.add_widget(self.tbl_queue)

        self.btn_clear_queue = AppButton(
            "🗑️ Clear Entire Queue",
            variant="default",
            ui_size="md",
            parent=grp_queue,
        )
        self.btn_clear_queue.clicked.connect(self.clear_queue)
        grp_queue.add_widget(self.btn_clear_queue)
        left_layout.addWidget(grp_queue)

        # 2. Page Layout Settings
        grp_layout_settings = SectionBox(
            "📐 A4 Page Layout Settings",
            section_id="print_layout",
            zone_id="print-sidebar",
            theme=self.theme,
            parent=left_panel,
        )

        self.spin_margin = NoWheelDoubleSpinBox()
        self.spin_margin.setRange(0.0, 30.0)
        self.spin_margin.setValue(10.0)
        self.spin_margin.setSingleStep(1.0)
        self.spin_margin.setSuffix(" mm")
        self.spin_margin.valueChanged.connect(self.refresh_preview)
        grp_layout_settings.add_widget(
            FormRow("Page Margin (mm):", self.spin_margin, spacing=sp.md, parent=grp_layout_settings)
        )

        self.spin_gap = NoWheelDoubleSpinBox()
        self.spin_gap.setRange(0.0, 20.0)
        self.spin_gap.setValue(2.0)
        self.spin_gap.setSingleStep(0.5)
        self.spin_gap.setSuffix(" mm")
        self.spin_gap.valueChanged.connect(self.refresh_preview)
        grp_layout_settings.add_widget(
            FormRow("Gap Between Photos (mm):", self.spin_gap, spacing=sp.md, parent=grp_layout_settings)
        )

        self.chk_cut_lines = QCheckBox("Draw Light-Grey Scissor Cut Lines")
        self.chk_cut_lines.setChecked(True)
        self.chk_cut_lines.toggled.connect(self.refresh_preview)
        grp_layout_settings.add_widget(self.chk_cut_lines)

        self.lbl_queue_status = AppLabel(
            "Placed: 0 photos | Overflow: 0 photos",
            role="body",
            tone="accent-bold",
            parent=grp_layout_settings,
        )
        grp_layout_settings.add_widget(self.lbl_queue_status)
        left_layout.addWidget(grp_layout_settings)

        # 3. Hardware Printing & Export
        grp_output = SectionBox(
            "🖨️ Hardware Printing && Export",
            section_id="print_output",
            zone_id="print-sidebar",
            theme=self.theme,
            parent=left_panel,
        )

        self.btn_print_hw = AppButton(
            "🖨️ Print Directly (1:1 Hardware A4)",
            variant="success",
            ui_size="xl",
            parent=grp_output,
        )
        self.btn_print_hw.clicked.connect(self._on_print_hardware)
        grp_output.add_widget(self.btn_print_hw)

        self.btn_export_png = AppButton(
            "💾 Save 300-DPI A4 PNG",
            variant="default",
            ui_size="md",
            parent=grp_output,
        )
        self.btn_export_png.clicked.connect(self._on_export_a4_png)
        grp_output.add_widget(self.btn_export_png)

        self.btn_export_pdf = AppButton(
            "📄 Save 300-DPI A4 PDF",
            variant="default",
            ui_size="md",
            parent=grp_output,
        )
        self.btn_export_pdf.clicked.connect(self._on_export_a4_pdf)
        grp_output.add_widget(self.btn_export_pdf)

        left_layout.addWidget(grp_output)
        left_layout.addSpacing(20)
        left_layout.addStretch()

        left_scroll.setWidget(left_panel)
        layout.addWidget(left_scroll)

        # Right: Live A4 Preview Viewport
        right_panel = QWidget()
        set_widget_props(right_panel, repolish=False, zone="print-preview")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(*preview_zone.margins)

        self.a4_canvas = InteractiveCanvas(
            overlay_tokens=self.theme.canvas,
            badge_font_family=self.theme.typography.font_family_raw,
        )
        right_layout.addWidget(self.a4_canvas)
        layout.addWidget(right_panel, stretch=1)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def add_photo(self, image: Image.Image, width_mm: float, height_mm: float, copies: int = 1, label: str = ""):
        """Adds a photo to the A4 print queue and refreshes preview."""
        entry = {
            "image": image.copy(),
            "width_mm": float(width_mm),
            "height_mm": float(height_mm),
            "copies": int(copies),
            "label": str(label),
        }
        self.print_queue.append(entry)
        self._refresh_queue_table()

    def clear_queue(self):
        """Clears all queued items."""
        self.print_queue.clear()
        self._refresh_queue_table()
        self._notify("Print queue cleared.", 3000)

    def refresh_preview(self):
        """Regenerates the 2D shelf-packed A4 sheet and refreshes viewport."""
        margin_mm = self.spin_margin.value()
        gap_mm = self.spin_gap.value()
        cut_lines = self.chk_cut_lines.isChecked()

        sheet, placed, overflow = printer.generate_a4_sheet(
            queue_items=self.print_queue,
            margin_mm=margin_mm,
            gap_mm=gap_mm,
            draw_cut_lines=cut_lines
        )
        self._cached_a4_sheet = sheet
        self.lbl_queue_status.setText(f"Placed: {placed} photos | Overflow: {overflow} photos")

        self.a4_canvas.set_pixmap(pil_to_pixmap(sheet), keep_roi=False)
        self.a4_canvas.fit_image()

    # -------------------------------------------------------------------------
    # Internal Handlers
    # -------------------------------------------------------------------------

    def _refresh_queue_table(self):
        thumb_px = self.theme.layout.print_thumb_px
        self.tbl_queue.setRowCount(0)
        for i, item in enumerate(self.print_queue):
            self.tbl_queue.insertRow(i)

            # Thumbnail
            thumb = item["image"].copy()
            thumb.thumbnail((thumb_px, thumb_px), Image.BILINEAR)
            lbl_icon = QLabel()
            lbl_icon.setPixmap(pil_to_pixmap(thumb))
            lbl_icon.setAlignment(Qt.AlignCenter)
            self.tbl_queue.setCellWidget(i, 0, lbl_icon)

            # Dimensions
            dim_str = f"{item['width_mm']:.1f} x {item['height_mm']:.1f} mm"
            dim_item = QTableWidgetItem(dim_str)
            dim_item.setTextAlignment(Qt.AlignCenter)
            self.tbl_queue.setItem(i, 1, dim_item)

            # Copies SpinBox
            spin = NoWheelSpinBox()
            spin.setRange(1, 50)
            spin.setValue(item.get("copies", 1))
            spin.valueChanged.connect(lambda val, idx=i: self._on_queue_copies_changed(idx, val))
            self.tbl_queue.setCellWidget(i, 2, spin)

            # Remove Button
            btn_del = AppButton("❌", variant="icon", ui_size="sm")
            btn_del.clicked.connect(lambda _, idx=i: self._on_remove_queue_item(idx))
            self.tbl_queue.setCellWidget(i, 3, btn_del)

        self.refresh_preview()

    def _on_queue_copies_changed(self, idx: int, copies: int):
        if 0 <= idx < len(self.print_queue):
            self.print_queue[idx]["copies"] = copies
            self.refresh_preview()

    def _on_remove_queue_item(self, idx: int):
        if 0 <= idx < len(self.print_queue):
            self.print_queue.pop(idx)
            self._refresh_queue_table()

    def _on_print_hardware(self):
        if self._cached_a4_sheet is None:
            self.refresh_preview()
        if self._cached_a4_sheet is None:
            return

        ok = printer.print_a4_hardware(self, self._cached_a4_sheet)
        if ok:
            self._notify("Print job sent successfully to hardware printer!", 5000)

    def _on_export_a4_png(self):
        if self._cached_a4_sheet is None:
            self.refresh_preview()
        if self._cached_a4_sheet is None:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save A4 Sheet as PNG", "PhotoStudio_A4_300DPI.png",
            "PNG Image (*.png)"
        )
        if filepath:
            try:
                printer.export_a4_png(self._cached_a4_sheet, filepath)
                self._notify(f"Exported A4 PNG: {filepath}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed saving A4 PNG:\n{e}")

    def _on_export_a4_pdf(self):
        if self._cached_a4_sheet is None:
            self.refresh_preview()
        if self._cached_a4_sheet is None:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save A4 Sheet as PDF", "PhotoStudio_A4_300DPI.pdf",
            "PDF Document (*.pdf)"
        )
        if filepath:
            try:
                printer.export_a4_pdf(self._cached_a4_sheet, filepath)
                self._notify(f"Exported A4 PDF: {filepath}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed saving A4 PDF:\n{e}")
