"""
print_studio.py - Self-Contained A4 Print Studio Tab for Windows 11 Photo Studio.
Manages 2D shelf bin-packing queue, millimeter page margins/gaps, 1:1 hardware printing, and 300-DPI PNG/PDF export.
"""

from typing import List, Dict, Any, Optional
from PIL import Image

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QGroupBox, QLabel, QPushButton, QCheckBox, QDoubleSpinBox,
    QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QMessageBox, QLayout
)

from canvas import InteractiveCanvas, pil_to_pixmap
import printer


class PrintStudioTab(QWidget):
    """
    Self-contained A4 Print Studio tab component.
    """

    def __init__(self, parent=None, status_bar_callback=None):
        super().__init__(parent)
        self.status_bar_callback = status_bar_callback
        self.print_queue: List[Dict[str, Any]] = []
        self._cached_a4_sheet: Optional[Image.Image] = None

        self._setup_ui()

    def _notify(self, message: str, timeout: int = 4000):
        if self.status_bar_callback:
            self.status_bar_callback(message, timeout)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Left: Queue & Layout settings in scroll area
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setFixedWidth(380)
        left_scroll.verticalScrollBar().setSingleStep(25)

        left_panel = QWidget()
        left_panel.setMinimumHeight(600)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSizeConstraint(QLayout.SetMinimumSize)
        left_layout.setContentsMargins(4, 4, 14, 8)
        left_layout.setSpacing(6)

        # 1. Queue Table Group
        grp_queue = QGroupBox("📋 A4 Print Queue")
        grp_queue_layout = QVBoxLayout(grp_queue)
        grp_queue_layout.setSpacing(5)

        self.tbl_queue = QTableWidget(0, 4)
        self.tbl_queue.setHorizontalHeaderLabels(["Preview", "Size (mm)", "Copies", "Action"])
        self.tbl_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_queue.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_queue.setMinimumHeight(110)
        self.tbl_queue.setMaximumHeight(160)
        grp_queue_layout.addWidget(self.tbl_queue)

        self.btn_clear_queue = QPushButton("🗑️ Clear Entire Queue")
        self.btn_clear_queue.clicked.connect(self.clear_queue)
        grp_queue_layout.addWidget(self.btn_clear_queue)
        left_layout.addWidget(grp_queue)

        # 2. Page Layout Settings
        grp_layout_settings = QGroupBox("📐 A4 Page Layout Settings")
        grp_settings_layout = QVBoxLayout(grp_layout_settings)
        grp_settings_layout.setSpacing(4)

        margin_row = QHBoxLayout()
        margin_row.addWidget(QLabel("Page Margin (mm):"))
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0.0, 30.0)
        self.spin_margin.setValue(10.0)
        self.spin_margin.setSingleStep(1.0)
        self.spin_margin.setSuffix(" mm")
        self.spin_margin.valueChanged.connect(self.refresh_preview)
        margin_row.addWidget(self.spin_margin)
        grp_settings_layout.addLayout(margin_row)

        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel("Gap Between Photos (mm):"))
        self.spin_gap = QDoubleSpinBox()
        self.spin_gap.setRange(0.0, 20.0)
        self.spin_gap.setValue(2.0)
        self.spin_gap.setSingleStep(0.5)
        self.spin_gap.setSuffix(" mm")
        self.spin_gap.valueChanged.connect(self.refresh_preview)
        gap_row.addWidget(self.spin_gap)
        grp_settings_layout.addLayout(gap_row)

        self.chk_cut_lines = QCheckBox("Draw Light-Grey Scissor Cut Lines")
        self.chk_cut_lines.setChecked(True)
        self.chk_cut_lines.toggled.connect(self.refresh_preview)
        grp_settings_layout.addWidget(self.chk_cut_lines)

        self.lbl_queue_status = QLabel("Placed: 0 photos | Overflow: 0 photos")
        self.lbl_queue_status.setStyleSheet("font-weight: bold; color: #38bdf8;")
        grp_settings_layout.addWidget(self.lbl_queue_status)

        left_layout.addWidget(grp_layout_settings)

        # 3. Hardware Printing & Export
        grp_output = QGroupBox("🖨️ Hardware Printing && Export")
        grp_output_layout = QVBoxLayout(grp_output)
        grp_output_layout.setSpacing(5)

        self.btn_print_hw = QPushButton("🖨️ Print Directly (1:1 Hardware A4)")
        self.btn_print_hw.setObjectName("btn_print_hw")
        self.btn_print_hw.clicked.connect(self._on_print_hardware)
        grp_output_layout.addWidget(self.btn_print_hw)

        self.btn_export_png = QPushButton("💾 Save 300-DPI A4 PNG")
        self.btn_export_png.clicked.connect(self._on_export_a4_png)
        grp_output_layout.addWidget(self.btn_export_png)

        self.btn_export_pdf = QPushButton("📄 Save 300-DPI A4 PDF")
        self.btn_export_pdf.clicked.connect(self._on_export_a4_pdf)
        grp_output_layout.addWidget(self.btn_export_pdf)

        left_layout.addWidget(grp_output)
        left_layout.addSpacing(20)
        left_layout.addStretch()

        left_scroll.setWidget(left_panel)
        layout.addWidget(left_scroll)

        # Right: Live A4 Preview Viewport
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self.a4_canvas = InteractiveCanvas()
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
        self.tbl_queue.setRowCount(0)
        for i, item in enumerate(self.print_queue):
            self.tbl_queue.insertRow(i)

            # Thumbnail
            thumb = item["image"].copy()
            thumb.thumbnail((40, 40), Image.BILINEAR)
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
            spin = QSpinBox()
            spin.setRange(1, 50)
            spin.setValue(item.get("copies", 1))
            spin.valueChanged.connect(lambda val, idx=i: self._on_queue_copies_changed(idx, val))
            self.tbl_queue.setCellWidget(i, 2, spin)

            # Remove Button
            btn_del = QPushButton("❌")
            btn_del.setFixedWidth(30)
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
