from __future__ import annotations

from computer_use.agents.pipeline import AgentPipeline
from computer_use.core.capture import ScreenCapture
from computer_use.core.region import ScreenRegion
from computer_use.core.validator import ResultValidator
from computer_use.core.window_enum import get_window_enumerator
from computer_use.gui.strings import MODE_LABELS, t
from computer_use.modes.types import AutomationMode

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    from computer_use.gui.region_selector import RegionSelectorWidget

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class MainWindow(QMainWindow):
        def __init__(self, lang: str = "ko") -> None:
            super().__init__()
            self.lang = lang
            self.pipeline = AgentPipeline()
            self.capture = ScreenCapture()
            self.validator = ResultValidator()
            self.enumerator = get_window_enumerator()
            self._region: ScreenRegion | None = None
            self._running = False

            self.setWindowTitle(t("app_title", lang))
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)

            mode_row = QHBoxLayout()
            mode_row.addWidget(QLabel(t("mode", lang)))
            self.mode_combo = QComboBox()
            for mode in AutomationMode:
                labels = MODE_LABELS[mode]
                self.mode_combo.addItem(labels.get(lang, labels["en"]), mode)
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
            mode_row.addWidget(self.mode_combo)
            layout.addLayout(mode_row)

            self.browser_warn = QLabel(t("browser_warning", lang))
            self.browser_warn.setWordWrap(True)
            self.browser_warn.setStyleSheet("color: #a60;")
            layout.addWidget(self.browser_warn)

            self.window_list = QListWidget()
            layout.addWidget(self.window_list)
            refresh_btn = QPushButton(t("refresh_windows", lang))
            refresh_btn.clicked.connect(self.refresh_windows)
            layout.addWidget(refresh_btn)

            self.region_selector = RegionSelectorWidget()
            layout.addWidget(QLabel(t("region_hint", lang)))
            layout.addWidget(self.region_selector)
            self.region_selector.regionSelected.connect(self._on_region)

            self.instruction = QLineEdit()
            self.instruction.setPlaceholderText(t("natural_language", lang))
            layout.addWidget(self.instruction)

            btn_row = QHBoxLayout()
            self.start_btn = QPushButton(t("start", lang))
            self.pause_btn = QPushButton(t("pause", lang))
            self.resume_btn = QPushButton(t("resume", lang))
            self.stop_btn = QPushButton(t("stop", lang))
            self.start_btn.clicked.connect(self.on_start)
            self.pause_btn.clicked.connect(self.on_pause)
            self.resume_btn.clicked.connect(self.on_resume)
            self.stop_btn.clicked.connect(self.on_stop)
            for b in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn):
                btn_row.addWidget(b)
            layout.addLayout(btn_row)

            self.status = QLabel("")
            layout.addWidget(self.status)

            preview = self.capture.capture_screen()
            self.region_selector.set_preview_image(preview)
            self.refresh_windows()
            self._on_mode_changed()

        def _on_mode_changed(self) -> None:
            mode = self.mode_combo.currentData()
            self.browser_warn.setVisible(mode == AutomationMode.BROWSER)

        def refresh_windows(self) -> None:
            self.window_list.clear()
            for win in self.enumerator.list_windows():
                self.window_list.addItem(f"{win.title} (#{win.handle})")

        def _on_region(self, region: ScreenRegion) -> None:
            self._region = region
            self.status.setText(f"Region: {region.left},{region.top} {region.width}x{region.height}")

        def on_start(self) -> None:
            if self.pipeline.paused:
                return
            self._running = True
            region = self._region
            if region is None:
                w, h = self.capture.primary_monitor_size()
                region = ScreenRegion(0, 0, min(400, w), min(300, h))
            before = self.capture.capture_region(region)
            after = self.capture.capture_region(region)
            result = self.validator.validate_unchanged(before, after)
            self.status.setText(
                f"Validation: {'OK' if result.passed else 'FAIL'} ({result.similarity:.3f})"
            )

        def on_pause(self) -> None:
            self.pipeline.pause_for_mfa()
            self.status.setText("Paused (MFA/user)")

        def on_resume(self) -> None:
            self.pipeline.resume()
            self.status.setText("Resumed")

        def on_stop(self) -> None:
            self._running = False
            self.pipeline.resume()
            self.status.setText("Stopped")

else:
    MainWindow = None  # type: ignore[misc, assignment]
