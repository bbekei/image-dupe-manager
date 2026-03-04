import { useEffect, useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ChevronRight, Check, Trash2, EyeOff, Wand2 } from 'lucide-react'
import { callBackend, useBackendEvent } from '../hooks/usePyBridge.ts'
import { useReviewStore } from '../stores/useReviewStore.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { DuplicateGroup, FileInfo, FileAction, SelectionPreset } from '../types/api.ts'

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
  currentAction,
}: {
  file: FileInfo
  onAction: (fileId: number, action: FileAction) => void
  currentAction?: FileAction
}) {
  const { t } = useTranslation()
  const fileName = file.path.split(/[/\\]/).pop() ?? file.path

  return (
    <div className="bg-dv-bg rounded-lg border border-dv-border p-3 flex gap-3">
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

      <div className="flex flex-col gap-1.5 shrink-0">
        <button
          onClick={() => onAction(file.id, 'keep')}
          className={`p-1.5 rounded text-xs ${
            currentAction === 'keep'
              ? 'bg-dv-success text-white'
              : 'bg-dv-surface hover:bg-dv-surface-hover text-dv-text-muted'
          }`}
          title={t('browse.actions.keep')}
        >
          <Check size={14} />
        </button>
        <button
          onClick={() => onAction(file.id, 'delete')}
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
          onClick={() => onAction(file.id, 'ignore')}
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
    setSelectedGroup,
    setLoading,
  } = useReviewStore()
  const [selectedFiles, setSelectedFiles] = useState<FileInfo[]>([])
  const [fileActions, setFileActions] = useState<Record<number, FileAction>>({})
  const parentRef = useRef<HTMLDivElement>(null)

  const loadGroups = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const result = await callBackend<DuplicateGroup[]>(
        'get_duplicate_groups',
        sessionId,
        0,
        PAGE_SIZE,
      )
      setGroups(result, result.length)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [sessionId, setGroups, setLoading])

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
    } catch {
      setSelectedFiles([])
    }
  }, [sessionId, setSelectedGroup])

  const handleFileAction = useCallback(async (fileId: number, action: FileAction) => {
    try {
      await callBackend('set_file_action', fileId, action, 'file')
      setFileActions((prev) => ({ ...prev, [fileId]: action }))
    } catch {
      // handle error
    }
  }, [])

  const handlePreset = useCallback(async (preset: SelectionPreset) => {
    if (!sessionId) return
    try {
      await callBackend('apply_selection_preset', sessionId, preset)
      // Reload current group to reflect changes
      if (selectedGroupHash) loadGroupDetail(selectedGroupHash)
    } catch {
      // handle error
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
        <div className="px-3 py-2 border-b border-dv-border flex flex-wrap gap-1">
          {presets.map((preset) => (
            <button
              key={preset}
              onClick={() => handlePreset(preset)}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-dv-surface hover:bg-dv-surface-hover rounded text-dv-text-muted"
              title={t(`browse.presets.${preset}`)}
            >
              <Wand2 size={12} />
              {t(`browse.presets.${preset}`)}
            </button>
          ))}
        </div>

        <div ref={parentRef} className="flex-1 overflow-y-auto">
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
                  currentAction={fileActions[file.id]}
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
