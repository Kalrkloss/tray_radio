import uuid

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFormLayout, QMessageBox,
)
from PyQt5.QtCore import Qt

from playlist_manager import PlaylistManager, Stream


class AddStreamDialog(QDialog):
    def __init__(self, playlist_manager: PlaylistManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Stream")
        self.setMinimumWidth(400)
        self._pm = playlist_manager
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. My Cool Radio")
        form.addRow("Name:", self._name_edit)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("e.g. https://example.com/stream.mp3")
        form.addRow("URL:", self._url_edit)

        layout.addLayout(form)

        playlist_layout = QHBoxLayout()
        playlist_layout.addWidget(QLabel("Add to playlist:"))

        self._playlist_combo = QComboBox()
        self._refresh_playlist_combo()
        playlist_layout.addWidget(self._playlist_combo, 1)
        layout.addLayout(playlist_layout)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _refresh_playlist_combo(self):
        self._playlist_combo.clear()
        for i, pl in enumerate(self._pm.playlists):
            self._playlist_combo.addItem(pl.name, i)

    def _on_ok(self):
        name = self._name_edit.text().strip()
        url = self._url_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Please enter a stream name.")
            self._name_edit.setFocus()
            return
        if not url:
            QMessageBox.warning(self, "Validation", "Please enter a stream URL.")
            self._url_edit.setFocus()
            return

        pl_idx = self._playlist_combo.currentData()
        if pl_idx is None:
            QMessageBox.warning(self, "Validation", "No playlist selected.")
            return

        stream = Stream(
            uuid=f"manual-{uuid.uuid4().hex[:12]}",
            name=name,
            url=url,
        )

        if self._pm.add_stream(pl_idx, stream):
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Stream already exists in this playlist.")
