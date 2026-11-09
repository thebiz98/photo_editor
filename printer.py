# printer.py - A4 Sheet Smart Auto-Grid Packing Engine (300 DPI)

from PIL import Image, ImageDraw

# Standard A4 dimensions in inches (210mm x 297mm)
A4_WIDTH_IN = 8.27
A4_HEIGHT_IN = 11.69

def build_a4_sheet(
    queue_items: list,
    table_rows: list,
    dpi: int = 300,
    margin_mm: float = 8.0,
    gap_mm: float = 3.0,
    draw_cut_borders: bool = True
):
    """
    Packs requested copies of each queued image onto a 300-DPI A4 sheet using shelf bin-packing.
    Returns (a4_pil_image, status_summary_string).
    """
    sheet_w = int(round(A4_WIDTH_IN * dpi))
    sheet_h = int(round(A4_HEIGHT_IN * dpi))
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#FFFFFF")
    draw = ImageDraw.Draw(sheet)

    if not queue_items:
        return sheet, "⚪ Print queue is empty. Add edited photos from Tab 1 first."

    margin_px = int(round((margin_mm / 25.4) * dpi))
    gap_px = int(round((gap_mm / 25.4) * dpi))

    cursor_x = margin_px
    cursor_y = margin_px
    current_row_max_h = 0
    placed_count = 0
    overflow_count = 0

    # Sync user edits from the dataframe (Copies, Width in, Height in)
    for idx, item in enumerate(queue_items):
        copies = item["copies"]
        w_in = item["w_in"]
        h_in = item["h_in"]

        if idx < len(table_rows):
            try:
                row = table_rows[idx]
                w_in = float(row[2])
                h_in = float(row[3])
                copies = int(float(row[4]))
            except (ValueError, IndexError, TypeError):
                pass

        if copies <= 0:
            continue

        target_w_px = max(20, int(round(w_in * dpi)))
        target_h_px = max(20, int(round(h_in * dpi)))

        # Resize tile to exact physical print size at sheet DPI
        tile = item["image"].convert("RGB").resize((target_w_px, target_h_px), Image.LANCZOS)

        for _ in range(copies):
            # Wrap to next row if tile exceeds right printable margin
            if cursor_x + target_w_px > sheet_w - margin_px:
                cursor_x = margin_px
                cursor_y += current_row_max_h + gap_px
                current_row_max_h = 0

            # Check if tile exceeds bottom printable margin
            if cursor_y + target_h_px > sheet_h - margin_px:
                overflow_count += 1
                continue

            sheet.paste(tile, (cursor_x, cursor_y))

            if draw_cut_borders:
                draw.rectangle(
                    [cursor_x, cursor_y, cursor_x + target_w_px - 1, cursor_y + target_h_px - 1],
                    outline="#9CA3AF",
                    width=2
                )

            cursor_x += target_w_px + gap_px
            current_row_max_h = max(current_row_max_h, target_h_px)
            placed_count += 1

    status = f"✅ Packed **{placed_count}** photo copies onto A4 sheet ({sheet_w}×{sheet_h} px @ {dpi} DPI)."
    if overflow_count > 0:
        status += f" ⚠️ **{overflow_count}** copies did not fit on a single A4 page."

    return sheet, status