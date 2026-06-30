from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt5.QtGui import QFont, QColor, QPainter, QBrush, QPen


class ToastNotification(QWidget):
    def __init__(self, title: str, message: str, duration_ms: int = 6000):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.Tool | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._title = title
        self._message = message
        self._duration = duration_ms

        self._build_ui()
        self._position()

        self.show()
        self._anim_in = None
        self._anim_out = None
        self._animate_in()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        title_lbl = QLabel(self._title)
        title_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        title_lbl.setStyleSheet("color: #ffffff;")
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        msg_lbl = QLabel(self._message)
        msg_lbl.setFont(QFont("Segoe UI", 9))
        msg_lbl.setStyleSheet("color: #cccccc;")
        msg_lbl.setWordWrap(True)
        msg_lbl.setMaximumWidth(320)
        layout.addWidget(msg_lbl)

        self.setFixedWidth(360)
        self.adjustSize()

    def _position(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 12
            y = geo.bottom() - self.height() - 12
            self.move(x, y)

    def _animate_in(self):
        self.setWindowOpacity(0.0)
        self._anim_in = QPropertyAnimation(self, b"windowOpacity")
        self._anim_in.setDuration(300)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.start()
        QTimer.singleShot(self._duration, self._animate_out)

    def _animate_out(self):
        self._anim_out = QPropertyAnimation(self, b"windowOpacity")
        self._anim_out.setDuration(300)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.finished.connect(self.close)
        self._anim_out.start()

    def mousePressEvent(self, event):
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(32, 32, 32, 230)))
        painter.setPen(QPen(QColor(64, 64, 64), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
