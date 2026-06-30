from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap

GITHUB_URL = "https://github.com/Kalrkloss/tray_radio"

class AboutDialog(QDialog):
    _instance = None

    @classmethod
    def show_modal(cls):
        if cls._instance is not None and cls._instance.isVisible():
            cls._instance.raise_()
            cls._instance.activateWindow()
            return
        dialog = cls()
        dialog.finished.connect(lambda: setattr(cls, "_instance", None))
        cls._instance = dialog
        dialog.exec_()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Tray Radio")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(380, 260)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        title_lbl = QLabel("Tray Radio")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        ver_lbl = QLabel("Version 1.0")
        ver_lbl.setFont(QFont("Segoe UI", 10))
        ver_lbl.setAlignment(Qt.AlignCenter)
        ver_lbl.setStyleSheet("color: #888;")
        layout.addWidget(ver_lbl)

        desc_lbl = QLabel(
            "A Windows system tray internet radio player.\n"
            "Browse thousands of stations, manage playlists, "
            "and discover new music."
        )
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)

        layout.addSpacing(8)

        link_lbl = QLabel(f'<a href="{GITHUB_URL}" style="color: #4a9eff;">{GITHUB_URL}</a>')
        link_lbl.setOpenExternalLinks(True)
        link_lbl.setAlignment(Qt.AlignCenter)
        link_lbl.setFont(QFont("Segoe UI", 9))
        layout.addWidget(link_lbl)

        bugs_lbl = QLabel("Report bugs and suggest features on GitHub")
        bugs_lbl.setFont(QFont("Segoe UI", 8))
        bugs_lbl.setAlignment(Qt.AlignCenter)
        bugs_lbl.setStyleSheet("color: #aaa;")
        layout.addWidget(bugs_lbl)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
