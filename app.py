# app.py - Main Entry Point (Editor Workspace + A4 Print Studio)

import tempfile
import gradio as gr
from styles import STUDIO_CSS, PRINT_A4_JS
from engine import (
    MODELS, extract_alpha_mask, process_image, get_target_dimensions
)
from printer import build_a4_sheet

with gr.Blocks(title="Local Photo & Print Studio", theme=gr.themes.Default(spacing_size="sm", radius_size="sm"), css=STUDIO_CSS) as app:
    # Shared Session State
    orig_state = gr.State(None)
    mask_state = gr.State(None)
    print_queue_state = gr.State([])  # List of dicts: {id, name, image, w_in, h_in, copies}

    with gr.Tabs() as main_tabs:
        # ====================================================
        # PAGE 1: PHOTO EDITOR WORKSPACE
        # ====================================================
        with gr.TabItem("📸 1. Photo Editor", id="editor_tab"):
            with gr.Row(elem_classes=["workspace-row"]):
                
                # --- LEFT PANE: UPLOAD & AI TRIGGER ---
                with gr.Column(elem_classes=["left-col"]):
                    input_img = gr.Image(type="pil", label="1. Input Photo", sources=["upload", "webcam"], height=210)
                    
                    with gr.Group():
                        model_selector = gr.Dropdown(
                            choices=list(MODELS.keys()),
                            value=list(MODELS.keys())[0],
                            label="AI Cutout Engine"
                        )
                        segment_btn = gr.Button("✨ Extract Subject / BG", variant="primary", size="sm")
                        mask_status = gr.Markdown("⚪ *Standard Mode (No AI)*")

                    with gr.Group():
                        copies_to_add = gr.Number(value=4, minimum=1, maximum=40, step=1, label="Copies for Print Queue")
                        add_to_print_btn = gr.Button("➕ Add to A4 Print Queue", variant="primary", size="sm")
                        queue_badge = gr.Markdown("🖨️ *Queue: 0 photos*")

                    reset_btn = gr.Button("🔄 Reset Edits", variant="secondary", size="sm")

                # --- CENTER PANE: PINNED LIVE PREVIEW ---
                with gr.Column(elem_classes=["center-col"]):
                    output_img = gr.Image(type="pil", label="Live Preview", format="png", interactive=False, height=620)

                # --- RIGHT PANE: PINNED SCROLLABLE CONTROLS ---
                with gr.Column(elem_classes=["right-col"]):
                    with gr.Tabs():
                        with gr.TabItem("☀️ Light"):
                            lighting_scope = gr.Radio(
                                choices=["Whole Image", "Subject Only (Requires Cutout)"],
                                value="Whole Image",
                                label="Apply Adjustments To"
                            )
                            brightness = gr.Slider(0.5, 1.8, value=1.0, step=0.02, label="Brightness")
                            contrast = gr.Slider(0.5, 1.8, value=1.0, step=0.02, label="Contrast")
                            saturation = gr.Slider(0.0, 2.0, value=1.0, step=0.05, label="Saturation")
                            warmth = gr.Slider(-1.0, 1.0, value=0.0, step=0.05, label="Warmth")
                            sharpness = gr.Slider(0.5, 2.5, value=1.0, step=0.1, label="Sharpness")

                        with gr.TabItem("🎨 BG"):
                            bg_mode = gr.Radio(
                                choices=[
                                    "Original (No Cutout)",
                                    "White Studio",
                                    "Passport Grey",
                                    "Corporate Navy",
                                    "Blur Background",
                                    "Custom Solid Color",
                                    "Custom Image",
                                    "Transparent PNG",
                                    "View Raw Mask (Debug)"
                                ],
                                value="Original (No Cutout)",
                                label="Backdrop Mode"
                            )
                            custom_color = gr.ColorPicker(value="#DBEAFE", label="Custom Solid Color")
                            blur_strength = gr.Slider(5, 50, value=20, step=1, label="Blur Strength")
                            custom_bg_img = gr.Image(type="pil", label="Custom Backdrop Photo", height=95)

                        with gr.TabItem("✂️ Size"):
                            crop_mode = gr.Dropdown(
                                choices=[
                                    "Original",
                                    "Indian Passport / ID (1.5 x 2.0 in)",
                                    "Indian Stamp Size (0.8 x 1.0 in)",
                                    "US Visa (2.0 x 2.0 in)",
                                    "1:1 Square",
                                    "3:4 Passport Ratio",
                                    "4:5 Portrait",
                                    "Custom Inches (Specify Below)"
                                ],
                                value="Indian Passport / ID (1.5 x 2.0 in)",
                                label="Crop & Print Size Preset"
                            )
                            with gr.Row():
                                width_in = gr.Number(value=1.5, minimum=0.4, maximum=8.0, step=0.1, label="Width (in)")
                                height_in = gr.Number(value=2.0, minimum=0.4, maximum=11.0, step=0.1, label="Height (in)")
                            dpi_input = gr.Number(value=300, minimum=72, maximum=600, step=50, label="Print DPI")

                        with gr.TabItem("🖌️ Fix"):
                            mask_threshold = gr.Slider(-0.4, 0.7, value=0.0, step=0.05, label="Auto-Mask Tightness")
                            feather_radius = gr.Slider(0.0, 5.0, value=1.0, step=0.2, label="Edge Feathering")
                            gr.Markdown("Black = Erase BG | White = Restore")
                            brush_editor = gr.ImageEditor(
                                type="pil",
                                label="Manual Brush Override",
                                brush=gr.Brush(colors=["#000000", "#FFFFFF"], default_color="#000000", default_size=25),
                                eraser=gr.Eraser(default_size=25),
                                height=250
                            )

        # ====================================================
        # PAGE 2: A4 PRINT & MULTI-COPY LAYOUT STUDIO
        # ====================================================
        with gr.TabItem("🖨️ 2. A4 Print Studio", id="print_tab"):
            with gr.Row(elem_classes=["workspace-row"]):
                
                # --- LEFT PANE: QUEUE GALLERY & COPY CONTROLS (Scale 4) ---
                with gr.Column(scale=4):
                    gr.Markdown("### 1. Working Pictures & Copy Counts")
                    queue_gallery = gr.Gallery(label="Pictures in Print Queue", columns=4, height=160, object_fit="contain")
                    
                    gr.Markdown("*Double-click any cell in **Width (in)**, **Height (in)**, or **Copies** below to change it, then click **Update A4 Preview**.*")
                    queue_table = gr.Dataframe(
                        headers=["#", "Picture", "Width (in)", "Height (in)", "Copies"],
                        datatype=["number", "str", "number", "number", "number"],
                        interactive=True,
                        col_count=(5, "fixed")
                    )

                    with gr.Row():
                        margin_mm = gr.Slider(0, 20, value=8, step=1, label="Page Margin (mm)")
                        gap_mm = gr.Slider(0, 15, value=3, step=0.5, label="Photo Spacing (mm)")
                        cut_lines = gr.Checkbox(value=True, label="Draw Scissor Cut Lines")

                    with gr.Row():
                        preview_a4_btn = gr.Button("🔄 Update A4 Sheet Preview", variant="primary")
                        clear_queue_btn = gr.Button("🗑️ Clear Queue", variant="secondary")

                    print_status = gr.Markdown("⚪ *Add edited photos from Tab 1 to build your A4 sheet.*")

                    with gr.Row():
                        print_now_btn = gr.Button("🖨️ Open Print Dialog (A4)", variant="primary")
                        download_a4_file = gr.DownloadButton("💾 Download 300-DPI A4 PNG", variant="secondary")

                # --- RIGHT PANE: LIVE A4 CANVAS PREVIEW (Scale 6) ---
                with gr.Column(scale=6):
                    a4_preview_img = gr.Image(
                        type="pil",
                        label="A4 Sheet Preview (210mm × 297mm @ 300 DPI)",
                        elem_id="a4-preview-box",
                        interactive=False,
                        height=630
                    )

    # ====================================================
    # EVENT WIRING
    # ====================================================
    edit_params = [
        orig_state, mask_state, brush_editor, lighting_scope, bg_mode,
        custom_color, custom_bg_img, blur_strength, mask_threshold, feather_radius,
        brightness, contrast, saturation, sharpness, warmth,
        crop_mode, width_in, height_in, dpi_input
    ]

    # Auto-sync Width/Height number boxes when user selects a preset crop size
    def sync_crop_dimensions(mode, cur_w, cur_h):
        _, w_in, h_in = get_target_dimensions(mode, cur_w, cur_h)
        return w_in, h_in

    crop_mode.change(fn=sync_crop_dimensions, inputs=[crop_mode, width_in, height_in], outputs=[width_in, height_in])

    # 1. Image Upload (Untouched fast load)
    def on_upload(img, *current_settings):
        if img is None:
            return None, None, None, "⚪ *Standard Mode (No AI)*", "Original (No Cutout)", "Whole Image", None
        rgb_img = img.convert("RGB")
        editor_init = {"background": rgb_img, "layers": [], "composite": rgb_img}
        settings_list = list(current_settings)
        settings_list[0] = None
        settings_list[1] = "Whole Image"
        settings_list[2] = "Original (No Cutout)"
        preview = process_image(rgb_img, None, *settings_list)
        return (
            rgb_img, None, editor_init,
            "⚪ *Standard Mode (Click Extract for BG)*",
            "Original (No Cutout)", "Whole Image", preview
        )

    input_img.change(
        fn=on_upload,
        inputs=[input_img] + edit_params[2:],
        outputs=[orig_state, mask_state, brush_editor, mask_status, bg_mode, lighting_scope, output_img]
    )

    # 2. On-Demand AI Subject Extraction
    def on_extract_click(orig_img, model_choice, *current_settings):
        if orig_img is None:
            return None, "⚠️ *Upload a photo first.*", "Original (No Cutout)", "Whole Image", None
        mask = extract_alpha_mask(orig_img, model_choice)
        settings_list = list(current_settings)
        new_bg_mode = "White Studio" if settings_list[2] == "Original (No Cutout)" else settings_list[2]
        new_scope = "Subject Only (Requires Cutout)"
        settings_list[1] = new_scope
        settings_list[2] = new_bg_mode
        preview = process_image(orig_img, mask, *settings_list)
        return mask, f"🟢 *Cutout Active ({model_choice.split()[0]})*", new_bg_mode, new_scope, preview

    segment_btn.click(
        fn=on_extract_click,
        inputs=[orig_state, model_selector] + edit_params[2:],
        outputs=[mask_state, mask_status, bg_mode, lighting_scope, output_img]
    )

    # 3. Live Sliders
    for ctrl in edit_params[2:]:
        ctrl.change(fn=process_image, inputs=edit_params, outputs=output_img, show_progress="hidden")

    # 4. Add Current Edited Photo to A4 Print Queue
    def format_queue_outputs(queue, margin, gap, borders):
        gallery_items = [(item["image"], f"#{item['id']} ({item['w_in']}x{item['h_in']} in)") for item in queue]
        table_rows = [[item["id"], item["name"], item["w_in"], item["h_in"], item["copies"]] for item in queue]
        sheet_img, status = build_a4_sheet(queue, table_rows, 300, margin, gap, borders)
        
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png", prefix="A4_Print_Sheet_")
        sheet_img.save(tmp.name, format="PNG", dpi=(300, 300))
        badge = f"🖨️ *Queue: {len(queue)} photo(s) ready*"
        return queue, badge, gallery_items, table_rows, sheet_img, status, tmp.name

    def add_to_queue(edited_img, queue, copies, c_mode, w_in, h_in, margin, gap, borders):
        if edited_img is None:
            return format_queue_outputs(queue, margin, gap, borders)
        _, final_w_in, final_h_in = get_target_dimensions(c_mode, w_in, h_in)
        new_id = len(queue) + 1
        queue.append({
            "id": new_id,
            "name": f"Photo {new_id}",
            "image": edited_img.copy(),
            "w_in": round(float(final_w_in), 2),
            "h_in": round(float(final_h_in), 2),
            "copies": int(copies)
        })
        return format_queue_outputs(queue, margin, gap, borders)

    add_to_print_btn.click(
        fn=add_to_queue,
        inputs=[output_img, print_queue_state, copies_to_add, crop_mode, width_in, height_in, margin_mm, gap_mm, cut_lines],
        outputs=[print_queue_state, queue_badge, queue_gallery, queue_table, a4_preview_img, print_status, download_a4_file]
    )

    # 5. Update A4 Sheet Preview from Table / Margin Changes
    def refresh_a4(queue, table_df, margin, gap, borders):
        rows = table_df.values.tolist() if hasattr(table_df, "values") else (table_df or [])
        for idx, item in enumerate(queue):
            if idx < len(rows):
                try:
                    item["w_in"] = float(rows[idx][2])
                    item["h_in"] = float(rows[idx][3])
                    item["copies"] = int(float(rows[idx][4]))
                except (ValueError, IndexError, TypeError):
                    pass
        return format_queue_outputs(queue, margin, gap, borders)[1:]

    preview_a4_btn.click(
        fn=refresh_a4,
        inputs=[print_queue_state, queue_table, margin_mm, gap_mm, cut_lines],
        outputs=[queue_badge, queue_gallery, queue_table, a4_preview_img, print_status, download_a4_file]
    )

    for print_ctrl in [margin_mm, gap_mm, cut_lines]:
        print_ctrl.change(
            fn=refresh_a4,
            inputs=[print_queue_state, queue_table, margin_mm, gap_mm, cut_lines],
            outputs=[queue_badge, queue_gallery, queue_table, a4_preview_img, print_status, download_a4_file],
            show_progress="hidden"
        )

    # 6. Clear Print Queue
    def clear_queue(margin, gap, borders):
        return format_queue_outputs([], margin, gap, borders)

    clear_queue_btn.click(
        fn=clear_queue,
        inputs=[margin_mm, gap_mm, cut_lines],
        outputs=[print_queue_state, queue_badge, queue_gallery, queue_table, a4_preview_img, print_status, download_a4_file]
    )

    # 7. Native Browser Print Trigger
    print_now_btn.click(fn=None, inputs=None, outputs=None, js=PRINT_A4_JS)

    # 8. Reset Editor
    def reset_all(orig):
        editor_reset = {"background": orig, "layers": [], "composite": orig} if orig else None
        defaults = (
            None, editor_reset, "Whole Image", "Original (No Cutout)", "#DBEAFE", None,
            20, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, "Indian Passport / ID (1.5 x 2.0 in)", 1.5, 2.0, 300
        )
        preview = process_image(orig, *defaults) if orig else None
        return None, "⚪ *Standard Mode (No AI)*", *defaults[1:], preview

    reset_btn.click(
        fn=reset_all,
        inputs=[orig_state],
        outputs=[mask_state, mask_status] + edit_params[2:] + [output_img]
    )

if __name__ == "__main__":
    app.launch(inbrowser=True)