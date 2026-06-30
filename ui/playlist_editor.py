from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QInputDialog, QMessageBox, QSplitter, QAbstractItemView,
    QMenu, QLabel, QWidget,
)
from PyQt5.QtCore import Qt

from playlist_manager import PlaylistManager, Stream


class PlaylistEditorDialog(QDialog):
    def __init__(self, playlist_manager: PlaylistManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Playlist Editor")
        self.setMinimumSize(600, 400)
        self._pm = playlist_manager
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        left_widget = QVBoxLayout()
        left_label = QLabel("Playlists")
        left_widget.addWidget(left_label)

        self._playlist_list = QListWidget()
        self._playlist_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._playlist_list.customContextMenuRequested.connect(self._playlist_context_menu)
        self._playlist_list.currentRowChanged.connect(self._on_playlist_selected)
        left_widget.addWidget(self._playlist_list)

        pl_btn_layout = QHBoxLayout()
        self._btn_add_pl = QPushButton("+")
        self._btn_add_pl.setMaximumWidth(40)
        self._btn_add_pl.clicked.connect(self._add_playlist)
        self._btn_rename_pl = QPushButton("Rename")
        self._btn_rename_pl.clicked.connect(self._rename_playlist)
        self._btn_del_pl = QPushButton("Delete")
        self._btn_del_pl.clicked.connect(self._delete_playlist)
        pl_btn_layout.addWidget(self._btn_add_pl)
        pl_btn_layout.addWidget(self._btn_rename_pl)
        pl_btn_layout.addWidget(self._btn_del_pl)
        pl_btn_layout.addStretch()
        left_widget.addLayout(pl_btn_layout)

        left_container = QWidget()
        left_container.setLayout(left_widget)

        right_widget = QVBoxLayout()
        right_label = QLabel("Streams")
        right_widget.addWidget(right_label)

        self._stream_list = QListWidget()
        self._stream_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._stream_list.customContextMenuRequested.connect(self._stream_context_menu)
        right_widget.addWidget(self._stream_list)

        stream_btn_layout = QHBoxLayout()
        self._btn_remove = QPushButton("Remove")
        self._btn_remove.clicked.connect(self._remove_stream)
        self._btn_move = QPushButton("Move to...")
        self._btn_move.clicked.connect(self._move_stream)
        stream_btn_layout.addWidget(self._btn_remove)
        stream_btn_layout.addWidget(self._btn_move)
        stream_btn_layout.addStretch()
        right_widget.addLayout(stream_btn_layout)

        right_container = QWidget()
        right_container.setLayout(right_widget)

        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        layout.addWidget(splitter)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _refresh(self):
        self._playlist_list.blockSignals(True)
        self._playlist_list.clear()
        for pl in self._pm.playlists:
            item = QListWidgetItem(pl.name)
            self._playlist_list.addItem(item)
        if self._pm.current_playlist_index >= 0:
            self._playlist_list.setCurrentRow(self._pm.current_playlist_index)
        self._playlist_list.blockSignals(False)
        self._refresh_streams()

    def _refresh_streams(self):
        self._stream_list.clear()
        idx = self._playlist_list.currentRow()
        if 0 <= idx < len(self._pm.playlists):
            pl = self._pm.playlists[idx]
            cur_uuid = self._pm.current_stream_uuid
            for s in pl.streams:
                item = QListWidgetItem(s.name)
                if s.uuid == cur_uuid:
                    item.setIcon(self._stream_list.style().standardIcon(
                        self._stream_list.style().SP_MediaPlay
                    ))
                self._stream_list.addItem(item)

    def _on_playlist_selected(self, index: int):
        self._pm.current_playlist_index = index
        self._pm.save()
        self._refresh_streams()

    def _add_playlist(self):
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        if ok and name.strip():
            self._pm.create_playlist(name.strip())
            self._refresh()

    def _rename_playlist(self):
        idx = self._playlist_list.currentRow()
        if idx < 0:
            return
        old_name = self._pm.playlists[idx].name
        name, ok = QInputDialog.getText(
            self, "Rename Playlist", "New name:", text=old_name
        )
        if ok and name.strip():
            self._pm.rename_playlist(idx, name.strip())
            self._refresh()

    def _delete_playlist(self):
        idx = self._playlist_list.currentRow()
        if idx < 0:
            return
        reply = QMessageBox.question(
            self, "Delete Playlist",
            f'Delete playlist "{self._pm.playlists[idx].name}"?',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._pm.delete_playlist(idx)
            self._refresh()

    def _remove_stream(self):
        pl_idx = self._playlist_list.currentRow()
        s_idx = self._stream_list.currentRow()
        if pl_idx < 0 or s_idx < 0:
            return
        self._pm.remove_stream(pl_idx, s_idx)
        self._refresh_streams()

    def _move_stream(self):
        pl_idx = self._playlist_list.currentRow()
        s_idx = self._stream_list.currentRow()
        if pl_idx < 0 or s_idx < 0:
            return

        targets = []
        for i, pl in enumerate(self._pm.playlists):
            if i != pl_idx:
                targets.append((i, pl.name))

        if not targets:
            QMessageBox.information(self, "Move Stream", "No other playlists available.")
            return

        items = [f"{name}" for _, name in targets]
        choice, ok = QInputDialog.getItem(
            self, "Move Stream", "Target playlist:", items, 0, False
        )
        if ok and choice:
            for i, name in targets:
                if name == choice:
                    self._pm.move_stream(pl_idx, s_idx, i)
                    self._refresh_streams()
                    break

    def _playlist_context_menu(self, pos):
        idx = self._playlist_list.currentRow()
        if idx < 0:
            return
        menu = QMenu()
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        action = menu.exec_(self._playlist_list.mapToGlobal(pos))
        if action == rename_action:
            self._rename_playlist()
        elif action == delete_action:
            self._delete_playlist()

    def _stream_context_menu(self, pos):
        pl_idx = self._playlist_list.currentRow()
        s_idx = self._stream_list.currentRow()
        if pl_idx < 0 or s_idx < 0:
            return
        menu = QMenu()
        remove_action = menu.addAction("Remove")
        move_action = menu.addAction("Move to...")
        action = menu.exec_(self._stream_list.mapToGlobal(pos))
        if action == remove_action:
            self._remove_stream()
        elif action == move_action:
            self._move_stream()
