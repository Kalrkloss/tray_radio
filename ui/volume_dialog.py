from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
)
from PyQt5.QtCore import Qt


class VolumeDialog(QDialog):
    def __init__(self, player, proxy_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Volume")
        self.setMinimumWidth(300)
        self._player = player
        self._proxy_config = proxy_config
        self._build_ui()
        self._volume_slider.setValue(proxy_config.volume)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_label = QLabel(f"{self._proxy_config.volume}%")
        self._volume_label.setAlignment(Qt.AlignCenter)
        self._volume_slider.valueChanged.connect(self._on_value_changed)

        layout.addWidget(self._volume_slider)
        layout.addWidget(self._volume_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_value_changed(self, value: int):
        self._volume_label.setText(f"{value}%")
        if self._player:
            self._player.set_volume(value)

    def _on_ok(self):
        self._proxy_config.volume = self._volume_slider.value()
        self.accept()
