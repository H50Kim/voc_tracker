from __future__ import annotations

import re
import sys

from computer_use.core.capture import ScreenCapture
from computer_use.core.region import ScreenRegion
from computer_use.core.validator import ResultValidator
from computer_use.core.window_enum import get_window_enumerator
from computer_use.gui.closed_loop_controller import ClosedLoopConfig, ClosedLoopController
from computer_use.gui.paths import default_ledger_path
from computer_use.gui.strings import MODE_LABELS, t
from computer_use.modes.types import AutomationMode

try:
    from PySide6.QtCore import QMetaObject, Q_ARG, Qt, Slot
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTextEdit,
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
            self.capture = ScreenCapture()
            self.validator = ResultValidator()
            self.enumerator = get_window_enumerator()
            self._region: ScreenRegion | None = None
            self._confirm_result: bool | None = None
            self._confirm_ready = False

            self._controller = ClosedLoopController(
                on_log=self._append_log,
                on_phase=self._on_phase_transition,
                on_finished=self._on_run_finished,
                request_confirmation=self._request_confirmation_worker,
                focus_window=self.enumerator.focus_window,
            )

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
            self.emergency_btn = QPushButton(t("emergency_stop", lang))
            self.start_btn.clicked.connect(self.on_start)
            self.pause_btn.clicked.connect(self.on_pause)
            self.resume_btn.clicked.connect(self.on_resume)
            self.stop_btn.clicked.connect(self.on_stop)
            self.emergency_btn.clicked.connect(self.on_emergency_stop)
            for b in (
                self.start_btn,
                self.pause_btn,
                self.resume_btn,
                self.stop_btn,
                self.emergency_btn,
            ):
                btn_row.addWidget(b)
            layout.addLayout(btn_row)

            self.status = QLabel("")
            layout.addWidget(self.status)

            self.log_panel = QTextEdit()
            self.log_panel.setReadOnly(True)
            self.log_panel.setMinimumHeight(120)
            layout.addWidget(QLabel(t("run_log", lang)))
            layout.addWidget(self.log_panel)

            preview = self.capture.capture_screen()
            self.region_selector.set_preview_image(preview)
            self.refresh_windows()
            self._on_mode_changed()
            self._load_ledger_startup()

        def _load_ledger_startup(self) -> None:
            snap = self._controller.load_startup_snapshot()
            path = default_ledger_path()
            self._append_log(f"Ledger: {path}")
            if snap and snap.pending_operation and not snap.pending_operation.resolved:
                op = snap.pending_operation
                self.status.setText(
                    f"Pending (unresolved): {op.operation_id} — no auto re-execute"
                )
                self._append_log(
                    f"Startup: unresolved pending {op.operation_id} "
                    f"({op.semantic_operation_key})"
                )

        def _append_log(self, line: str) -> None:
            self.log_panel.append(line)

        def _on_phase_transition(self, phase, _result) -> None:
            self.status.setText(f"Phase: {phase.value}")

        def _on_run_finished(self, result) -> None:
            outcome = result.outcome.value if result.outcome else "—"
            self.status.setText(f"Finished: {result.phase.value} ({outcome})")
            self._set_controls_running(False)

        def _set_controls_running(self, running: bool) -> None:
            self.start_btn.setEnabled(not running)
            self.pause_btn.setEnabled(running)
            self.resume_btn.setEnabled(running)
            self.stop_btn.setEnabled(running)
            self.emergency_btn.setEnabled(running)

        def _on_mode_changed(self) -> None:
            mode = self.mode_combo.currentData()
            self.browser_warn.setVisible(mode == AutomationMode.BROWSER)

        def refresh_windows(self) -> None:
            self.window_list.clear()
            for win in self.enumerator.list_windows():
                self.window_list.addItem(f"{win.title} (#{win.handle})")

        def _on_region(self, region: ScreenRegion) -> None:
            self._region = region
            self.status.setText(
                f"Region: {region.left},{region.top} {region.width}x{region.height}"
            )

        def _selected_window_handle(self) -> int | None:
            item = self.window_list.currentItem()
            if item is None:
                return None
            text = item.text()
            match = re.search(r"#(\d+)\)", text)
            if not match:
                return None
            handle = int(match.group(1))
            return handle if handle > 0 else None

        def _request_confirmation_worker(self, action, goal: str):
            from computer_use.agent.types import SafetyDecision

            self._confirm_result = None
            self._confirm_ready = False
            QMetaObject.invokeMethod(
                self,
                "_show_confirmation_dialog",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(str, action.description),
                Q_ARG(str, goal),
            )
            approved = bool(self._confirm_result)
            return SafetyDecision(approved=approved, reason="" if approved else "denied")

        @Slot(str, str)
        def _show_confirmation_dialog(self, description: str, goal: str) -> None:
            msg = t("confirm_action", self.lang).format(
                description=description, goal=goal
            )
            box = QMessageBox(self)
            box.setWindowTitle(t("confirm_title", self.lang))
            box.setText(msg)
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            box.setDefaultButton(QMessageBox.StandardButton.No)
            self._confirm_result = box.exec() == QMessageBox.StandardButton.Yes

        def on_start(self) -> None:
            if self._controller.state.value != "idle":
                return
            goal = self.instruction.text().strip()
            if not goal:
                self.status.setText(t("goal_required", self.lang))
                return
            region = self._region
            if region is None:
                w, h = self.capture.primary_monitor_size()
                region = ScreenRegion(0, 0, min(400, w), min(300, h))
            config = ClosedLoopConfig(
                goal=goal,
                mode=self.mode_combo.currentData(),
                region=region,
                window_handle=self._selected_window_handle(),
                dry_run=sys.platform != "win32",
            )
            if self._controller.start(config):
                self._set_controls_running(True)
                self._append_log("Closed-loop run started")

        def on_pause(self) -> None:
            self._controller.pause()
            self.status.setText(t("paused_status", self.lang))

        def on_resume(self) -> None:
            ctx = self._controller.context
            at_safety = ctx is not None and ctx.phase.value == "safety_gate"
            self._controller.resume(ui_recovery=at_safety)
            self.status.setText(t("resumed_status", self.lang))

        def on_stop(self) -> None:
            self._controller.stop()
            self._controller.join(timeout=3.0)

        def on_emergency_stop(self) -> None:
            self._controller.stop(emergency=True)
            self._controller.join(timeout=3.0)

else:
    MainWindow = None  # type: ignore[misc, assignment]
