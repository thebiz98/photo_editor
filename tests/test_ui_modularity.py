"""
tests/test_ui_modularity.py - Headless PySide6 verification for UI modularity,
theme tokens, section style overrides, primitives, and end-to-end studio workflows.
"""

from dataclasses import replace
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PIL import Image
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

import main
from ui.primitives import (
    AppButton,
    AppLabel,
    LabeledSlider,
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    NoWheelSlider,
    NoWheelSpinBox,
    SectionBox,
    SegmentedButtonGroup,
)
from ui.theme import STUDIO_DARK_THEME, SectionStyle, build_stylesheet


_APP = QApplication.instance() or QApplication(sys.argv)


class TestUIModularity(unittest.TestCase):
    """Verifies modular UI architecture, theme generation, and studio workflows."""

    def test_theme_compilation_and_section_overrides(self):
        base_qss = build_stylesheet(STUDIO_DARK_THEME)
        self.assertIn('QPushButton[variant="primary"]', base_qss)
        self.assertIn('QLabel[tone="danger"]', base_qss)
        self.assertNotIn("QPushButton#btn_apply_crop", base_qss)

        custom_sections = dict(STUDIO_DARK_THEME.sections)
        custom_sections["ai_background"] = SectionStyle(
            margins=(10, 8, 10, 10),
            spacing=8,
            title_color="#a78bfa",
            border_color="#8b5cf6",
            font_size=12,
        )
        custom_theme = replace(STUDIO_DARK_THEME, sections=custom_sections)
        custom_qss = build_stylesheet(custom_theme)

        self.assertIn('QGroupBox[section="ai_background"]', custom_qss)
        self.assertIn("border-color: #8b5cf6;", custom_qss)
        self.assertIn('QGroupBox[section="ai_background"]::title', custom_qss)
        self.assertIn("color: #a78bfa;", custom_qss)

        box = SectionBox("AI", section_id="ai_background", zone_id="inspector-right", theme=custom_theme)
        self.assertEqual(box.property("section"), "ai_background")
        self.assertEqual(box.property("zone"), "inspector-right")
        self.assertEqual(box.body_layout.spacing(), 8)

    def test_primitives_and_wheel_safety(self):
        btn = AppButton("Run", variant="compute", ui_size="lg")
        self.assertEqual(btn.property("variant"), "compute")
        self.assertEqual(btn.property("uiSize"), "lg")

        seg = SegmentedButtonGroup([("a", "A", "Tip A"), ("b", "B", "Tip B")], active_key="a")
        emitted = []
        seg.selectionChanged.connect(emitted.append)
        seg.button("b").click()
        self.assertEqual(seg.active_key(), "b")
        self.assertEqual(emitted, ["b"])

        lbl = AppLabel("Status", role="caption", tone="accent")
        lbl.set_tone("danger")
        self.assertEqual(lbl.property("tone"), "danger")

        slider = LabeledSlider("Feather", 0, 50, 0, formatter=lambda v: f"{v / 10.0:.1f} px")
        slider.set_value(35, block_signals=True)
        self.assertEqual(slider.lbl_value.text(), "3.5 px")
        slider.reset(block_signals=True)
        self.assertEqual(slider.lbl_value.text(), "0.0 px")

        for widget in (
            NoWheelSlider(Qt.Horizontal),
            NoWheelSpinBox(),
            NoWheelDoubleSpinBox(),
            NoWheelComboBox(),
        ):
            ev = QWheelEvent(
                QPointF(0, 0),
                QPointF(0, 0),
                widget.pos(),
                widget.pos(),
                Qt.NoButton,
                Qt.NoModifier,
                Qt.ScrollUpdate,
                False,
            )
            widget.wheelEvent(ev)
            self.assertFalse(ev.isAccepted(), f"{type(widget).__name__} should ignore wheel events")

    def test_no_inline_stylesheets_on_child_widgets(self):
        win = main.PhotoStudioApp()
        self.addCleanup(win.close)

        self.assertTrue(len(win.styleSheet()) > 1000)
        for child in win.findChildren(QWidget):
            self.assertEqual(
                child.styleSheet(),
                "",
                f"Unexpected inline styleSheet on child {type(child).__name__} ({child.objectName()})",
            )

        sections = win.findChildren(SectionBox)
        self.assertGreaterEqual(len(sections), 8)
        for sec in sections:
            self.assertTrue(bool(sec.property("section")))
            self.assertTrue(bool(sec.property("zone")))

    def test_studio_and_print_workflows(self):
        win = main.PhotoStudioApp()
        self.addCleanup(win.close)

        img1 = Image.new("RGB", (400, 300), (200, 100, 50))
        img2 = Image.new("RGB", (800, 600), (50, 100, 200))
        idx0 = win._add_photo_to_workspace(img1, "p1.png")
        idx1 = win._add_photo_to_workspace(img2, "p2.png")

        win.workspace_panel.set_current_row(idx0)
        self.assertEqual(win.current_photo_idx, 0)
        win.lighting_panel.slider_bright.slider.setValue(120)

        # Workspace isolation across photos
        win.workspace_panel.set_current_row(idx1)
        self.assertEqual(win.lighting_panel.slider_bright.value(), 100)
        win.workspace_panel.set_current_row(idx0)
        self.assertEqual(win.lighting_panel.slider_bright.value(), 120)

        # Crop/Straighten mode & canvas overlay rendering
        win.crop_panel.mode_selector.button("perspective").click()
        self.assertEqual(win.canvas.crop_mode, "perspective")
        paint_target = QPixmap(200, 150)
        painter = QPainter(paint_target)
        win.canvas.render(painter)
        painter.end()

        win.crop_panel.mode_selector.button("standard").click()
        self.assertEqual(win.canvas.crop_mode, "standard")
        win.crop_panel.combo_presets.setCurrentText("Standard Passport (35 x 45 mm)")
        win.crop_panel.combo_unit.setCurrentText("in")
        self.assertEqual(win.crop_panel.current_unit(), "in")

        win._on_apply_crop()
        self.assertTrue(win.toolbar.btn_undo.isEnabled())
        win._on_undo()
        win._on_bake_edit()
        win._on_revert_to_original()

        # Rescale safety limit tone switch without inline setStyleSheet
        win.rescale_panel.spin_rescale_pct.setValue(400)
        win._on_rescale_pct_changed(400)
        win.workspace_panel.set_current_row(idx1)
        win.rescale_panel.spin_rescale_pct.setValue(600)
        win._on_rescale_pct_changed(600)
        # Verify tone switch at extreme scale (400% of 800x600 is 3200px, within 4096;
        # force a large image to exceed MAX_SAFE_IMAGE_DIM)
        big_img = Image.new("RGB", (2000, 2000), (10, 20, 30))
        idx2 = win._add_photo_to_workspace(big_img, "big.png")
        win.workspace_panel.set_current_row(idx2)
        win.rescale_panel.spin_rescale_pct.setValue(300)
        win._on_rescale_pct_changed(300)
        self.assertEqual(win.rescale_panel.lbl_target_res.property("tone"), "danger")
        self.assertFalse(win.rescale_panel.btn_apply_scale.isEnabled())

        # Send to Print Studio and verify queue interactions
        win.workspace_panel.set_current_row(idx0)
        win._on_send_to_print_queue()
        win.tabs.setCurrentIndex(1)
        self.assertEqual(win.tab_printer.tbl_queue.rowCount(), 1)
        self.assertIn("Placed: 4 photos", win.tab_printer.lbl_queue_status.text())
        win.tab_printer._on_remove_queue_item(0)
        self.assertEqual(win.tab_printer.tbl_queue.rowCount(), 0)


if __name__ == "__main__":
    unittest.main()
