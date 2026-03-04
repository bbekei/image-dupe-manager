"""
ui/similarity_screen.py — Full-screen similarity review widget.

Registered in NavigationController as "similarity".
Left panel: QTreeView with SimilarityModel (groups + files).
Right panel: SimilarityComparePanel (detail for selected group).
Bottom bar: Stats + "Review Plan >>" button.

Plan reference: §S4.3.
"""

from datetime import datetime, timezone

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.similarity_selection import (
    SimilarityPreset,
    apply_similarity_preset,
    recommend_keeper,
)
from data.db import Database
from ui.similarity_compare import SimilarityComparePanel
from ui.similarity_model import (
    ROLE_GROUP_ID,
    ROLE_NODE_TYPE,
    SimilarityModel,
)


class SimilarityScreen(QWidget):
    """Similarity review screen with group tree and comparison panel.

    Signals:
        back_requested:    user wants to go back to dashboard
        review_requested:  user wants to proceed to Plan Review
        status_message:    status bar update
    """

    back_requested = pyqtSignal()
    review_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self._session_id: int | None = None
        self._model = SimilarityModel(parent=self)
        self._build_ui()

    def set_session_id(self, session_id: int | None) -> None:
        self._session_id = session_id

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(16, 8, 16, 8)

        back_btn = QPushButton(self.tr("\u2190 Back"))
        back_btn.clicked.connect(self.back_requested)
        top_bar.addWidget(back_btn)

        title = QLabel(self.tr("Similar Images"))
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        top_bar.addWidget(title)

        top_bar.addStretch()

        self._smart_btn = QPushButton(self.tr("Smart Select"))
        self._smart_btn.setToolTip(
            self.tr("Apply a preset to select files to keep/delete")
        )
        self._smart_btn.clicked.connect(self._on_smart_select)
        top_bar.addWidget(self._smart_btn)

        root.addLayout(top_bar)

        # Splitter: tree (left) + compare (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(False)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(
            QTreeView.SelectionMode.SingleSelection
        )
        self._tree.clicked.connect(self._on_tree_clicked)
        splitter.addWidget(self._tree)

        self._compare = SimilarityComparePanel()
        self._compare.keep_file.connect(self._on_keep_file)
        self._compare.delete_file.connect(self._on_delete_file)
        splitter.addWidget(self._compare)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.setContentsMargins(16, 8, 16, 8)

        self._stats_label = QLabel()
        self._stats_label.setStyleSheet("color: #6b7280;")
        bottom.addWidget(self._stats_label)

        bottom.addStretch()

        review_btn = QPushButton(self.tr("Review Plan \u00bb"))
        review_btn.clicked.connect(self.review_requested)
        bottom.addWidget(review_btn)

        root.addLayout(bottom)

    # ── Data loading ──────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload similarity groups from DB."""
        if self._session_id is None:
            return
        self._model.load_from_db(self._db, self._session_id)
        gc = self._model.group_count()
        fc = self._model.total_files()
        self._stats_label.setText(
            self.tr("{0} groups \u00b7 {1} files").format(gc, fc)
        )
        self._compare.clear()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    # ── Tree interaction ──────────────────────────────────────────────

    def _on_tree_clicked(self, index) -> None:
        node_type = self._model.data(index, ROLE_NODE_TYPE)
        if node_type == "file":
            # Navigate to parent group.
            index = index.parent()
            node_type = "group"

        if node_type != "group":
            return

        group_id = self._model.data(index, ROLE_GROUP_ID)
        if group_id is None:
            return

        # Fetch group members from DB.
        members = self._db.get_similarity_group_members(group_id)
        file_dicts = [dict(m) for m in members]

        if not file_dicts:
            self._compare.clear()
            return

        rec_id, rec_reason = recommend_keeper(file_dicts)

        display_files = []
        for m in file_dicts:
            display_files.append({
                "file_id": m["id"],
                "path": m.get("path", ""),
                "size": m.get("size", 0) or 0,
                "modified_at": m.get("modified_at", "") or "",
                "thumbnail_path": m.get("thumbnail_path", "") or "",
                "width": m.get("width", 0) or 0,
                "height": m.get("height", 0) or 0,
                "distance": m.get("distance", 0) or 0,
                "is_recommended": m["id"] == rec_id,
            })

        import os
        rec_name = ""
        for f in display_files:
            if f["file_id"] == rec_id:
                rec_name = os.path.basename(f["path"])
                break

        recommendation = self.tr("Recommendation: Keep {0} ({1})").format(
            rec_name, rec_reason
        )
        self._compare.show_group(display_files, recommendation)

    # ── File actions ──────────────────────────────────────────────────

    def _on_keep_file(self, file_id: int) -> None:
        if self._session_id is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        self._db.set_file_action(self._session_id, file_id, "keep", "file", now)
        self.status_message.emit(self.tr("Marked file {0} to keep").format(file_id))

    def _on_delete_file(self, file_id: int) -> None:
        if self._session_id is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        self._db.set_file_action(self._session_id, file_id, "delete", "file", now)
        self.status_message.emit(
            self.tr("Marked file {0} for deletion").format(file_id)
        )

    # ── Smart Select ──────────────────────────────────────────────────

    _PRESET_LABELS = [
        ("Keep Highest Resolution", SimilarityPreset.KEEP_HIGHEST_RESOLUTION),
        ("Keep Largest File", SimilarityPreset.KEEP_LARGEST_FILE),
        ("Keep Newest", SimilarityPreset.KEEP_NEWEST),
        ("Keep Oldest", SimilarityPreset.KEEP_OLDEST),
        ("Keep Shortest Path", SimilarityPreset.KEEP_SHORTEST_PATH),
    ]

    def _on_smart_select(self) -> None:
        """Show preset chooser and apply to all similarity groups."""
        if self._session_id is None:
            return
        labels = [self.tr(label) for label, _ in self._PRESET_LABELS]
        choice, ok = QInputDialog.getItem(
            self,
            self.tr("Smart Select"),
            self.tr("Choose which file to keep in each group:"),
            labels,
            current=0,
            editable=False,
        )
        if not ok:
            return
        idx = labels.index(choice)
        preset = self._PRESET_LABELS[idx][1]
        keep, delete = apply_similarity_preset(
            self._db, self._session_id, preset,
        )
        self.status_message.emit(
            self.tr("Smart Select: {0} keep, {1} delete").format(keep, delete)
        )
        self.refresh()
