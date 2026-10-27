from __future__ import annotations

import re
import sys

from computer_use.core.capture import ScreenCapture
from computer_use.core.region import ScreenRegion
from computer_use.core.validator import ResultValidator
from computer_use.controllers.browser_controller import get_edge_enumerator
from computer_use.controllers.remote_controller import get_remote_enumerator
from computer_use.modes.remote import default_remote_controller
from computer_use.core.window_enum import get_window_enumerator
from computer_use.modes.browser import default_browser_controller
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
    from computer_use.gui.teach_replay_panel import TeachReplayPanel

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
            self._edge = get_edge_enumerator()
            self._remote_enum = get_remote_enumerator()
            self._browser = default_browser_controller()
            self._remote = default_remote_controller()
            self._region: ScreenRegion | None = None
            self._remote_inner: ScreenRegion | None = None
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

            self.remote_warn = QLabel(t("remote_warning", lang))
            self.remote_warn.setWordWrap(True)
            self.remote_warn.setStyleSheet("color: #06a;")
            layout.addWidget(self.remote_warn)

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

            self.ai_status = QLabel("")
            self.ai_status.setWordWrap(True)
            self.ai_status.setStyleSheet("color: #444; font-size: 11px;")
            layout.addWidget(QLabel(t("ai_model_panel", lang)))
            layout.addWidget(self.ai_status)
            self._refresh_ai_status()

            self.teach_panel = TeachReplayPanel(
                lang=lang,
                get_anchor_region=lambda: self._region,
                append_log=self._append_log,
            )
            layout.addWidget(self.teach_panel)

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

        def _refresh_ai_status(self) -> None:
            status = self._controller.agent_pipeline.model_status
            self.ai_status.setText(status)

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
            from computer_use.agent.types import Phase

            if phase == Phase.PAUSED:
                mode = self.mode_combo.currentData()
                if mode == AutomationMode.REMOTE:
                    self.status.setText(t("remote_pause_status", self.lang))
                else:
                    self.status.setText(t("auth_pause_status", self.lang))
                    self._append_log(t("auth_pause_log", self.lang))
                return
            if phase == Phase.INCOMPLETE:
                self.status.setText(t("remote_stop_status", self.lang))
                return
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
            self.remote_warn.setVisible(mode == AutomationMode.REMOTE)
            self.refresh_windows()

        def refresh_windows(self) -> None:
            self.window_list.clear()
            mode = self.mode_combo.currentData()
            if mode == AutomationMode.BROWSER:
                try:
                    self._browser.assert_attach_only()
                except Exception as exc:
                    self.status.setText(str(exc))
                    return
                for win in self._edge.list_edge_windows():
                    tab = f" — tab: {win.tab_hint}" if win.tab_hint else ""
                    self.window_list.addItem(f"{win.title}{tab} (#{win.handle})")
                if self.window_list.count() == 0:
                    self.window_list.addItem(t("browser_no_edge", self.lang))
                return
            if mode == AutomationMode.REMOTE:
                for win in self._remote_enum.list_remote_windows():
                    kind = win.client_kind.value.upper()
                    self.window_list.addItem(
                        f"[{kind}] {win.title} (#{win.handle})"
                    )
                if self.window_list.count() == 0:
                    self.window_list.addItem(t("remote_no_client", self.lang))
                return
            for win in self.enumerator.list_windows():
                self.window_list.addItem(f"{win.title} (#{win.handle})")

        def _on_region(self, region: ScreenRegion) -> None:
            self._region = region
            mode = self.mode_combo.currentData()
            handle = self._selected_window_handle()
            if mode == AutomationMode.REMOTE and handle and handle > 0:
                binding = self._remote.binding_from_gui_selection(
                    window_handle=handle,
                    user_screen_region=region,
                )
                if binding is not None:
                    self._remote_inner = binding.inner_relative
                    inner = self._remote_inner
                    self.status.setText(
                        f"Remote inner: {inner.left},{inner.top} "
                        f"{inner.width}x{inner.height} (window #{handle})"
                    )
                    return
                self._remote_inner = None
                self.status.setText(t("remote_region_outside", self.lang))
                return
            self._remote_inner = None
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
            if self.teach_panel.is_teach_mode():
                self.status.setText(t("teach_mode_blocks_closed_loop", self.lang))
                return
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
            mode = self.mode_combo.currentData()
            handle = self._selected_window_handle()
            remote_inner = None
            if mode == AutomationMode.BROWSER:
                if handle is None or handle <= 0:
                    self.status.setText(t("browser_pick_edge", self.lang))
                    return
                if self._edge.focus_window(handle):
                    self._append_log(f"Focused Edge #{handle}")
            elif mode == AutomationMode.REMOTE:
                if handle is None or handle <= 0:
                    self.status.setText(t("remote_pick_client", self.lang))
                    return
                binding = self._remote.binding_from_gui_selection(
                    window_handle=handle,
                    user_screen_region=region,
                )
                if binding is None:
                    self.status.setText(t("remote_region_outside", self.lang))
                    return
                remote_inner = binding.inner_relative
                self._remote_inner = remote_inner
                if self._remote_enum.focus_window(handle):
                    self._append_log(f"Focused remote client #{handle}")
            config = ClosedLoopConfig(
                goal=goal,
                mode=mode,
                region=region,
                window_handle=handle,
                remote_inner_region=remote_inner,
                dry_run=sys.platform != "win32",
            )
            if self._controller.start(config):
                self._set_controls_running(True)
                self._append_log("Closed-loop run started")
                self._refresh_ai_status()
                rec = self._controller.agent_pipeline.model_manager.recommendation
                if rec:
                    self._append_log(f"AI planner model: {rec.text_model} ({rec.notes})")

        def on_pause(self) -> None:
            self._controller.pause()
            self.status.setText(t("paused_status", self.lang))

        def on_resume(self) -> None:
            ctx = self._controller.context
            if self._controller.auth_reobserve_pending:
                self._controller.resume_after_auth_pause()
                self.status.setText(t("auth_resume_status", self.lang))
                return
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
