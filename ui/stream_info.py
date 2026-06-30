import io

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from playlist_manager import Stream
from icon_generator import fetch_logo


class StreamInfoDialog(QDialog):
    def __init__(self, stream: Stream, current_song: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Now Playing")
        self.setMinimumWidth(350)
        self._stream = stream
        self._current_song = current_song
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        logo = fetch_logo(self._stream.favicon)
        if logo:
            logo = logo.resize((80, 80))
            buf = io.BytesIO()
            logo.save(buf, format="PNG")
            qp = QPixmap()
            qp.loadFromData(buf.getvalue())
            logo_label = QLabel()
            logo_label.setPixmap(qp)
            logo_label.setFixedSize(80, 80)
            top_layout.addWidget(logo_label)

        info_layout = QVBoxLayout()
        self._name_label = QLabel(self._stream.name)
        self._name_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self._name_label.setWordWrap(True)
        info_layout.addWidget(self._name_label)

        self._song_label = QLabel(self._current_song or "(no song info)")
        self._song_label.setStyleSheet("font-size: 12px; color: #555;")
        self._song_label.setWordWrap(True)
        info_layout.addWidget(self._song_label)

        top_layout.addLayout(info_layout)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        desc_parts = []
        if self._stream.tags:
            desc_parts.append(f"Tags: {self._stream.tags}")
        if self._stream.country:
            desc_parts.append(f"Country: {self._stream.country}")
        if self._stream.language:
            desc_parts.append(f"Language: {self._stream.language}")
        if self._stream.codec and self._stream.bitrate:
            desc_parts.append(f"Format: {self._stream.codec} / {self._stream.bitrate} kbps")
        elif self._stream.codec:
            desc_parts.append(f"Format: {self._stream.codec}")

        if desc_parts:
            desc_label = QLabel("\n".join(desc_parts))
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("font-size: 11px; color: #777;")
            layout.addWidget(desc_label)

        if self._stream.homepage:
            url_label = QLabel(f'<a href="{self._stream.homepage}">{self._stream.homepage}</a>')
            url_label.setOpenExternalLinks(True)
            url_label.setWordWrap(True)
            layout.addWidget(url_label)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def update_song(self, song: str):
        self._current_song = song
        self._song_label.setText(song or "(no song info)")
