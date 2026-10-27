from __future__ import annotations

import sys
from pathlib import Path

from computer_use.controllers.browser_controller import get_edge_enumerator
from computer_use.core.region import ScreenRegion
from computer_use.gui.strings import t
from computer_use.workflow.glean_helper import GleanHelper
from computer_use.workflow.recorder import WorkflowRecorder
from computer_use.workflow.replay import WorkflowReplayer
from computer_use.workflow.storage import default_workflows_dir, load_workflow, save_workflow

try:
    from PySide6.QtWidgets import (
        QCheckBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class TeachReplayPanel(QWidget):
        """Teach & Replay controls (local JSON workflows)."""

        def __init__(
            self,
            *,
            lang: str,
            get_anchor_region,
            append_log,
            parent=None,
        ) -> None:
            super().__init__(parent)
            self.lang = lang
            self._get_anchor_region = get_anchor_region
            self._append_log = append_log
            self._recorder = WorkflowRecorder(on_log=append_log)
            self._glean = GleanHelper()
            self._edge = get_edge_enumerator()

            layout = QVBoxLayout(self)
            self.enable_cb = QCheckBox(t("teach_replay_enable", lang))
            layout.addWidget(self.enable_cb)

            box = QGroupBox(t("teach_replay_group", lang))
            box_layout = QVBoxLayout(box)

            row1 = QHBoxLayout()
            self.record_start_btn = QPushButton(t("teach_record_start", lang))
            self.record_stop_btn = QPushButton(t("teach_record_stop", lang))
            self.record_start_btn.clicked.connect(self._on_record_start)
            self.record_stop_btn.clicked.connect(self._on_record_stop)
            row1.addWidget(self.record_start_btn)
            row1.addWidget(self.record_stop_btn)
            box_layout.addLayout(row1)

            self.workflow_name = QLineEdit()
            self.workflow_name.setPlaceholderText(t("teach_workflow_name", lang))
            box_layout.addWidget(self.workflow_name)

            row2 = QHBoxLayout()
            self.save_btn = QPushButton(t("teach_save", lang))
            self.load_btn = QPushButton(t("teach_load", lang))
            self.replay_btn = QPushButton(t("teach_replay", lang))
            self.glean_btn = QPushButton(t("teach_glean", lang))
            self.save_btn.clicked.connect(self._on_save)
            self.load_btn.clicked.connect(self._on_load)
            self.replay_btn.clicked.connect(self._on_replay)
            self.glean_btn.clicked.connect(self._on_glean)
            for b in (self.save_btn, self.load_btn, self.replay_btn, self.glean_btn):
                row2.addWidget(b)
            box_layout.addLayout(row2)

            layout.addWidget(box)
            self._sync_enabled(False)
            self.enable_cb.toggled.connect(self._sync_enabled)

        def _sync_enabled(self, enabled: bool) -> None:
            for w in (
                self.record_start_btn,
                self.record_stop_btn,
                self.save_btn,
                self.load_btn,
                self.replay_btn,
                self.glean_btn,
                self.workflow_name,
            ):
                w.setEnabled(enabled)

        def is_teach_mode(self) -> bool:
            return self.enable_cb.isChecked()

        def _apply_anchor(self) -> None:
            region = self._get_anchor_region()
            if region is not None:
                self._recorder.anchor_region = region
            else:
                w, h = self._recorder.capture.primary_monitor_size()
                self._recorder.anchor_region = ScreenRegion(0, 0, w, h)

        def _on_record_start(self) -> None:
            self._apply_anchor()
            self._recorder.clear()
            name = self.workflow_name.text().strip()
            if name:
                self._recorder.document.name = name
            self._recorder.start_listening()
            self._append_log(t("teach_recording_on", self.lang))

        def _on_record_stop(self) -> None:
            self._recorder.stop_listening()
            self._append_log(
                t("teach_recording_off", self.lang).format(
                    count=len(self._recorder.document.steps)
                )
            )

        def _on_save(self) -> None:
            self._apply_anchor()
            name = self.workflow_name.text().strip() or self._recorder.document.name
            self._recorder.document.name = name
            default_dir = default_workflows_dir()
            default_dir.mkdir(parents=True, exist_ok=True)
            path, _ = QFileDialog.getSaveFileName(
                self,
                t("teach_save", self.lang),
                str(default_dir / f"{name}.json"),
                "JSON (*.json)",
            )
            if not path:
                return
            save_workflow(Path(path), self._recorder.document)
            self._append_log(f"Saved workflow: {path}")

        def _on_load(self) -> None:
            default_dir = default_workflows_dir()
            path, _ = QFileDialog.getOpenFileName(
                self,
                t("teach_load", self.lang),
                str(default_dir),
                "JSON (*.json)",
            )
            if not path:
                return
            self._recorder.document = load_workflow(Path(path))
            self.workflow_name.setText(self._recorder.document.name)
            self._append_log(
                t("teach_loaded", self.lang).format(
                    path=path, count=len(self._recorder.document.steps)
                )
            )

        def _on_replay(self) -> None:
            self._apply_anchor()
            dry = sys.platform != "win32"
            replayer = WorkflowReplayer(dry_run=dry)
            result = replayer.replay(self._recorder.document)
            for outcome in result.outcomes:
                self._append_log(
                    f"Replay step {outcome.index}: {outcome.message}"
                )
            if result.success:
                self._append_log(t("teach_replay_ok", self.lang))
            else:
                self._append_log(t("teach_replay_fail", self.lang))

        def _on_glean(self) -> None:
            msg = self._glean.suggest_open_glean_tab(self._edge.list_edge_windows())
            self._append_log(msg)

else:
    TeachReplayPanel = None  # type: ignore[misc, assignment]
