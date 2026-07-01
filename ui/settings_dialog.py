from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QRadioButton, QButtonGroup, QPushButton, QGroupBox, QFormLayout,
    QCheckBox, QComboBox, QSlider, QApplication,
)
import logging

from PyQt5.QtCore import Qt, QTimer

from proxy import ProxyConfig, detect_system_proxy, get_system_pac_url, get_system_auto_detect, set_auto_start
from player import get_output_devices

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    def __init__(self, proxy_config: ProxyConfig, player=None, lms_service=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self._proxy_config = proxy_config
        self._player = player
        self._lms_service = lms_service
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        group = QGroupBox("Proxy Mode")
        group_layout = QVBoxLayout(group)
        self._btn_group = QButtonGroup(self)
        self._rb_off = QRadioButton("Off (direct connection)")
        self._rb_system = QRadioButton("System proxy (Windows settings)")
        self._rb_manual = QRadioButton("Manual proxy")

        self._btn_group.addButton(self._rb_off, 0)
        self._btn_group.addButton(self._rb_system, 1)
        self._btn_group.addButton(self._rb_manual, 2)

        group_layout.addWidget(self._rb_off)
        group_layout.addWidget(self._rb_system)
        group_layout.addWidget(self._rb_manual)
        layout.addWidget(group)

        self._rb_off.toggled.connect(self._on_mode_changed)
        self._rb_system.toggled.connect(self._on_mode_changed)
        self._rb_manual.toggled.connect(self._on_mode_changed)

        manual_group = QGroupBox("Manual Proxy Settings")
        manual_layout = QFormLayout(manual_group)

        self._server_edit = QLineEdit()
        self._server_edit.setPlaceholderText("proxy.example.com")
        manual_layout.addRow("Server:", self._server_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(8080)
        manual_layout.addRow("Port:", self._port_spin)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("(optional)")
        manual_layout.addRow("Username:", self._user_edit)

        self._pwd_edit = QLineEdit()
        self._pwd_edit.setEchoMode(QLineEdit.Password)
        self._pwd_edit.setPlaceholderText("(optional)")
        manual_layout.addRow("Password:", self._pwd_edit)

        layout.addWidget(manual_group)
        self._manual_group = manual_group

        sys_info_group = QGroupBox("Detected System Proxy")
        sys_info_layout = QVBoxLayout(sys_info_group)
        self._sys_proxy_label = QLabel("(not detected)")
        self._sys_proxy_label.setWordWrap(True)
        sys_info_layout.addWidget(self._sys_proxy_label)
        layout.addWidget(sys_info_group)

        self._auto_play_cb = QCheckBox("Auto-play last stream on startup")
        self._auto_play_cb.setChecked(self._proxy_config.auto_play)
        layout.addWidget(self._auto_play_cb)

        self._auto_start_cb = QCheckBox("Start app automatically at Windows login")
        self._auto_start_cb.setChecked(self._proxy_config.auto_start)
        layout.addWidget(self._auto_start_cb)

        scan_group = QGroupBox("Station Scanner")
        scan_layout = QFormLayout(scan_group)
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 50)
        self._workers_spin.setValue(self._proxy_config.workers)
        self._workers_spin.setToolTip("Number of parallel tasks when checking which streams are reachable")
        scan_layout.addRow("Workers:", self._workers_spin)
        layout.addWidget(scan_group)

        audio_group = QGroupBox("Audio Output")
        audio_layout = QFormLayout(audio_group)
        self._device_combo = QComboBox()
        self._device_combo.setToolTip("Select the audio output device")
        self._populate_devices()
        audio_layout.addRow("Device:", self._device_combo)
        layout.addWidget(audio_group)

        volume_group = QGroupBox("Volume")
        volume_layout = QVBoxLayout(volume_group)
        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setToolTip("Adjust playback volume")
        self._volume_label = QLabel("100%")
        self._volume_label.setAlignment(Qt.AlignCenter)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_layout.addWidget(self._volume_slider)
        volume_layout.addWidget(self._volume_label)
        layout.addWidget(volume_group)

        lms_group = QGroupBox("Lyrion Music Server")
        lms_layout = QFormLayout(lms_group)
        self._lms_server_combo = QComboBox()
        self._lms_server_combo.setEditable(True)
        self._lms_server_combo.setToolTip("Select a discovered server or type a custom host:port")
        self._lms_server_combo.lineEdit().setPlaceholderText("host:port (e.g. 192.168.1.90:9000)")
        self._lms_player_name = QLineEdit()
        self._lms_player_name.setPlaceholderText("TrayRadio")
        self._lms_auto_cb = QCheckBox("Auto-connect on startup")
        lms_btn_layout = QHBoxLayout()
        self._lms_status_label = QLabel("⚫ Not connected")
        self._lms_rescan_btn = QPushButton("Rescan Network")
        self._lms_rescan_btn.clicked.connect(self._on_lms_rescan)
        self._lms_test_btn = QPushButton("Test Server")
        self._lms_test_btn.clicked.connect(self._on_lms_test)
        lms_btn_layout.addWidget(self._lms_status_label)
        lms_btn_layout.addStretch()
        lms_btn_layout.addWidget(self._lms_rescan_btn)
        lms_btn_layout.addWidget(self._lms_test_btn)
        lms_layout.addRow("Server:", self._lms_server_combo)
        lms_layout.addRow("Player Name:", self._lms_player_name)
        lms_layout.addRow(self._lms_auto_cb)
        lms_layout.addRow(lms_btn_layout)
        layout.addWidget(lms_group)
        self._lms_group = lms_group

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _populate_devices(self):
        self._device_combo.clear()
        self._device_combo.addItem("(System Default)", "")
        selected = self._proxy_config.output_device
        for d in get_output_devices():
            name = d["name"]
            if name == "(System Default)":
                continue
            self._device_combo.addItem(name, name)
        idx = self._device_combo.findData(selected)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)

    def _load_config(self):
        mode_map = {"off": 0, "system": 1, "manual": 2}
        btn_id = mode_map.get(self._proxy_config.mode, 1)
        btn = self._btn_group.button(btn_id)
        if btn:
            btn.setChecked(True)

        self._server_edit.setText(self._proxy_config.server)
        self._port_spin.setValue(self._proxy_config.port or 8080)
        self._user_edit.setText(self._proxy_config.username)
        self._pwd_edit.setText(self._proxy_config.password)

        sys_proxy = detect_system_proxy()
        pac_url = get_system_pac_url()
        auto_detect = get_system_auto_detect()
        lines = []
        if sys_proxy:
            lines.append(f"Proxy: {sys_proxy}")
        if pac_url:
            lines.append(f"PAC URL: {pac_url}")
        if auto_detect:
            lines.append("Auto-detect: enabled")
        if not lines:
            lines.append("(no system proxy detected)")
        self._sys_proxy_label.setText("\n".join(lines))
        self._volume_slider.setValue(self._proxy_config.volume)

        self._lms_player_name.setText(self._proxy_config.lms_player_name)
        self._lms_auto_cb.setChecked(self._proxy_config.lms_auto_connect)
        self._populate_lms_servers()

        if not self._proxy_config.lms_host and not self._proxy_config.lms_known_servers:
            QTimer.singleShot(500, self._on_lms_rescan)

        self._on_mode_changed()

    def _on_volume_changed(self, value: int):
        self._volume_label.setText(f"{value}%")
        if self._player:
            self._player.set_volume(value)

    def _on_mode_changed(self):
        is_manual = self._rb_manual.isChecked()
        self._manual_group.setEnabled(is_manual)

    def _populate_lms_servers(self):
        self._lms_server_combo.clear()
        seen = set()
        current = ""
        if self._proxy_config.lms_host:
            current = f"{self._proxy_config.lms_host}:{self._proxy_config.lms_port}"
            self._lms_server_combo.addItem(current)
            seen.add(current)
        for srv in self._proxy_config.lms_known_servers or []:
            entry = f"{srv['host']}:{srv['port']}"
            if entry not in seen:
                self._lms_server_combo.addItem(entry)
                seen.add(entry)
        self._lms_server_combo.addItem("Custom\u2026")
        idx = self._lms_server_combo.findText(current)
        if idx >= 0:
            self._lms_server_combo.setCurrentIndex(idx)

    def _on_lms_rescan(self):
        if not self._lms_service:
            logger.warning("LMS service not available")
            self._lms_status_label.setText("No LMS service available")
            return
        self._lms_rescan_btn.setEnabled(False)
        self._lms_status_label.setText("Scanning\u2026")
        self._lms_test_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            servers = self._lms_service.rescan_network()
            logger.info("LMS scan found %d servers: %s", len(servers), servers)
        except Exception as e:
            logger.error("LMS scan failed: %s", e)
            servers = []

        # Also directly probe known LMS address as fallback
        if not servers:
            try:
                from lms.discovery import probe_http
                direct = probe_http("192.168.1.90", 9000, timeout=2.0)
                if direct:
                    logger.info("Direct probe found LMS: %s", direct)
                    servers = [direct]
            except Exception as e:
                logger.error("Direct probe also failed: %s", e)

        known = self._proxy_config.lms_known_servers or []
        seen_hosts = {(s["host"], s["port"]) for s in known}
        for srv in servers:
            key = (srv["host"], srv["port"])
            if key not in seen_hosts:
                known.append(srv)
                seen_hosts.add(key)
        self._proxy_config.lms_known_servers = known
        self._populate_lms_servers()
        if servers:
            label = f"Found {len(servers)} server(s)"
            logger.info(label)
            self._lms_status_label.setText(label)
        else:
            msg = "No servers found"
            logger.warning(msg)
            self._lms_status_label.setText(msg)
        QApplication.processEvents()
        self._lms_rescan_btn.setEnabled(True)
        self._lms_test_btn.setEnabled(True)

    def _on_lms_test(self):
        text = self._lms_server_combo.currentText().strip()
        if not text or text == "Custom\u2026":
            self._lms_status_label.setText("Enter a server address first")
            return
        if ":" in text:
            host, _, port_str = text.partition(":")
            try:
                port = int(port_str)
            except ValueError:
                self._lms_status_label.setText("Invalid port")
                return
        else:
            host = text
            port = 9000
        self._lms_test_btn.setEnabled(False)
        self._lms_status_label.setText("Testing\u2026")
        self._lms_rescan_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            name = self._lms_service.test_server(host, port) if self._lms_service else None
            logger.info("LMS test %s:%d -> %s", host, port, name)
        except Exception as e:
            logger.error("LMS test failed: %s", e)
            name = None
        if name:
            self._lms_status_label.setText(f"\U0001f7e2 Connected \u2014 {name}")
        else:
            self._lms_status_label.setText("\u26ab Server unreachable")
        self._lms_test_btn.setEnabled(True)
        self._lms_rescan_btn.setEnabled(True)

    def _on_ok(self):
        mode_map = {0: "off", 1: "system", 2: "manual"}
        self._proxy_config.mode = mode_map[self._btn_group.checkedId()]
        self._proxy_config.server = self._server_edit.text().strip()
        self._proxy_config.port = self._port_spin.value()
        self._proxy_config.username = self._user_edit.text().strip()
        self._proxy_config.password = self._pwd_edit.text()
        self._proxy_config.workers = self._workers_spin.value()
        self._proxy_config.auto_play = self._auto_play_cb.isChecked()
        self._proxy_config.auto_start = self._auto_start_cb.isChecked()
        self._proxy_config.volume = self._volume_slider.value()
        self._proxy_config.output_device = self._device_combo.currentData()

        lms_text = self._lms_server_combo.currentText().strip()
        if lms_text and lms_text != "Custom\u2026":
            if ":" in lms_text:
                host, _, port_str = lms_text.partition(":")
                try:
                    self._proxy_config.lms_port = int(port_str)
                except ValueError:
                    self._proxy_config.lms_port = 9000
                self._proxy_config.lms_host = host
            else:
                self._proxy_config.lms_host = lms_text
                self._proxy_config.lms_port = 9000
        self._proxy_config.lms_player_name = self._lms_player_name.text().strip() or "TrayRadio"
        self._proxy_config.lms_auto_connect = self._lms_auto_cb.isChecked()

        set_auto_start(self._proxy_config.auto_start)
        self.accept()

    @property
    def proxy_config(self) -> ProxyConfig:
        return self._proxy_config
