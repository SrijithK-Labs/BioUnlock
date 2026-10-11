"""PySide6 setup GUI for the BioUnlock PC agent (optional).

Importing this module does not require PySide6; ``main()`` imports it lazily so
the rest of the agent (and its tests) can run headless.
"""

from __future__ import annotations

import asyncio
import sys
import threading

from biounlock_agent.agent import Agent
from biounlock_agent.errors import AgentError


def main() -> int:  # pragma: no cover - GUI is exercised manually
    try:
        from PySide6.QtCore import QThread, QTimer, Signal
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import (
            QApplication,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"PySide6 is required for the GUI: {exc}", file=sys.stderr)
        return 1

    class EnrollWorker(QThread):
        paired = Signal(bool)
        failed = Signal(str)

        def __init__(self, agent: Agent, server_url: str, device_name: str) -> None:
            super().__init__()
            self._agent = agent
            self._server_url = server_url
            self._device_name = device_name
            self.enrollment = None

        def run(self) -> None:
            try:
                self.enrollment = self._agent.enroll(
                    self._server_url, device_name=self._device_name
                )
            except AgentError as exc:
                self.failed.emit(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(str(exc))
                return
            try:
                ok = asyncio.run(self._agent.wait_for_pairing(timeout=300.0))
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(str(exc))
                return
            self.paired.emit(ok)

    class AgentRunner:
        def __init__(self, agent: Agent) -> None:
            self.agent = agent
            self._thread: threading.Thread | None = None
            self._loop: asyncio.AbstractEventLoop | None = None

        def is_running(self) -> bool:
            return bool(self._thread and self._thread.is_alive())

        def start(self) -> None:
            if self.is_running():
                return
            self._loop = asyncio.new_event_loop()

            def _run() -> None:
                assert self._loop is not None
                asyncio.set_event_loop(self._loop)
                try:
                    self._loop.run_until_complete(self.agent.run())
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    self._loop.close()

            self._thread = threading.Thread(target=_run, name="biounlock-agent", daemon=True)
            self._thread.start()

        def stop(self) -> None:
            loop = self._loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self.agent.request_stop)
            else:
                self.agent.request_stop()

    class SetupWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.agent = Agent()
            self.runner = AgentRunner(self.agent)
            self._enroll_worker: EnrollWorker | None = None

            self.setWindowTitle("BioUnlock Setup")
            self.resize(520, 460)

            self.server_url = QLineEdit(self.agent.config.server_url or "")
            self.server_url.setPlaceholderText("https://unlock.example.com")
            self.device_name = QLineEdit(self.agent.config.device_name or "")
            self.enroll_button = QPushButton("Enroll this PC")

            form = QFormLayout()
            form.addRow("Server URL", self.server_url)
            form.addRow("PC name", self.device_name)

            self.code_label = QLabel("-")
            self.code_label.setTextInteractionFlags(self.code_label.textInteractionFlags())
            self.qr_label = QLabel()
            self.qr_label.setMinimumSize(240, 240)

            self.status_label = QLabel("")
            self.detail_label = QLabel("")
            self.detail_label.setWordWrap(True)

            self.start_button = QPushButton("Start agent")
            self.stop_button = QPushButton("Stop agent")
            self.unenroll_button = QPushButton("Unenroll")

            buttons = QHBoxLayout()
            buttons.addWidget(self.start_button)
            buttons.addWidget(self.stop_button)
            buttons.addWidget(self.unenroll_button)

            layout = QVBoxLayout()
            layout.addLayout(form)
            layout.addWidget(self.enroll_button)
            layout.addWidget(QLabel("Pairing code"))
            layout.addWidget(self.code_label)
            layout.addWidget(self.qr_label)
            layout.addWidget(self.status_label)
            layout.addWidget(self.detail_label)
            layout.addLayout(buttons)

            container = QWidget()
            container.setLayout(layout)
            self.setCentralWidget(container)

            self.enroll_button.clicked.connect(self._on_enroll)
            self.start_button.clicked.connect(self._on_start)
            self.stop_button.clicked.connect(self._on_stop)
            self.unenroll_button.clicked.connect(self._on_unenroll)

            self._refresh()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh)
            self._timer.start(1000)

        # --- actions ---

        def _on_enroll(self) -> None:
            url = self.server_url.text().strip()
            if not url:
                QMessageBox.warning(self, "BioUnlock", "Enter the server URL first.")
                return
            if self.runner.is_running():
                QMessageBox.warning(self, "BioUnlock", "Stop the agent before enrolling.")
                return
            self.enroll_button.setEnabled(False)
            self.code_label.setText("Enrolling...")
            self._enroll_worker = EnrollWorker(self.agent, url, self.device_name.text().strip())
            self._enroll_worker.paired.connect(self._on_enrolled)
            self._enroll_worker.failed.connect(self._on_enroll_failed)
            self._enroll_worker.start()

        def _on_enrolled(self, ok: bool) -> None:
            self.enroll_button.setEnabled(True)
            worker = self._enroll_worker
            if worker is not None and worker.enrollment is not None:
                self.code_label.setText(worker.enrollment.pairing_code)
                self._show_qr(worker.enrollment.qr_payload)
            self.status_label.setText("Paired" if ok else "Enrolled, waiting for phone")
            self.server_url.setText(self.agent.config.server_url or self.server_url.text())
            self._refresh()

        def _on_enroll_failed(self, message: str) -> None:
            self.enroll_button.setEnabled(True)
            self.code_label.setText("-")
            QMessageBox.critical(self, "BioUnlock", f"Enrollment failed:\n{message}")

        def _on_start(self) -> None:
            if not self.agent.config.is_enrolled:
                QMessageBox.warning(self, "BioUnlock", "Enroll this PC first.")
                return
            self.runner.start()

        def _on_stop(self) -> None:
            self.runner.stop()

        def _on_unenroll(self) -> None:
            confirm = QMessageBox.question(
                self,
                "BioUnlock",
                "Remove the local enrollment and device key?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            self.runner.stop()
            self.agent.unenroll()
            self.server_url.clear()
            self.code_label.setText("-")
            self.qr_label.clear()
            self._refresh()

        # --- display ---

        def _show_qr(self, payload: str) -> None:
            try:
                import segno
            except Exception:  # noqa: BLE001
                self.qr_label.setText("Install 'segno' to show a QR code.")
                return
            data = segno.make(payload, error="m").png_data(scale=6)
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.qr_label.setPixmap(pixmap)

        def _refresh(self) -> None:
            status = self.agent.status()
            state = "running" if self.runner.is_running() else "stopped"
            paired = "paired" if status.paired else "not paired"
            connected = "connected" if status.connected else "disconnected"
            self.status_label.setText(
                f"Agent: {state} | {paired} | {connected} | verified: {status.processed_count}"
            )
            details = []
            if status.device_id:
                details.append(f"Device: {status.device_name} ({status.device_id})")
            if status.account_email:
                details.append(f"Account: {status.account_email}")
            if status.server_url:
                details.append(f"Server: {status.server_url}")
            if status.last_error:
                details.append(f"Last error: {status.last_error}")
            self.detail_label.setText("\n".join(details))
            self.start_button.setEnabled(not self.runner.is_running())
            self.stop_button.setEnabled(self.runner.is_running())

        def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
            self.runner.stop()
            super().closeEvent(event)

    app = QApplication.instance() or QApplication(sys.argv)
    window = SetupWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
