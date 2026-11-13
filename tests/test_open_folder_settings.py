"""
tests/test_open_folder_settings.py - Unit tests for remembering the last-opened
folder in QSettings (Windows Registry by default) for the Add Photos dialog only.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PIL import Image
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication

import main


_APP = QApplication.instance() or QApplication(sys.argv)


class TestOpenFolderSettings(unittest.TestCase):
    """Verifies remembered Add Photos folder persistence and fallback behavior."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        self.ini_path = self.tmp_root / "test_settings.ini"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_settings(self) -> QSettings:
        return QSettings(str(self.ini_path), QSettings.IniFormat)

    def _make_image_file(self, folder: Path, filename: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        Image.new("RGB", (64, 64), (120, 160, 200)).save(path)
        return path

    def test_default_settings_uses_native_registry(self):
        win = main.PhotoStudioApp()
        self.addCleanup(win.close)

        self.assertEqual(win.settings.format(), QSettings.NativeFormat)
        self.assertIn(main.APP_ORGANIZATION, win.settings.fileName())
        self.assertIn(main.APP_NAME, win.settings.fileName())

    def test_first_run_falls_back_to_pictures_location(self):
        pictures_dir = self.tmp_root / "Pictures"
        pictures_dir.mkdir()
        win = main.PhotoStudioApp(settings=self._make_settings())
        self.addCleanup(win.close)

        with patch.object(
            QStandardPaths, "writableLocation", return_value=str(pictures_dir)
        ):
            self.assertEqual(win._get_initial_open_dir(), str(pictures_dir))

    def test_open_files_persists_folder_across_restarts_and_cancel_keeps_it(self):
        pictures_dir = self.tmp_root / "Pictures"
        pictures_dir.mkdir()
        shoot_dir = self.tmp_root / "ShootA"
        img_a = self._make_image_file(shoot_dir, "a.png")

        win1 = main.PhotoStudioApp(settings=self._make_settings())
        self.addCleanup(win1.close)

        with patch.object(
            QStandardPaths, "writableLocation", return_value=str(pictures_dir)
        ), patch.object(
            main.QFileDialog,
            "getOpenFileNames",
            return_value=([str(img_a)], "Images (*.png)"),
        ) as mock_dialog:
            win1._on_open_files()

        self.assertEqual(mock_dialog.call_args.args[2], str(pictures_dir))
        self.assertEqual(len(win1.workspace_photos), 1)

        # New app instance simulates restart and reads persisted folder
        win2 = main.PhotoStudioApp(settings=self._make_settings())
        self.addCleanup(win2.close)

        with patch.object(
            main.QFileDialog,
            "getOpenFileNames",
            return_value=([], ""),
        ) as mock_dialog_cancel:
            win2._on_open_files()

        self.assertEqual(mock_dialog_cancel.call_args.args[2], str(shoot_dir))
        self.assertEqual(
            win2.settings.value(main.SETTINGS_LAST_OPEN_DIR), str(shoot_dir)
        )

    def test_missing_saved_folder_falls_back_cleanly(self):
        pictures_dir = self.tmp_root / "Pictures"
        pictures_dir.mkdir()
        deleted_dir = self.tmp_root / "DeletedFolder"

        settings = self._make_settings()
        settings.setValue(main.SETTINGS_LAST_OPEN_DIR, str(deleted_dir))
        settings.sync()

        win = main.PhotoStudioApp(settings=settings)
        self.addCleanup(win.close)

        with patch.object(
            QStandardPaths, "writableLocation", return_value=str(pictures_dir)
        ):
            self.assertEqual(win._get_initial_open_dir(), str(pictures_dir))

        with patch.object(QStandardPaths, "writableLocation", return_value=""):
            self.assertEqual(win._get_initial_open_dir(), "")

    def test_drag_and_drop_does_not_overwrite_remembered_folder(self):
        shoot_dir = self.tmp_root / "ShootA"
        drop_dir = self.tmp_root / "Downloads"
        dropped_img = self._make_image_file(drop_dir, "dropped.png")

        settings = self._make_settings()
        settings.setValue(main.SETTINGS_LAST_OPEN_DIR, str(shoot_dir))
        shoot_dir.mkdir()
        settings.sync()

        win = main.PhotoStudioApp(settings=settings)
        self.addCleanup(win.close)

        win.canvas.filesDropped.emit([str(dropped_img)])

        self.assertEqual(len(win.workspace_photos), 1)
        self.assertEqual(win._get_initial_open_dir(), str(shoot_dir))
        self.assertEqual(
            self._make_settings().value(main.SETTINGS_LAST_OPEN_DIR), str(shoot_dir)
        )


if __name__ == "__main__":
    unittest.main()
