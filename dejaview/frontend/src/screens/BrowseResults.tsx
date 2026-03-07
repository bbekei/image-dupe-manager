import { useEffect, useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ChevronRight, ChevronDown, Check, Trash2, EyeOff, Wand2, FolderCheck, Settings2 } from 'lucide-react'
import { callBackend, useBackendEvent } from '../hooks/usePyBridge.ts'
import { useReviewStore } from '../stores/useReviewStore.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import { CriteriaBuilder } from '../components/CriteriaBuilder.tsx'
import type { DuplicateGroup, DuplicateGroupsPage, FileInfo, FileAction, SelectionPreset, SortCriterion, SelectionResult } from '../types/api.ts'

const PAGE_SIZE = 50

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

function FileCard({
  file,
  onAction,
  onKeepAndDeleteOthers,
  currentAction,
  groupSize,
}: {
  file: FileInfo
  onAction: (fileId: number, action: FileAction, scope: 'file' | 'folder') => void
  onKeepAndDeleteOthers?: (fileId: number) => void
  currentAction?: FileAction
  groupSize: number
}) {
  const { t } = useTranslation()
  const [folderScope, setFolderScope] = useState(false)
  const [pendingFolderAction, setPendingFolderAction] = useState<FileAction | null>(null)
  const [keepMenuOpen, setKeepMenuOpen] = useState(false)
  const fileName = file.path.split(/[/\\]/).pop() ?? file.path
  const showSplitKeep = groupSize >= 4 && onKeepAndDeleteOthers

  const handleFolderToggle = () => {
    if (!folderScope && currentAction) {
      // Turning ON folder scope while an action is already set → confirm first
      setPendingFolderAction(currentAction)
    } else {
      setFolderScope(!folderScope)
    }
  }

  const handleAction = (action: FileAction) => {
    if (folderScope) {
      // Folder scope is ON → confirm before applying to whole folder
      setPendingFolderAction(action)
    } else {
      onAction(file.id, action, 'file')
    }
  }

  const confirmFolderAction = () => {
    if (pendingFolderAction) {
      setFolderScope(true)
      onAction(file.id, pendingFolderAction, 'folder')
      setPendingFolderAction(null)
    }
  }

  const cancelFolderAction = () => {
    setFolderScope(false)
    setPendingFolderAction(null)
  }

  return (
    <div className="bg-dv-bg rounded-lg border border-dv-border p-3 flex gap-3 relative">
      {file.thumbnail_data ? (
        <img
          src={file.thumbnail_data}
          alt={fileName}
          className="w-24 h-24 object-cover rounded-md shrink-0"
          loading="lazy"
        />
      ) : (
        <div className="w-24 h-24 bg-dv-surface rounded-md shrink-0 flex items-center justify-center text-dv-text-muted text-xs">
          No thumb
        </div>
      )}

      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-dv-text truncate" title={file.path}>
          {fileName}
        </div>
        <div className="text-xs text-dv-text-muted mt-1 space-y-0.5">
          <div>{formatBytes(file.size)}</div>
          {file.width && file.height && (
            <div>{file.width} x {file.height}</div>
          )}
          <div className="truncate" title={file.path}>{file.path}</div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="flex flex-col gap-1.5">
          {showSplitKeep ? (
            <div className="relative">
              <div className="flex">
                <button
                  onClick={() => handleAction('keep')}
                  className={`p-1.5 rounded-l text-xs ${
                    currentAction === 'keep'
                      ? 'bg-dv-success text-white'
                      : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
                  }`}
                  title={t('browse.actions.keep')}
                >
                  <Check size={14} />
                </button>
                <button
                  onClick={() => setKeepMenuOpen(!keepMenuOpen)}
                  className={`px-0.5 rounded-r border-l text-xs ${
                    currentAction === 'keep'
                      ? 'bg-dv-success text-white border-white/30'
                      : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted border-dv-border'
                  }`}
                  title={t('browse.actions.keep_delete_others')}
                >
                  <ChevronDown size={10} />
                </button>
              </div>
              {keepMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-20 bg-dv-surface border border-dv-border rounded shadow-lg min-w-max">
                  <button
                    onClick={() => {
                      onKeepAndDeleteOthers(file.id)
                      setKeepMenuOpen(false)
                    }}
                    className="px-3 py-1.5 text-xs text-dv-text hover:bg-dv-surface-hover w-full text-left whitespace-nowrap"
                  >
                    {t('browse.actions.keep_delete_others')}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button
              onClick={() => handleAction('keep')}
              className={`p-1.5 rounded text-xs ${
                currentAction === 'keep'
                  ? 'bg-dv-success text-white'
                  : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
              }`}
              title={t('browse.actions.keep')}
            >
              <Check size={14} />
            </button>
          )}
          <button
            onClick={() => handleAction('delete')}
            className={`p-1.5 rounded text-xs ${
              currentAction === 'delete'
                ? 'bg-dv-danger text-white'
                : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
            }`}
            title={t('browse.actions.delete')}
          >
            <Trash2 size={14} />
          </button>
          <button
            onClick={() => handleAction('ignore')}
            className={`p-1.5 rounded text-xs ${
              currentAction === 'ignore'
                ? 'bg-dv-warning text-white'
                : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
            }`}
            title={t('browse.actions.ignore')}
          >
            <EyeOff size={14} />
          </button>
        </div>
        <button
          onClick={handleFolderToggle}
          className={`p-2 rounded text-xs ${
            folderScope
              ? 'bg-dv-primary text-white'
              : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
          }`}
          title={t('browse.actions.folder_scope')}
        >
          <FolderCheck size={18} />
        </button>
      </div>

      {/* Folder-scope confirmation overlay */}
      {pendingFolderAction && (
        <div className="absolute inset-0 bg-dv-bg/95 rounded-lg flex items-center justify-center z-10 border border-dv-border">
          <div className="text-center px-4">
            <p className="text-sm text-dv-text mb-3">
              {t('browse.actions.folder_confirm')}
            </p>
            <div className="flex gap-2 justify-center">
              <button
                onClick={confirmFolderAction}
                className="px-3 py-1.5 text-xs bg-dv-primary text-white rounded hover:bg-dv-primary/90"
              >
                {t('common.confirm')}
              </button>
              <button
                onClick={cancelFolderAction}
                className="px-3 py-1.5 text-xs bg-dv-surface text-dv-text-muted rounded hover:bg-dv-surface-hover border border-dv-border"
              >
                {t('common.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function GroupRow({
  group,
  isSelected,
  onClick,
}: {
  group: DuplicateGroup
  isSelected: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors border-b border-dv-border ${
        isSelected ? 'bg-dv-primary/10' : 'hover:bg-dv-surface-hover'
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="text-sm font-mono text-dv-text truncate">
          {group.pixel_hash.slice(0, 16)}...
        </div>
        <div className="text-xs text-dv-text-muted">
          {group.file_count} files
        </div>
      </div>
      <ChevronRight size={16} className="text-dv-text-muted shrink-0" />
    </button>
  )
}

const presets: SelectionPreset[] = [
  'KEEP_LARGEST_FILE',
  'KEEP_NEWEST',
  'KEEP_OLDEST',
  'KEEP_SHORTEST_PATH',
  'KEEP_HIGHEST_RESOLUTION',
]

export function BrowseResults() {
  const { t } = useTranslation()
  const { sessionId } = useScanStore()
  const {
    groups,
    totalGroups,
    selectedGroupHash,
    loading,
    setGroups,
    appendGroups,
    setSelectedGroup,
    setLoading,
  } = useReviewStore()
  const [selectedFiles, setSelectedFiles] = useState<FileInfo[]>([])
  const [fileActions, setFileActions] = useState<Record<number, FileAction>>({})
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selectionProgress, setSelectionProgress] = useState<{ current: number; total: number } | null>(null)
  const [applyingPreset, setApplyingPreset] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const parentRef = useRef<HTMLDivElement>(null)

  const loadGroups = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const result = await callBackend<DuplicateGroupsPage>(
        'get_duplicate_groups',
        sessionId,
        0,
        PAGE_SIZE,
      )
      setGroups(result.groups, result.total_count)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [sessionId, setGroups, setLoading])

  const loadMore = useCallback(async () => {
    if (!sessionId || loadingMore || groups.length >= totalGroups) return
    setLoadingMore(true)
    try {
      const result = await callBackend<DuplicateGroupsPage>(
        'get_duplicate_groups',
        sessionId,
        groups.length,
        PAGE_SIZE,
      )
      appendGroups(result.groups)
    } catch {
      // handle error
    } finally {
      setLoadingMore(false)
    }
  }, [sessionId, loadingMore, groups.length, totalGroups, appendGroups])

  useEffect(() => { loadGroups() }, [loadGroups])

  // Refresh groups when scan completes
  useBackendEvent('scan:status', (e: CustomEvent) => {
    if (e.detail.status === 'complete') loadGroups()
  })

  const loadGroupDetail = useCallback(async (pixelHash: string) => {
    if (!sessionId) return
    setSelectedGroup(pixelHash)
    try {
      const files = await callBackend<FileInfo[]>('get_group_detail', sessionId, pixelHash)
      setSelectedFiles(files)
      // Populate fileActions from backend-supplied action field
      const actions: Record<number, FileAction> = {}
      for (const f of files) {
        if (f.action) actions[f.id] = f.action
      }
      setFileActions(actions)
    } catch {
      setSelectedFiles([])
      setFileActions({})
    }
  }, [sessionId, setSelectedGroup])

  const handleFileAction = useCallback(async (fileId: number, action: FileAction, scope: 'file' | 'folder' = 'file') => {
    setActivePreset(null)
    try {
      if (scope === 'folder') {
        // Apply action to ALL scanned files in the same folder (across all groups)
        const targetFile = selectedFiles.find((f) => f.id === fileId)
        if (!targetFile || !sessionId) return
        const folderPath = targetFile.path.replace(/[/\\][^/\\]+$/, '')
        await callBackend('apply_folder_action', sessionId, folderPath, action)
        // Reload the group to reflect updated actions
        if (selectedGroupHash) await loadGroupDetail(selectedGroupHash)
      } else {
        const result = await callBackend<{ actions: Record<string, FileAction> }>(
          'set_file_action', fileId, action, 'file',
        )
        const updated: Record<number, FileAction> = {}
        for (const [id, act] of Object.entries(result.actions)) {
          updated[Number(id)] = act
        }
        setFileActions(updated)
      }
    } catch {
      // handle error
    }
  }, [selectedFiles, sessionId, selectedGroupHash, loadGroupDetail])

  const handleKeepAndDeleteOthers = useCallback(async (fileId: number) => {
    try {
      const groupFileIds = selectedFiles.map((f) => f.id)
      const result = await callBackend<{ actions: Record<string, FileAction> }>(
        'keep_and_delete_others', fileId, groupFileIds,
      )
      const updated: Record<number, FileAction> = {}
      for (const [id, act] of Object.entries(result.actions)) {
        updated[Number(id)] = act
      }
      setFileActions(updated)
    } catch {
      // handle error
    }
  }, [selectedFiles])

  // Listen for selection progress/complete events
  useBackendEvent('selection:progress', (e: CustomEvent) => {
    setSelectionProgress({ current: e.detail.current, total: e.detail.total })
  })
  useBackendEvent('selection:complete', (e: CustomEvent) => {
    setSelectionProgress(null)
    setApplyingPreset(false)
    setActivePreset(e.detail.active_preset)
    if (selectedGroupHash) loadGroupDetail(selectedGroupHash)
  })

  const handlePreset = useCallback(async (preset: SelectionPreset) => {
    if (!sessionId) return
    setApplyingPreset(true)
    setActivePreset(preset)
    try {
      await callBackend<SelectionResult>('apply_selection_preset', sessionId, preset)
      if (selectedGroupHash) loadGroupDetail(selectedGroupHash)
    } catch {
      // handle error
    } finally {
      setApplyingPreset(false)
      setSelectionProgress(null)
    }
  }, [sessionId, selectedGroupHash, loadGroupDetail])

  const handleCustomChain = useCallback(async (criteria: SortCriterion[]) => {
    if (!sessionId) return
    setApplyingPreset(true)
    setActivePreset('custom')
    try {
      await callBackend<SelectionResult>('apply_custom_selection', sessionId, criteria)
      if (selectedGroupHash) loadGroupDetail(selectedGroupHash)
    } catch {
      // handle error
    } finally {
      setApplyingPreset(false)
      setSelectionProgress(null)
    }
  }, [sessionId, selectedGroupHash, loadGroupDetail])

  const virtualizer = useVirtualizer({
    count: groups.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
  })

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full text-dv-text-muted">
        {t('browse.no_duplicates')}
      </div>
    )
  }

  return (
    <div className="flex h-full gap-0 -m-6">
      {/* Group list (left panel) */}
      <div className="w-80 border-r border-dv-border flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-dv-border">
          <h2 className="font-semibold text-dv-text">{t('browse.title')}</h2>
          <div className="text-xs text-dv-text-muted mt-1">
            {t('browse.groups', { count: totalGroups })}
          </div>
        </div>

        {/* Preset toolbar */}
        <div className="px-3 py-2 border-b border-dv-border space-y-2">
          <div className="flex flex-wrap gap-1">
            {presets.map((preset) => (
              <button
                key={preset}
                onClick={() => handlePreset(preset)}
                disabled={applyingPreset}
                className={`flex items-center gap-1 px-2 py-1 text-xs rounded ${
                  activePreset === preset
                    ? 'bg-dv-primary text-white ring-2 ring-dv-primary/40'
                    : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
                } disabled:opacity-50`}
                title={t(`browse.presets.${preset}`)}
              >
                <Wand2 size={12} />
                {t(`browse.presets.${preset}`)}
              </button>
            ))}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className={`flex items-center gap-1 px-2 py-1 text-xs rounded ${
                showAdvanced || activePreset === 'custom'
                  ? 'bg-dv-primary text-white'
                  : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
              }`}
            >
              <Settings2 size={12} />
              {t('selection.advanced_toggle')}
            </button>
          </div>

          {/* Progress bar */}
          {selectionProgress && (
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-dv-bg rounded-full overflow-hidden">
                <div
                  className="h-full bg-dv-primary rounded-full transition-all"
                  style={{ width: `${selectionProgress.total > 0 ? (selectionProgress.current / selectionProgress.total) * 100 : 0}%` }}
                />
              </div>
              <span className="text-xs text-dv-text-muted">{t('selection.applying')}</span>
            </div>
          )}

          {/* Advanced panel */}
          {showAdvanced && (
            <CriteriaBuilder
              onApply={handleCustomChain}
              disabled={applyingPreset}
              progress={selectionProgress}
            />
          )}
        </div>

        <div
          ref={parentRef}
          className="flex-1 overflow-y-auto"
          onScroll={(e) => {
            const el = e.currentTarget
            if (el.scrollHeight - el.scrollTop - el.clientHeight < 200) {
              loadMore()
            }
          }}
        >
          {loading ? (
            <div className="p-4 text-center text-dv-text-muted">{t('common.loading')}</div>
          ) : (
            <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
              {virtualizer.getVirtualItems().map((virtualItem) => {
                const group = groups[virtualItem.index]
                return (
                  <div
                    key={group.pixel_hash}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: virtualItem.size,
                      transform: `translateY(${virtualItem.start}px)`,
                    }}
                  >
                    <GroupRow
                      group={group}
                      isSelected={selectedGroupHash === group.pixel_hash}
                      onClick={() => loadGroupDetail(group.pixel_hash)}
                    />
                  </div>
                )
              })}
            </div>
          )}
          {loadingMore && (
            <div className="p-3 text-center text-xs text-dv-text-muted">{t('common.loading')}</div>
          )}
          {!loading && groups.length < totalGroups && !loadingMore && (
            <button
              onClick={loadMore}
              className="w-full p-2 text-xs text-dv-text-muted hover:bg-dv-surface-hover"
            >
              {t('browse.load_more', { loaded: groups.length, total: totalGroups })}
            </button>
          )}
        </div>
      </div>

      {/* Detail panel (right) */}
      <div className="flex-1 overflow-y-auto p-6">
        {selectedGroupHash && selectedFiles.length > 0 ? (
          <div>
            <h3 className="text-lg font-semibold text-dv-text mb-4">
              {t('browse.files', { count: selectedFiles.length })}
            </h3>
            <div className="space-y-3">
              {selectedFiles.map((file) => (
                <FileCard
                  key={file.id}
                  file={file}
                  onAction={handleFileAction}
                  onKeepAndDeleteOthers={handleKeepAndDeleteOthers}
                  currentAction={fileActions[file.id]}
                  groupSize={selectedFiles.length}
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-dv-text-muted">
            Select a group to view its files
          </div>
        )}
      </div>
    </div>
  )
}
