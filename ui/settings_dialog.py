from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QRadioButton, QButtonGroup, QPushButton, QGroupBox, QFormLayout,
    QCheckBox, QMessageBox,
)
from PyQt5.QtCore import Qt

from proxy import ProxyConfig, detect_system_proxy, get_system_pac_url, get_system_auto_detect, set_auto_start


class SettingsDialog(QDialog):
    def __init__(self, proxy_config: ProxyConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proxy Settings")
        self.setMinimumWidth(400)
        self._proxy_config = proxy_config
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

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

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
        self._on_mode_changed()

    def _on_mode_changed(self):
        is_manual = self._rb_manual.isChecked()
        self._manual_group.setEnabled(is_manual)

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
        set_auto_start(self._proxy_config.auto_start)
        self.accept()

    @property
    def proxy_config(self) -> ProxyConfig:
        return self._proxy_config
