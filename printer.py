"""
printer.py - A4 2D Shelf Bin-Packing & 1:1 Physical Hardware Printing Engine.
Guarantees exact millimeter scale output without printer driver auto-scaling distortions.
"""

from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtGui import QPainter, QPageSize, QPageLayout, QImage
from PySide6.QtCore import QMarginsF

# Constants for A4 at 300 DPI
DPI = 300
PX_PER_MM = 300.0 / 25.4  # ~11.8110236
A4_W_PX = 2480  # 210 mm @ 300 DPI
A4_H_PX = 3508  # 297 mm @ 300 DPI


def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Converts a PIL Image to a PySide6 QImage safely."""
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    return qimg.copy()


def generate_a4_sheet(
    queue_items: List[Dict[str, Any]],
    margin_mm: float = 10.0,
    gap_mm: float = 2.0,
    draw_cut_lines: bool = True
) -> Tuple[Image.Image, int, int]:
    """
    Arranges multiple photos on an A4 sheet (2480x3508 @ 300 DPI) using 2D shelf bin-packing.
    
    Each item in queue_items:
    {
        "image": PIL.Image,
        "width_mm": float,
        "height_mm": float,
        "copies": int,
        "label": str (optional)
    }

    Returns:
    (canvas_pil, placed_count, overflow_count)
    """
    canvas = Image.new("RGB", (A4_W_PX, A4_H_PX), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    margin_px = round(margin_mm * PX_PER_MM)
    gap_px = round(gap_mm * PX_PER_MM)

    cursor_x = margin_px
    cursor_y = margin_px
    shelf_height = 0

    placed_count = 0
    overflow_count = 0

    for item in queue_items:
        src_img = item["image"]
        w_mm = float(item.get("width_mm", 35.0))
        h_mm = float(item.get("height_mm", 45.0))
        copies = int(item.get("copies", 1))

        w_px = max(10, round(w_mm * PX_PER_MM))
        h_px = max(10, round(h_mm * PX_PER_MM))

        # High-quality resize to exact physical target dimensions
        resized_item = src_img.convert("RGB").resize((w_px, h_px), Image.LANCZOS)

        for _ in range(copies):
            # Check horizontal boundary
            if cursor_x + w_px > A4_W_PX - margin_px:
                # Wrap to next row
                cursor_x = margin_px
                cursor_y += shelf_height + gap_px
                shelf_height = 0

            # Check vertical boundary
            if cursor_y + h_px > A4_H_PX - margin_px:
                overflow_count += 1
                continue

            # Paste item onto canvas
            canvas.paste(resized_item, (cursor_x, cursor_y))

            # Optional cutting guide border
            if draw_cut_lines:
                draw.rectangle(
                    [cursor_x, cursor_y, cursor_x + w_px - 1, cursor_y + h_px - 1],
                    outline=(200, 200, 200),
                    width=1
                )

            placed_count += 1
            cursor_x += w_px + gap_px
            shelf_height = max(shelf_height, h_px)

    return canvas, placed_count, overflow_count


def print_a4_hardware(parent_widget, a4_pil_image: Image.Image) -> bool:
    """
    Sends the 300 DPI A4 image directly to Windows hardware printer using native QPrinter.
    Configures full-page 0mm margin layout so printer driver does not shrink 35x45mm photos.
    """
    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageOrientation(QPageLayout.Portrait)
    printer.setFullPage(True)
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)

    dialog = QPrintDialog(printer, parent_widget)
    if dialog.exec() == QPrintDialog.Accepted:
        qimg = pil_to_qimage(a4_pil_image)
        painter = QPainter(printer)
        target_rect = painter.viewport()
        painter.drawImage(target_rect, qimg, qimg.rect())
        painter.end()
        return True
    return False


def export_a4_png(a4_pil_image: Image.Image, filepath: str) -> None:
    """Exports 300 DPI A4 image to PNG with embedded DPI metadata."""
    a4_pil_image.save(filepath, "PNG", dpi=(DPI, DPI))


def export_a4_pdf(a4_pil_image: Image.Image, filepath: str) -> None:
    """Exports 300 DPI A4 image directly to PDF at 300 DPI resolution."""
    a4_pil_image.save(filepath, "PDF", resolution=float(DPI))
