"""
ui/results_panel.py — Results tree view (plan §Dev Phases Phase 3, Req 4.3).

Shows all scanned files in their original directory tree structure.
Filter bar: All | Duplicates Only (Cross-Library added in Phase 5).
Duplicate badges: "● DUPLICATE" on files that share a pixel_hash.

UI update rate-limiting (plan §Resource Usage — UI update rate-limiting):
  Incoming hash_complete signals are queued; the tree refreshes at most once
  every 200 ms via a QTimer debounce.  file_discovered signals during Pass 1
  also go through the debounce queue.

Emits compare_view_requested(str pixel_hash) when a duplicate file is clicked.
"""

import logging
from typing import Optional

from PyQt6.QtCore import (
    QModelIndex,
    Qt,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QStandardItem
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

# Re-export from results_model for backward compatibility.
from ui.results_model import (  # noqa: F401
    ROLE_FILE_ID,
    ROLE_FILE_PATH,
    ROLE_PIXEL_HASH,
    ROLE_IS_DUPLICATE,
    ROLE_NODE_TYPE,
    ROLE_IS_CROSS_LIBRARY,
    ROLE_IS_FOLDER_DUPLICATED,
    ROLE_FOLDER_FILE_COUNT,
    ROLE_FOLDER_DUP_COUNT,
    ROLE_ACTION,
    ROLE_HAS_DECISION,
    ROLE_IS_MASTER,
    FILTER_ALL,
    FILTER_DUPLICATES_ONLY,
    FILTER_CROSS_LIBRARY,
    DuplicateFilterProxy,
    ResultsTreeModel,
    ViewState,
    _DEBOUNCE_MS,
    _DEFAULT_INDENT,
    _MIN_INDENT,
)
from ui.cluster_model import ClusterModel

log = logging.getLogger(__name__)

# Backward-compatible aliases for internal names used by old imports.
_DuplicateFilterProxy = DuplicateFilterProxy
_ViewState = ViewState


class ResultsPanel(QWidget):
    """
    Right pane: folder tree with filters and duplicate badges (plan §UI Layout).
    """

    compare_view_requested = pyqtSignal(str)  # pixel_hash
    compare_folder_requested = pyqtSignal(str)  # folder_path

    def __init__(self, db: Database, session_id: int | None = None, parent=None,
                 perf_monitor=None, tree_model: ResultsTreeModel | None = None):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id
        self._perf = perf_monitor  # None = no telemetry overhead

        # Shared tree model (or create a private one).
        self._tree_model = tree_model or ResultsTreeModel()
        self._model = self._tree_model.model

        # Phase 5: Cluster view model (loaded on-demand).
        self._cluster_model = ClusterModel()
        self._view_mode = "tree"  # "tree" or "cluster"

        # Pending updates queued by scanner signals, flushed by debounce timer.
        self._pending_file_ids: list[int] = []
        self._pending_hash_updates: list[tuple[int, str]] = []  # (file_id, pixel_hash)

        # Directories that completed hashing and need folder-badge recompute.
        self._pending_folder_recomputes: list[str] = []

        # Saved view state for persistence across reloads.
        self._saved_state: ViewState | None = None

        self._build_ui()
        self._build_debounce_timer()

    # ── Convenience accessors for shared model data ───────────────────

    @property
    def _duplicate_hashes(self) -> set[str]:
        return self._tree_model.duplicate_hashes

    @property
    def _cross_library_hashes(self) -> set[str]:
        return self._tree_model.cross_library_hashes

    @property
    def _folder_items(self) -> dict[str, QStandardItem]:
        return self._tree_model.folder_items

    @property
    def _file_id_to_item(self) -> dict[int, QStandardItem]:
        return self._tree_model.file_id_to_item

    # ── Public API ───────────────────────────────────────────────────────

    def set_session_id(self, session_id: int) -> None:
        self._session_id = session_id
        self._saved_state = None  # Fresh session — no state to restore.
        self.reload()

    def reload(self) -> None:
        """Full reload of the tree from the database."""
        # Save current view state before clearing (if tree has content).
        state = (
            self._save_view_state()
            if self._model.rowCount() > 0
            else self._saved_state
        )

        # Delegate tree rebuild to the shared model.
        self._tree_model.load_from_db(self._db, self._session_id)

        # Enable/disable Cross-Library radio based on data availability.
        self._radio_cross.setEnabled(len(self._cross_library_hashes) > 0)

        # Dynamic view adjustments.
        self._adjust_indentation()
        self._fit_columns()

        # Restore saved state or apply smart expand for first load.
        if state:
            self._restore_view_state(state)
        else:
            self._smart_expand()

        self._update_stats()

    def update_cross_library_data(self) -> None:
        """Refresh cross-library hashes after an import and update filter/tags.

        Called by main_window after Share > Import completes (Phase 5).
        Does a full reload to re-tag all items with updated cross-library status.
        """
        self.reload()

    # ── Scanner signal slots ─────────────────────────────────────────────

    @pyqtSlot(int, str)
    def on_file_discovered(self, file_id: int, path: str) -> None:
        """Called during Pass 1 — queue for debounced tree insert."""
        self._pending_file_ids.append(file_id)
        self._ensure_timer_running()

    @pyqtSlot(int, str)
    def on_hash_complete(self, file_id: int, pixel_hash: str) -> None:
        """Called during Pass 2 — queue for debounced badge update."""
        self._pending_hash_updates.append((file_id, pixel_hash))
        self._ensure_timer_running()

    @pyqtSlot(str, list)
    def on_duplicate_found(self, pixel_hash: str, file_ids: list[int]) -> None:
        """Called when a new duplicate group is first detected (exactly once per hash)."""
        self._duplicate_hashes.add(pixel_hash)
        # Queue badge refresh for the affected files.
        for fid in file_ids:
            self._pending_hash_updates.append((fid, pixel_hash))
        self._ensure_timer_running()

    @pyqtSlot(list)
    def on_hash_complete_batch(self, updates: list) -> None:
        """Called during Pass 2 — batch of (file_id, pixel_hash) tuples."""
        self._pending_hash_updates.extend(updates)
        self._ensure_timer_running()

    @pyqtSlot(list)
    def on_directories_hashed(self, dir_paths: list) -> None:
        """Called with a batch of completed directory paths."""
        self._pending_folder_recomputes.extend(dir_paths)
        self._ensure_timer_running()

    @pyqtSlot(str)
    def on_directory_hashed(self, dir_path: str) -> None:
        """Called after all files in a directory have been hashed.

        Queues a folder-badge recompute for the completed directory.
        Processing happens on the next debounce timer tick (not immediately).
        """
        self._pending_folder_recomputes.append(dir_path)
        self._ensure_timer_running()

    # ── Filter controls ──────────────────────────────────────────────────

    def set_filter(self, mode: str) -> None:
        """Programmatically set the filter mode."""
        self._proxy.set_filter_mode(mode)
        if mode == FILTER_ALL:
            self._radio_all.setChecked(True)
        elif mode == FILTER_DUPLICATES_ONLY:
            self._radio_dupes.setChecked(True)
        elif mode == FILTER_CROSS_LIBRARY:
            self._radio_cross.setChecked(True)

    @property
    def current_filter(self) -> str:
        return self._proxy.filter_mode

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Phase 5: View toggle + search bar toolbar.
        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(6, 4, 6, 0)

        self._view_group = QButtonGroup(self)
        self._tree_btn = QPushButton(self.tr("Tree View"), self)
        self._tree_btn.setCheckable(True)
        self._tree_btn.setChecked(True)
        self._cluster_btn = QPushButton(self.tr("Cluster View"), self)
        self._cluster_btn.setCheckable(True)
        self._view_group.addButton(self._tree_btn, 0)
        self._view_group.addButton(self._cluster_btn, 1)
        self._view_group.setExclusive(True)
        toolbar_row.addWidget(self._tree_btn)
        toolbar_row.addWidget(self._cluster_btn)

        toolbar_row.addSpacing(12)

        self._search_input = QLineEdit(self)
        self._search_input.setPlaceholderText(self.tr("Search files..."))
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setMaximumWidth(250)
        toolbar_row.addWidget(self._search_input)
        toolbar_row.addStretch()
        layout.addLayout(toolbar_row)

        # Phase 5: Stats header.
        self._stats_label = QLabel("", self)
        self._stats_label.setContentsMargins(6, 0, 6, 0)
        self._stats_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self._stats_label)

        # Filter bar (plan §Workflow 2 — filter bar above the tree).
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(6, 4, 6, 0)

        self._radio_all = QRadioButton(self.tr("All"), self)
        self._radio_dupes = QRadioButton(self.tr("Duplicates Only"), self)
        self._radio_cross = QRadioButton(self.tr("Cross-Library"), self)
        self._radio_cross.setEnabled(False)  # Enabled when cross-library data exists

        self._radio_all.setChecked(True)

        self._filter_group = QButtonGroup(self)
        self._filter_group.addButton(self._radio_all, 0)
        self._filter_group.addButton(self._radio_dupes, 1)
        self._filter_group.addButton(self._radio_cross, 2)

        filter_row.addWidget(self._radio_all)
        filter_row.addWidget(self._radio_dupes)
        filter_row.addWidget(self._radio_cross)
        filter_row.addStretch()

        # Compare button (enabled when a duplicate is selected).
        self._compare_btn = QPushButton(self.tr("Compare"), self)
        self._compare_btn.setObjectName("compare_btn")
        self._compare_btn.setEnabled(False)
        filter_row.addWidget(self._compare_btn)

        layout.addLayout(filter_row)

        # Tree view.
        self._proxy = DuplicateFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._tree = QTreeView(self)
        self._tree.setModel(self._proxy)
        self._tree.setHeaderHidden(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        # Hide Action column (used only by PlanningPanel).
        self._tree.setColumnHidden(2, True)

        layout.addWidget(self._tree)

        # Context menu on tree.
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        # Enable/disable Compare button based on selection.
        self._tree.selectionModel().currentChanged.connect(self._on_selection_changed)

        # Folder expansion override: when user expands a fully-duplicated folder,
        # temporarily clear the flag so children become visible.
        self._tree.expanded.connect(self._on_folder_expanded)
        self._tree.collapsed.connect(self._on_folder_collapsed)

        # Signals.
        self._filter_group.idToggled.connect(self._on_filter_changed)
        self._tree.doubleClicked.connect(self._on_item_double_clicked)
        self._compare_btn.clicked.connect(self._on_compare_clicked)
        self._view_group.idToggled.connect(self._on_view_toggled)
        self._search_input.textChanged.connect(self._on_search_changed)

    def _build_debounce_timer(self) -> None:
        """200ms debounce timer (plan §Resource Usage — UI update rate-limiting)."""
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setInterval(_DEBOUNCE_MS)
        self._debounce_timer.setSingleShot(False)
        self._debounce_timer.timeout.connect(self._flush_pending)

    def _ensure_timer_running(self) -> None:
        if not self._debounce_timer.isActive():
            self._debounce_timer.start()

    # ── Debounce flush ───────────────────────────────────────────────────

    @pyqtSlot()
    def _flush_pending(self) -> None:
        """Process queued file discoveries and hash completions."""
        if self._perf:
            self._perf.record_ui_backlog(
                len(self._pending_file_ids), len(self._pending_hash_updates)
            )
        # Process new file discoveries (Pass 1).
        file_ids = self._pending_file_ids[:]
        self._pending_file_ids.clear()
        for file_id in file_ids:
            row = self._db.get_file(file_id)
            if row and row["status"] == "active":
                self._tree_model.add_file_to_tree(
                    file_id=row["id"],
                    path=row["path"],
                    pixel_hash=row["pixel_hash"],
                )

        # Process hash completions / duplicate badge updates (Pass 2).
        # Deduplicate by file_id, keeping the last pixel_hash seen.
        seen: dict[int, str] = {}
        for file_id, pixel_hash in self._pending_hash_updates:
            seen[file_id] = pixel_hash
        self._pending_hash_updates.clear()
        for file_id, pixel_hash in seen.items():
            self._tree_model.update_file_badge(file_id, pixel_hash)

        # Incremental folder-badge recompute: only process completed dirs
        # and their parent chain, not the entire tree.
        if self._pending_folder_recomputes:
            dirs = self._pending_folder_recomputes[:]
            self._pending_folder_recomputes.clear()
            for dir_path in dirs:
                self._tree_model.recompute_folder_chain(dir_path)

        # Auto-fit columns after incremental updates.
        if file_ids:
            self._fit_columns()

        # Stop timer if nothing pending.
        if not self._pending_file_ids and not self._pending_hash_updates:
            self._debounce_timer.stop()

    # ── View state persistence ──────────────────────────────────────────

    def _save_view_state(self) -> ViewState:
        """Capture current filter, expansion, scroll, and selection."""
        state = ViewState()
        state.filter_mode = self._proxy.filter_mode

        state.expanded_paths = set()
        self._collect_expanded(self._model.invisibleRootItem(), state.expanded_paths)

        state.scroll_value = self._tree.verticalScrollBar().value()

        idx = self._tree.currentIndex()
        if idx.isValid():
            src = self._proxy.mapToSource(idx)
            item = self._model.itemFromIndex(src)
            if item and item.data(ROLE_NODE_TYPE) == "file":
                state.selected_path = item.data(ROLE_FILE_PATH)

        return state

    def _collect_expanded(self, parent: QStandardItem, paths: set[str]) -> None:
        """Walk the tree and record expanded folder paths."""
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder":
                proxy_idx = self._proxy.mapFromSource(child.index())
                if proxy_idx.isValid() and self._tree.isExpanded(proxy_idx):
                    for path, item in self._folder_items.items():
                        if item is child:
                            paths.add(path)
                            break
                self._collect_expanded(child, paths)

    def _restore_view_state(self, state: ViewState) -> None:
        """Restore filter, expansion, scroll, and selection from a snapshot."""
        self.set_filter(state.filter_mode)

        for folder_path, item in self._folder_items.items():
            proxy_idx = self._proxy.mapFromSource(item.index())
            if proxy_idx.isValid():
                self._tree.setExpanded(proxy_idx, folder_path in state.expanded_paths)

        QTimer.singleShot(
            0, lambda v=state.scroll_value: self._tree.verticalScrollBar().setValue(v)
        )

        if state.selected_path:
            item = self._find_file_by_path(state.selected_path)
            if item:
                proxy_idx = self._proxy.mapFromSource(item.index())
                if proxy_idx.isValid():
                    self._tree.setCurrentIndex(proxy_idx)

    def _find_file_by_path(self, path: str) -> Optional[QStandardItem]:
        """Find a file item by its ROLE_FILE_PATH."""
        return self._find_by_path_recursive(self._model.invisibleRootItem(), path)

    def _find_by_path_recursive(
        self, parent: QStandardItem, path: str
    ) -> Optional[QStandardItem]:
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child is None:
                continue
            if child.data(ROLE_NODE_TYPE) == "file" and child.data(ROLE_FILE_PATH) == path:
                return child
            if child.data(ROLE_NODE_TYPE) == "folder":
                result = self._find_by_path_recursive(child, path)
                if result:
                    return result
        return None

    # ── Dynamic view adjustment ──────────────────────────────────────────

    def _fit_columns(self) -> None:
        """Auto-fit the Name column to content, floored at viewport width."""
        self._tree.resizeColumnToContents(0)
        viewport_width = self._tree.viewport().width()
        status_width = self._tree.columnWidth(1)
        min_name_width = viewport_width - status_width - 4
        if self._tree.columnWidth(0) < min_name_width:
            self._tree.setColumnWidth(0, min_name_width)

    def _adjust_indentation(self) -> None:
        """Scale tree indentation inversely with depth."""
        depth = self._tree_model.max_depth()
        if depth <= 4:
            indent = _DEFAULT_INDENT
        else:
            indent = max(_MIN_INDENT, _DEFAULT_INDENT * 4 // depth)
        self._tree.setIndentation(indent)

    # ── Smart expand/collapse ────────────────────────────────────────────

    def _smart_expand(self) -> None:
        """Expand folders based on filter mode and content."""
        mode = self._proxy.filter_mode
        if mode == FILTER_ALL:
            self._expand_to_depth(self._model.invisibleRootItem(), max_depth=2, current=0)
        elif mode in (FILTER_DUPLICATES_ONLY, FILTER_CROSS_LIBRARY):
            self._expand_paths_to_matches()

    def _expand_to_depth(
        self, parent: QStandardItem, max_depth: int, current: int
    ) -> None:
        """Expand folders up to *max_depth* levels, collapse deeper ones."""
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder":
                proxy_idx = self._proxy.mapFromSource(child.index())
                if proxy_idx.isValid():
                    self._tree.setExpanded(proxy_idx, current < max_depth)
                if current < max_depth:
                    self._expand_to_depth(child, max_depth, current + 1)

    def _expand_paths_to_matches(self) -> None:
        """Expand only folder chains leading to duplicate/cross-library files."""
        self._tree.collapseAll()
        target_hashes = (
            self._duplicate_hashes
            if self._proxy.filter_mode == FILTER_DUPLICATES_ONLY
            else self._cross_library_hashes
        )
        self._expand_ancestors_of_matches(self._model.invisibleRootItem(), target_hashes)

    def _expand_ancestors_of_matches(
        self, parent: QStandardItem, target_hashes: set[str]
    ) -> bool:
        """Recursively expand folders containing matching files."""
        has_match = False
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child is None:
                continue
            if child.data(ROLE_NODE_TYPE) == "file":
                ph = child.data(ROLE_PIXEL_HASH)
                if ph and ph in target_hashes:
                    has_match = True
            elif child.data(ROLE_NODE_TYPE) == "folder":
                if self._expand_ancestors_of_matches(child, target_hashes):
                    proxy_idx = self._proxy.mapFromSource(child.index())
                    if proxy_idx.isValid():
                        self._tree.setExpanded(proxy_idx, True)
                    has_match = True
        return has_match

    # ── Slots ────────────────────────────────────────────────────────────

    @pyqtSlot(QModelIndex)
    def _on_folder_expanded(self, proxy_index: QModelIndex) -> None:
        """When user expands a fully-duplicated folder, clear the flag so children show."""
        if self._proxy.filter_mode != FILTER_DUPLICATES_ONLY:
            return
        source = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source)
        if item and item.data(ROLE_IS_FOLDER_DUPLICATED):
            item.setData(False, ROLE_IS_FOLDER_DUPLICATED)
            self._proxy.invalidateFilter()

    @pyqtSlot(QModelIndex)
    def _on_folder_collapsed(self, proxy_index: QModelIndex) -> None:
        """When user collapses a folder that was fully duplicated, restore the flag."""
        if self._proxy.filter_mode != FILTER_DUPLICATES_ONLY:
            return
        source = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source)
        if item and item.data(ROLE_NODE_TYPE) == "folder":
            # Re-check if all children are duplicates.
            total, duped = self._tree_model._compute_folder_dup_recursive(item)
            if total > 0 and total == duped:
                item.setData(True, ROLE_IS_FOLDER_DUPLICATED)
                self._proxy.invalidateFilter()

    @pyqtSlot(int, bool)
    def _on_filter_changed(self, button_id: int, checked: bool) -> None:
        if not checked:
            return
        mode_map = {0: FILTER_ALL, 1: FILTER_DUPLICATES_ONLY, 2: FILTER_CROSS_LIBRARY}
        mode = mode_map.get(button_id, FILTER_ALL)
        self._proxy.set_filter_mode(mode)
        self._smart_expand()

    @pyqtSlot(QModelIndex)
    def _on_item_double_clicked(self, proxy_index: QModelIndex) -> None:
        """Double-click a duplicate file → emit compare_view_requested(pixel_hash)."""
        source_index = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source_index)
        if item is None:
            return
        if item.data(ROLE_NODE_TYPE) != "file":
            return
        pixel_hash = item.data(ROLE_PIXEL_HASH)
        is_dup = item.data(ROLE_IS_DUPLICATE)
        if pixel_hash and is_dup:
            self.compare_view_requested.emit(pixel_hash)

    @pyqtSlot(QModelIndex, QModelIndex)
    def _on_selection_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        """Enable/disable Compare button based on selection."""
        if not current.isValid():
            self._compare_btn.setEnabled(False)
            return
        source = self._proxy.mapToSource(current)
        item = self._model.itemFromIndex(source)
        if item is None:
            self._compare_btn.setEnabled(False)
            return
        is_file = item.data(ROLE_NODE_TYPE) == "file"
        is_dup = bool(item.data(ROLE_IS_DUPLICATE))
        is_folder_dup = bool(item.data(ROLE_IS_FOLDER_DUPLICATED)) if item.data(ROLE_NODE_TYPE) == "folder" else False
        self._compare_btn.setEnabled((is_file and is_dup) or is_folder_dup)

    @pyqtSlot()
    def _on_compare_clicked(self) -> None:
        """Compare button clicked — emit compare signal for the selected item."""
        idx = self._tree.currentIndex()
        if not idx.isValid():
            return
        source = self._proxy.mapToSource(idx)
        item = self._model.itemFromIndex(source)
        if item is None:
            return
        if item.data(ROLE_NODE_TYPE) == "file":
            pixel_hash = item.data(ROLE_PIXEL_HASH)
            if pixel_hash and item.data(ROLE_IS_DUPLICATE):
                self.compare_view_requested.emit(pixel_hash)
        elif item.data(ROLE_NODE_TYPE) == "folder" and item.data(ROLE_IS_FOLDER_DUPLICATED):
            # Find the folder path from the folder_items mapping.
            for path, folder_item in self._folder_items.items():
                if folder_item is item:
                    self.compare_folder_requested.emit(path)
                    break

    @pyqtSlot("QPoint")
    def _on_context_menu(self, position) -> None:
        """Show context menu on right-click."""
        idx = self._tree.indexAt(position)
        if not idx.isValid():
            return
        source = self._proxy.mapToSource(idx)
        item = self._model.itemFromIndex(source)
        if item is None:
            return

        if item.data(ROLE_NODE_TYPE) == "file" and item.data(ROLE_IS_DUPLICATE):
            menu = QMenu(self)
            pixel_hash = item.data(ROLE_PIXEL_HASH)
            action = menu.addAction(self.tr("Compare Duplicates"))
            action.triggered.connect(
                lambda: self.compare_view_requested.emit(pixel_hash)
            )
            menu.exec(self._tree.viewport().mapToGlobal(position))

    # ── Phase 5: View toggle, search, stats ─────────────────────────────

    @pyqtSlot(int, bool)
    def _on_view_toggled(self, button_id: int, checked: bool) -> None:
        """Switch between tree view and cluster view."""
        if not checked:
            return
        if button_id == 0:
            self._switch_to_tree_view()
        elif button_id == 1:
            self._switch_to_cluster_view()

    def _switch_to_tree_view(self) -> None:
        """Switch the QTreeView back to the folder-based tree model."""
        self._view_mode = "tree"
        self._tree.setModel(self._proxy)
        self._tree.setColumnHidden(2, True)
        # Restore filter bar (relevant for tree view).
        self._radio_all.setVisible(True)
        self._radio_dupes.setVisible(True)
        self._radio_cross.setVisible(True)
        self._adjust_indentation()
        self._fit_columns()
        self._update_stats()

    def _switch_to_cluster_view(self) -> None:
        """Switch the QTreeView to the cluster model (grouped by hash)."""
        self._view_mode = "cluster"
        if self._session_id is not None:
            search = self._search_input.text().strip() or None
            self._cluster_model.load_from_db(
                self._db, self._session_id, search_text=search,
            )
        self._tree.setModel(self._cluster_model)
        self._tree.setColumnHidden(2, False)
        # Hide filter bar radios (cluster view uses filter sidebar instead).
        self._radio_all.setVisible(False)
        self._radio_dupes.setVisible(False)
        self._radio_cross.setVisible(False)
        self._tree.expandAll()
        self._fit_columns()
        self._update_stats()

    @pyqtSlot(str)
    def _on_search_changed(self, text: str) -> None:
        """Filter the current view by filename search text."""
        if self._view_mode == "cluster" and self._session_id is not None:
            search = text.strip() or None
            self._cluster_model.load_from_db(
                self._db, self._session_id, search_text=search,
            )
            self._tree.expandAll()
        # For tree view, search is informational only (full filter in sidebar).
        self._update_stats()

    def apply_filter_criteria(self, criteria) -> None:
        """Apply FilterCriteria from the sidebar to the current view.

        Args:
            criteria: A FilterCriteria dataclass instance from filter_sidebar.
        """
        if self._session_id is None:
            return

        if self._view_mode == "cluster":
            self._cluster_model.load_from_db(
                self._db,
                self._session_id,
                date_from=criteria.date_from,
                date_to=criteria.date_to,
                extensions=criteria.extensions,
                min_copies=criteria.min_copies,
                sort_by=criteria.sort_by,
                sort_desc=criteria.sort_descending,
                search_text=criteria.search_text or self._search_input.text().strip() or None,
            )
            self._tree.expandAll()
        # Tree view: the filter sidebar criteria are applied via the proxy in future enhancement.
        self._update_stats()

    def _update_stats(self) -> None:
        """Refresh the stats header label."""
        if self._view_mode == "cluster":
            groups = self._cluster_model.cluster_count()
            files = self._cluster_model.total_files()
            waste = self._cluster_model.total_waste_bytes()
            waste_str = self._format_size(waste)
            self._stats_label.setText(
                self.tr("{0} groups \u00b7 {1} files \u00b7 {2} potential savings").format(
                    groups, files, waste_str
                )
            )
        else:
            dup_count = len(self._duplicate_hashes)
            if dup_count > 0:
                self._stats_label.setText(
                    self.tr("{0} duplicate groups found").format(dup_count)
                )
            else:
                self._stats_label.setText("")

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes into human-readable string."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    @property
    def view_mode(self) -> str:
        """Return current view mode: 'tree' or 'cluster'."""
        return self._view_mode

    @property
    def cluster_model(self) -> ClusterModel:
        """Access the cluster model (for wiring from cleanup_screen)."""
        return self._cluster_model

    # ── Helpers for tests ────────────────────────────────────────────────

    def visible_file_count(self) -> int:
        """Count visible file leaf nodes (for test assertions)."""
        return self._count_visible_files(self._proxy, QModelIndex())

    def _count_visible_files(self, model, parent: QModelIndex) -> int:
        count = 0
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            node_type = idx.data(ROLE_NODE_TYPE)
            if node_type == "file":
                count += 1
            elif node_type == "folder":
                count += self._count_visible_files(model, idx)
        return count

    def visible_items_data(self) -> list[dict]:
        """Return data for all visible file items (for test assertions)."""
        result = []
        self._collect_visible(self._proxy, QModelIndex(), result)
        return result

    def _collect_visible(self, model, parent: QModelIndex, result: list) -> None:
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            node_type = idx.data(ROLE_NODE_TYPE)
            if node_type == "file":
                badge_idx = model.index(row, 1, parent)
                result.append({
                    "file_id": idx.data(ROLE_FILE_ID),
                    "path": idx.data(ROLE_FILE_PATH),
                    "pixel_hash": idx.data(ROLE_PIXEL_HASH),
                    "is_duplicate": idx.data(ROLE_IS_DUPLICATE),
                    "is_cross_library": idx.data(ROLE_IS_CROSS_LIBRARY),
                    "badge_text": badge_idx.data(Qt.ItemDataRole.DisplayRole) or "",
                })
            elif node_type == "folder":
                self._collect_visible(model, idx, result)
