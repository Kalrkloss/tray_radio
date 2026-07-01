import logging
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSlider,
    QGroupBox, QMessageBox, QWidget,
)
from PyQt5.QtCore import Qt, QTimer

from lms.models import LmsPlayer

logger = logging.getLogger(__name__)


class LmsDialog(QDialog):
    def __init__(self, lms_service, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lyrion Music Server")
        self.setMinimumSize(600, 400)
        self._lms = lms_service
        self._players: list[LmsPlayer] = []
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        status_layout = QHBoxLayout()
        self._status_label = QLabel("Disconnected")
        self._status_label.setStyleSheet("font-weight: bold;")
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()
        status_layout.addWidget(self._connect_btn)
        status_layout.addWidget(self._refresh_btn)
        layout.addLayout(status_layout)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["", "Name", "Model", "IP", "Volume", "Sync Group"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.MultiSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnWidth(0, 30)
        layout.addWidget(self._table)

        ctrl_layout = QHBoxLayout()
        self._play_btn = QPushButton("Play")
        self._play_btn.clicked.connect(self._on_play)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        self._sync_btn = QPushButton("Sync Selected")
        self._sync_btn.clicked.connect(self._on_sync)
        self._unsync_btn = QPushButton("Unsync")
        self._unsync_btn.clicked.connect(self._on_unsync)
        ctrl_layout.addWidget(self._play_btn)
        ctrl_layout.addWidget(self._stop_btn)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self._sync_btn)
        ctrl_layout.addWidget(self._unsync_btn)
        layout.addLayout(ctrl_layout)

        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

    def _on_connect(self):
        if not self._lms:
            return
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting...")
        self._lms.reconnect()
        QTimer.singleShot(1000, self._refresh)

    def _refresh(self):
        if not self._lms:
            return
        connected = self._lms.is_connected if self._lms else False
        if connected:
            self._status_label.setText("\U0001f7e2 Connected")
            self._status_label.setStyleSheet("font-weight: bold; color: green;")
            self._connect_btn.setEnabled(False)
            self._connect_btn.setText("Connect")
            self._players = self._lms.get_players()
            self._populate_table()
        else:
            self._status_label.setText("\u26ab Disconnected")
            self._status_label.setStyleSheet("font-weight: bold;")
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("Connect")
            self._players = []
            self._table.setRowCount(0)

    def _populate_table(self):
        self._table.setRowCount(0)
        for player in self._players:
            row = self._table.rowCount()
            self._table.insertRow(row)
            cb = QTableWidgetItem("")
            cb.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb.setCheckState(Qt.Unchecked)
            if player.sync_master:
                cb.setText("\U0001f517")
                cb.setToolTip(f"Synced to {player.sync_master}")
            elif player.sync_slaves:
                cb.setText("\U0001f517")
                cb.setToolTip(f"Master of {len(player.sync_slaves)} slave(s)")
            else:
                cb.setCheckState(Qt.Unchecked)
            self._table.setItem(row, 0, cb)

            name_item = QTableWidgetItem(player.name)
            name_item.setData(Qt.UserRole, player.playerid)
            self._table.setItem(row, 1, name_item)

            self._table.setItem(row, 2, QTableWidgetItem(player.model))
            self._table.setItem(row, 3, QTableWidgetItem(player.ip))

            vol_layout = QHBoxLayout()
            vol_slider = QSlider(Qt.Horizontal)
            vol_slider.setRange(0, 100)
            vol_slider.setValue(player.volume)
            vol_slider.valueChanged.connect(lambda v, pid=player.playerid: self._on_volume_changed(pid, v))
            vol_label = QLabel(f"{player.volume}%")
            vol_slider.valueChanged.connect(lambda v, lbl=vol_label: lbl.setText(f"{v}%"))
            vol_widget = QWidget()
            vol_widget.setLayout(vol_layout)
            vol_layout.addWidget(vol_slider)
            vol_layout.addWidget(vol_label)
            self._table.setCellWidget(row, 4, vol_widget)

            sync_text = "Master" if player.is_master else f"Slave of {player.sync_master}"
            self._table.setItem(row, 5, QTableWidgetItem(sync_text))

    def _get_selected_ids(self) -> list[str]:
        ids = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item:
                cb = self._table.item(row, 0)
                if cb and cb.checkState() == Qt.Checked:
                    ids.append(item.data(Qt.UserRole))
        if not ids:
            current = self._table.currentRow()
            if current >= 0:
                item = self._table.item(current, 1)
                if item:
                    ids.append(item.data(Qt.UserRole))
        return ids

    def _on_play(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        if self._lms and self._lms.cli and self._lms.cli.is_connected:
            for pid in ids:
                self._lms.cli.player_play(pid)

    def _on_stop(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        if self._lms and self._lms.cli and self._lms.cli.is_connected:
            for pid in ids:
                self._lms.cli.player_stop(pid)

    def _on_sync(self):
        ids = self._get_selected_ids()
        if len(ids) < 2:
            QMessageBox.information(self, "Sync", "Select at least 2 players to sync")
            return
        master = ids[0]
        if self._lms and self._lms.cli and self._lms.cli.is_connected:
            for pid in ids[1:]:
                self._lms.cli.player_sync(pid, master)
            QTimer.singleShot(500, self._refresh)

    def _on_unsync(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        if self._lms and self._lms.cli and self._lms.cli.is_connected:
            for pid in ids:
                self._lms.cli.player_unsync(pid)
            QTimer.singleShot(500, self._refresh)

    def _on_volume_changed(self, player_id: str, volume: int):
        if self._lms and self._lms.cli and self._lms.cli.is_connected:
            self._lms.cli.player_volume(player_id, volume)
