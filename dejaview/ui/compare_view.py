"""
ui/compare_view.py — Side-by-side duplicate comparison (plan §Dev Phases Phase 4, Req 4.4 + 4.5).

Shows all files sharing the same pixel_hash as tiles laid out side by side.
Each tile displays a 400×400 thumbnail, file metadata, and inline action buttons.

Module ownership (plan §Architecture):
  - All staging logic lives here.
  - Reads/writes the ``actions`` table via db.py.
  - File operations (delete, rename) execute here after confirmation.
  - Thumbnail cleanup: calls db.cleanup_orphaned_thumbnails() and os.remove().

Signals:
  actions_confirmed  — emitted after a batch confirmation so ResultsPanel can refresh.
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rename validation (plan §Security — rename path traversal)
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r'^[^\\/:*?"<>|.][^\\/:*?"<>|]{0,253}$')


def _validate_rename(new_name: str) -> bool:
    """Return True iff *new_name* is a safe bare filename (no path component)."""
    return bool(_SAFE_NAME_RE.match(new_name))


# ---------------------------------------------------------------------------
# Tile widget — one per file in the duplicate group
# ---------------------------------------------------------------------------

class _FileTile(QWidget):
    """
    Single tile in the compare view (plan §UI Layout — Compare View).

    Displays: thumbnail, path, size, date, and action buttons.
    ``is_local=False`` hides action buttons entirely (remote/peer tiles,
    plan §Workflow 4 — remote tiles are informational only).
    """

    keep_clicked = pyqtSignal(int)    # file_id
    delete_clicked = pyqtSignal(int)  # file_id
    rename_requested = pyqtSignal(int, str)  # file_id, new_name

    def __init__(
        self,
        file_id: int,
        file_path: str,
        size: int,
        modified_at: str,
        thumbnail_path: Optional[str],
        is_local: bool = True,
        peer_name: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._file_id = file_id
        self._file_path = file_path
        self._is_local = is_local
        self._peer_name = peer_name

        self.setFixedWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Thumbnail (plan §Thumbnail caching — 400×400).
        self._thumb_label = QLabel(self)
        self._thumb_label.setFixedSize(240, 240)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("border: 1px solid #ccc; background: #f0f0f0;")
        if thumbnail_path and os.path.isfile(thumbnail_path):
            pix = QPixmap(thumbnail_path)
            self._thumb_label.setPixmap(
                pix.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._thumb_label.setText(self.tr("No thumbnail"))
        layout.addWidget(self._thumb_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Metadata labels.
        if is_local:
            self._path_label = QLabel(file_path, self)
        else:
            display = peer_name or self.tr("Remote")
            self._path_label = QLabel(f"{display}", self)
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._path_label)

        if is_local:
            fname = os.path.basename(file_path)
            self._name_label = QLabel(fname, self)
            self._name_label.setStyleSheet("font-weight: bold;")
            layout.addWidget(self._name_label)

        size_str = self._format_size(size) if size else "?"
        self._size_label = QLabel(size_str, self)
        layout.addWidget(self._size_label)

        date_str = modified_at[:10] if modified_at and len(modified_at) >= 10 else "?"
        self._date_label = QLabel(date_str, self)
        layout.addWidget(self._date_label)

        # Action buttons — only for local tiles (plan §Workflow 4).
        if is_local:
            btn_row = QHBoxLayout()
            self._keep_btn = QPushButton(self.tr("KEEP"), self)
            self._keep_btn.setObjectName("keep_btn")
            self._del_btn = QPushButton(self.tr("DEL"), self)
            self._del_btn.setObjectName("del_btn")
            self._rename_btn = QPushButton(self.tr("Rename"), self)
            self._rename_btn.setObjectName("rename_btn")
            btn_row.addWidget(self._keep_btn)
            btn_row.addWidget(self._del_btn)
            btn_row.addWidget(self._rename_btn)
            layout.addLayout(btn_row)

            # Inline rename field (hidden by default).
            self._rename_edit = QLineEdit(self)
            self._rename_edit.setPlaceholderText(self.tr("New filename…"))
            self._rename_edit.setVisible(False)
            layout.addWidget(self._rename_edit)

            self._keep_btn.clicked.connect(lambda: self.keep_clicked.emit(self._file_id))
            self._del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._file_id))
            self._rename_btn.clicked.connect(self._toggle_rename)
            self._rename_edit.returnPressed.connect(self._submit_rename)
        else:
            # Peer label badge (plan §Workflow 4 — remote tiles show peer name).
            if peer_name:
                peer_label = QLabel(self.tr("({0}'s copy)").format(peer_name), self)
                peer_label.setObjectName("peer_label")
                peer_label.setStyleSheet("color: #666; font-style: italic;")
                layout.addWidget(peer_label)
            ro_label = QLabel(self.tr("(read only)"), self)
            ro_label.setObjectName("read_only_label")
            ro_label.setStyleSheet("color: #999;")
            layout.addWidget(ro_label)

        layout.addStretch()

    # ── Public helpers ────────────────────────────────────────────────────

    @property
    def file_id(self) -> int:
        return self._file_id

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def is_local(self) -> bool:
        return self._is_local

    def set_marked(self, action: str) -> None:
        """Visually mark tile as KEEP or DEL candidate."""
        if action == "keep":
            self.setStyleSheet("background-color: #e6ffe6; border: 2px solid #4caf50;")
        elif action == "delete":
            self.setStyleSheet("background-color: #ffe6e6; border: 2px solid #f44336;")
        else:
            self.setStyleSheet("")

    # ── Private slots ─────────────────────────────────────────────────────

    def _toggle_rename(self) -> None:
        self._rename_edit.setVisible(not self._rename_edit.isVisible())
        if self._rename_edit.isVisible():
            basename = os.path.basename(self._file_path)
            self._rename_edit.setText(basename)
            self._rename_edit.setFocus()
            self._rename_edit.selectAll()

    def _submit_rename(self) -> None:
        new_name = self._rename_edit.text().strip()
        if not _validate_rename(new_name):
            QMessageBox.warning(
                self,
                self.tr("Invalid filename"),
                self.tr("The filename is invalid. Use a simple name without path separators."),
            )
            return
        self._rename_edit.setVisible(False)
        self.rename_requested.emit(self._file_id, new_name)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"


# ---------------------------------------------------------------------------
# Batch rules dialog (plan §Workflow 3 — Batch rules...)
# ---------------------------------------------------------------------------

class _BatchRulesDialog(QDialog):
    """Modal dialog offering automatic KEEP/DEL rules for a duplicate group."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Batch Rules"))
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Apply an automatic rule to this group:"), self))

        self._keep_oldest_btn = QPushButton(self.tr("Keep oldest, delete rest"), self)
        self._keep_oldest_btn.setObjectName("keep_oldest_btn")
        self._keep_largest_btn = QPushButton(self.tr("Keep largest, delete rest"), self)
        self._keep_largest_btn.setObjectName("keep_largest_btn")
        self._cancel_btn = QPushButton(self.tr("Cancel"), self)

        layout.addWidget(self._keep_oldest_btn)
        layout.addWidget(self._keep_largest_btn)
        layout.addWidget(self._cancel_btn)

        self._result: Optional[str] = None
        self._keep_oldest_btn.clicked.connect(lambda: self._select("keep_oldest"))
        self._keep_largest_btn.clicked.connect(lambda: self._select("keep_largest"))
        self._cancel_btn.clicked.connect(self.reject)

    def _select(self, rule: str) -> None:
        self._result = rule
        self.accept()

    @property
    def selected_rule(self) -> Optional[str]:
        return self._result


# ---------------------------------------------------------------------------
# Confirmation dialog (plan §Workflow 3 — confirmation dialog)
# ---------------------------------------------------------------------------

class _ConfirmDialog(QDialog):
    """Lists all staged deletes/renames for user review before execution."""

    def __init__(self, staged_actions: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Confirm Actions"))
        self.setMinimumSize(500, 350)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            self.tr("The following actions will be performed:"), self
        ))

        self._list = QListWidget(self)
        for action in staged_actions:
            action_type = action["action_type"]
            path = action["path"]
            detail = action.get("detail", "")
            if action_type == "delete":
                text = self.tr("DELETE: {0}").format(path)
            elif action_type == "rename":
                text = self.tr("RENAME: {0} → {1}").format(path, detail)
            elif action_type == "keep":
                text = self.tr("KEEP: {0}").format(path)
            else:
                text = f"{action_type}: {path}"
            self._list.addItem(QListWidgetItem(text))
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ---------------------------------------------------------------------------
# CompareView — main widget
# ---------------------------------------------------------------------------

class CompareView(QWidget):
    """
    Side-by-side comparison of a duplicate group (plan §UI Layout — Compare View).

    Opened by ResultsPanel.compare_view_requested(pixel_hash).
    Shows all files sharing *pixel_hash* as scrollable tiles.
    """

    actions_confirmed = pyqtSignal()  # triggers ResultsPanel refresh
    closed = pyqtSignal()             # so MainWindow can restore results panel

    def __init__(
        self,
        db: Database,
        session_id: int,
        pixel_hash: str,
        session_folders: list[str],
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id
        self._pixel_hash = pixel_hash
        self._session_folders = [Path(f) for f in session_folders]
        self._tiles: list[_FileTile] = []

        self._build_ui()
        self._populate_tiles()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # Header (plan §UI Layout — "DUPLICATE GROUP (N files · SHA: ...)")
        short_hash = self._pixel_hash[:8] if self._pixel_hash else "?"
        self._header = QLabel(self)
        self._header.setObjectName("compare_header")
        self._header.setStyleSheet("font-size: 14px; font-weight: bold;")
        outer.addWidget(self._header)

        # Scrollable tile area.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._tile_container = QWidget()
        self._tile_layout = QHBoxLayout(self._tile_container)
        self._tile_layout.setContentsMargins(0, 0, 0, 0)
        self._tile_layout.setSpacing(12)
        self._tile_layout.addStretch()
        scroll.setWidget(self._tile_container)
        outer.addWidget(scroll, stretch=1)

        # Group-level action bar (plan §Workflow 3 — group-level actions).
        action_row = QHBoxLayout()
        self._apply_btn = QPushButton(self.tr("Apply to all in group"), self)
        self._apply_btn.setObjectName("apply_btn")
        self._batch_btn = QPushButton(self.tr("Batch rules\u2026"), self)
        self._batch_btn.setObjectName("batch_btn")
        self._confirm_btn = QPushButton(self.tr("Review && Confirm\u2026"), self)
        self._confirm_btn.setObjectName("confirm_btn")
        self._close_btn = QPushButton(self.tr("Close"), self)
        self._close_btn.setObjectName("close_btn")

        action_row.addWidget(self._apply_btn)
        action_row.addWidget(self._batch_btn)
        action_row.addStretch()
        action_row.addWidget(self._confirm_btn)
        action_row.addWidget(self._close_btn)
        outer.addLayout(action_row)

        self._apply_btn.clicked.connect(self._on_apply_all)
        self._batch_btn.clicked.connect(self._on_batch_rules)
        self._confirm_btn.clicked.connect(self._on_confirm)
        self._close_btn.clicked.connect(self._on_close)

    def _populate_tiles(self) -> None:
        # Local files in this duplicate group.
        local_files = self._db.get_files_by_pixel_hash(self._session_id, self._pixel_hash)

        # Remote matches (plan §Workflow 4 — cross-library).
        remote_matches = self._db.get_cross_library_matches(self._session_id)
        remote_for_hash = [r for r in remote_matches if r["pixel_hash"] == self._pixel_hash]

        file_count = len(local_files) + len(remote_for_hash)
        short_hash = self._pixel_hash[:8] if self._pixel_hash else "?"
        self._header.setText(
            self.tr("DUPLICATE GROUP ({0} files \u00b7 SHA: {1}\u2026)").format(
                file_count, short_hash
            )
        )

        # Remove stretch before adding tiles (re-add at end).
        stretch_item = self._tile_layout.takeAt(self._tile_layout.count() - 1)

        for f in local_files:
            tile = _FileTile(
                file_id=f["id"],
                file_path=f["path"],
                size=f["size"] or 0,
                modified_at=f["modified_at"] or "",
                thumbnail_path=f["thumbnail_path"],
                is_local=True,
                parent=self._tile_container,
            )
            tile.keep_clicked.connect(self._on_keep)
            tile.delete_clicked.connect(self._on_delete)
            tile.rename_requested.connect(self._on_rename)
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        for r in remote_for_hash:
            tile = _FileTile(
                file_id=-1,  # not a real local file_id
                file_path=r["remote_path"] or r["remote_filename"] or "?",
                size=r["remote_size"] or 0,
                modified_at=r["remote_modified_at"] or "",
                thumbnail_path=None,
                is_local=False,
                peer_name=r["username"],
                parent=self._tile_container,
            )
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        self._tile_layout.addStretch()

    # ── Tile count helper (for tests) ─────────────────────────────────────

    @property
    def tiles(self) -> list[_FileTile]:
        return list(self._tiles)

    @property
    def local_tiles(self) -> list[_FileTile]:
        return [t for t in self._tiles if t.is_local]

    @property
    def remote_tiles(self) -> list[_FileTile]:
        return [t for t in self._tiles if not t.is_local]

    # ── Per-file action slots ─────────────────────────────────────────────

    @pyqtSlot(int)
    def _on_keep(self, file_id: int) -> None:
        """Stage KEEP for this file; mark others as DEL candidates (plan §Workflow 3)."""
        self._clear_staged_for_group()
        self._db.stage_action(file_id, "keep")
        for tile in self.local_tiles:
            if tile.file_id == file_id:
                tile.set_marked("keep")
            else:
                self._db.stage_action(tile.file_id, "delete")
                tile.set_marked("delete")

    @pyqtSlot(int)
    def _on_delete(self, file_id: int) -> None:
        """Stage DELETE for this file only."""
        self._db.stage_action(file_id, "delete")
        for tile in self.local_tiles:
            if tile.file_id == file_id:
                tile.set_marked("delete")

    @pyqtSlot(int, str)
    def _on_rename(self, file_id: int, new_name: str) -> None:
        """Stage RENAME for this file (plan §Security — rename target validation)."""
        if not _validate_rename(new_name):
            return
        self._db.stage_action(file_id, "rename", detail=new_name)

    # ── Group-level actions ───────────────────────────────────────────────

    @pyqtSlot()
    def _on_apply_all(self) -> None:
        """Apply current KEEP/DEL markings to all files in the group at once.

        If no file is marked KEEP yet, this is a no-op.
        """
        staged = self._db.get_staged_actions(self._session_id)
        kept_ids = {a["file_id"] for a in staged if a["action_type"] == "keep"}
        if not kept_ids:
            return
        for tile in self.local_tiles:
            if tile.file_id not in kept_ids:
                # Check if already staged as delete.
                already = any(
                    a["file_id"] == tile.file_id and a["action_type"] == "delete"
                    for a in staged
                )
                if not already:
                    self._db.stage_action(tile.file_id, "delete")
                    tile.set_marked("delete")

    @pyqtSlot()
    def _on_batch_rules(self) -> None:
        """Open batch rules dialog (plan §Workflow 3 — Batch rules...)."""
        dlg = _BatchRulesDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rule = dlg.selected_rule
        if rule is None:
            return

        self._clear_staged_for_group()

        local_files = self._db.get_files_by_pixel_hash(self._session_id, self._pixel_hash)
        if not local_files:
            return

        if rule == "keep_oldest":
            keeper = min(local_files, key=lambda f: f["modified_at"] or "")
        elif rule == "keep_largest":
            keeper = max(local_files, key=lambda f: f["size"] or 0)
        else:
            return

        self._db.stage_action(keeper["id"], "keep")
        for f in local_files:
            if f["id"] != keeper["id"]:
                self._db.stage_action(f["id"], "delete")

        # Update tile visuals.
        for tile in self.local_tiles:
            if tile.file_id == keeper["id"]:
                tile.set_marked("keep")
            else:
                tile.set_marked("delete")

    # ── Confirmation & execution ──────────────────────────────────────────

    @pyqtSlot()
    def _on_confirm(self) -> None:
        """Show confirmation dialog, then execute staged actions (plan §Workflow 3)."""
        staged = self._db.get_staged_actions(self._session_id)
        if not staged:
            QMessageBox.information(
                self, self.tr("No actions"), self.tr("No actions have been staged yet.")
            )
            return

        action_list = [
            {
                "action_type": a["action_type"],
                "path": a["path"],
                "detail": a["detail"],
                "action_id": a["id"],
                "file_id": a["file_id"],
            }
            for a in staged
        ]

        dlg = _ConfirmDialog(action_list, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._execute_actions(action_list)

    def _execute_actions(self, action_list: list[dict]) -> None:
        """
        Execute confirmed actions: delete files, rename files, update DB.
        Plan §Post-Action Cleanup + §Security — confirmed-delete path validation.
        """
        now = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        for action in action_list:
            action_type = action["action_type"]
            action_id = action["action_id"]
            file_id = action["file_id"]
            file_path = action["path"]

            if action_type == "delete":
                if not self._path_within_scope(file_path):
                    errors.append(self.tr("Path outside scan scope: {0}").format(file_path))
                    continue
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except OSError as e:
                    errors.append(f"{file_path}: {e}")
                    continue
                self._db.update_file_status(file_id, "deleted")
                self._db.confirm_action(action_id, now)

            elif action_type == "rename":
                new_name = action.get("detail", "")
                if not _validate_rename(new_name):
                    errors.append(self.tr("Invalid rename target: {0}").format(new_name))
                    continue
                src = Path(file_path)
                dest = src.parent / new_name
                if not self._path_within_scope(str(src)):
                    errors.append(self.tr("Path outside scan scope: {0}").format(file_path))
                    continue
                try:
                    os.rename(str(src), str(dest))
                except OSError as e:
                    errors.append(f"{file_path}: {e}")
                    continue
                self._db.update_file_path(file_id, str(dest))
                self._db.update_file_status(file_id, "renamed")
                self._db.confirm_action(action_id, now)

            elif action_type == "keep":
                self._db.confirm_action(action_id, now)

        # Orphan thumbnail cleanup (plan §Post-Action Cleanup).
        orphans = self._db.cleanup_orphaned_thumbnails()
        for thumb_path in orphans:
            try:
                if os.path.isfile(thumb_path):
                    os.remove(thumb_path)
            except OSError:
                pass  # non-critical

        if errors:
            QMessageBox.warning(
                self,
                self.tr("Some actions failed"),
                "\n".join(errors),
            )

        self.actions_confirmed.emit()

    # ── Security: path scope check ────────────────────────────────────────

    def _path_within_scope(self, file_path: str) -> bool:
        """
        Verify resolved path falls within a session_folders root
        (plan §Security — confirmed-delete path validation).
        """
        try:
            resolved = Path(file_path).resolve()
        except (OSError, ValueError):
            return False
        for root in self._session_folders:
            try:
                resolved.relative_to(root.resolve())
                return True
            except ValueError:
                continue
        return False

    # ── Helpers ───────────────────────────────────────────────────────────

    def _clear_staged_for_group(self) -> None:
        """Remove all staged (unconfirmed) actions for files in this group."""
        staged = self._db.get_staged_actions(self._session_id)
        local_ids = {t.file_id for t in self.local_tiles}
        for a in staged:
            if a["file_id"] in local_ids:
                # Delete the staged action row.
                self._db.conn.execute("DELETE FROM actions WHERE id = ?", (a["id"],))
        self._db.conn.commit()
        for tile in self.local_tiles:
            tile.set_marked("")

    @pyqtSlot()
    def _on_close(self) -> None:
        self.closed.emit()
