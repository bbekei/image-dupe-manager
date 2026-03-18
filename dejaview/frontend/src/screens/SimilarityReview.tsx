import { useEffect, useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Images, Star, Check, ChevronDown, Trash2, EyeOff, Wand2, Settings2 } from 'lucide-react'
import { ReactCompareSlider, ReactCompareSliderImage } from 'react-compare-slider'
import { callBackend, useBackendEvent } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import { CriteriaBuilder } from '../components/CriteriaBuilder.tsx'
import type { SimilarityGroupSummary, SimilarityGroupsPage, SimilarityGroup, FileInfo, FileAction, KeeperRecommendation, SelectionPreset, SortCriterion, SelectionResult } from '../types/api.ts'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

const presets: SelectionPreset[] = [
  'KEEP_LARGEST_FILE',
  'KEEP_NEWEST',
  'KEEP_OLDEST',
  'KEEP_SHORTEST_PATH',
  'KEEP_HIGHEST_RESOLUTION',
]

const PAGE_SIZE = 200

export function SimilarityReview() {
  const { t } = useTranslation()
  const { sessionId } = useScanStore()
  const [groupSummaries, setGroupSummaries] = useState<SimilarityGroupSummary[]>([])
  const [totalGroups, setTotalGroups] = useState(0)
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [currentDetail, setCurrentDetail] = useState<SimilarityGroup | null>(null)
  const [recommendation, setRecommendation] = useState<KeeperRecommendation | null>(null)
  const [fileActions, setFileActions] = useState<Record<number, FileAction>>({})
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selectionProgress, setSelectionProgress] = useState<{ current: number; total: number } | null>(null)
  const [applyingPreset, setApplyingPreset] = useState(false)
  const [jumpInput, setJumpInput] = useState<string | null>(null)

  // Track which pages of summaries we've loaded
  const loadedPages = useRef(new Set<number>())

  const loadSummaryPage = useCallback(async (page: number) => {
    if (!sessionId || loadedPages.current.has(page)) return
    loadedPages.current.add(page)
    const offset = page * PAGE_SIZE
    const result = await callBackend<SimilarityGroupsPage>(
      'get_similarity_groups', { session_id: sessionId, offset, limit: PAGE_SIZE },
    )
    setTotalGroups(result.total_count)
    setGroupSummaries((prev) => {
      const next = [...prev]
      // Place groups at the correct indices
      for (let i = 0; i < result.groups.length; i++) {
        next[offset + i] = result.groups[i]
      }
      return next
    })
  }, [sessionId])

  // Initial load
  const loadInitial = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    loadedPages.current.clear()
    try {
      await loadSummaryPage(0)
    } finally {
      setLoading(false)
    }
  }, [sessionId, loadSummaryPage])

  useEffect(() => { loadInitial() }, [loadInitial])

  // Load detail for the currently selected group
  const loadDetail = useCallback(async (groupId: number) => {
    setDetailLoading(true)
    try {
      const detail = await callBackend<SimilarityGroup>(
        'get_similarity_group_detail', { group_id: groupId },
      )
      setCurrentDetail(detail)
      // Populate actions from backend-supplied action field
      const actions: Record<number, FileAction> = {}
      for (const m of detail.members) {
        if (m.action) actions[m.id] = m.action
      }
      setFileActions(actions)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  // When selectedIdx changes, ensure the summary page is loaded and fetch detail
  useEffect(() => {
    if (totalGroups === 0) return
    const page = Math.floor(selectedIdx / PAGE_SIZE)
    loadSummaryPage(page)
    const summary = groupSummaries[selectedIdx]
    if (summary) {
      loadDetail(summary.id)
    }
  }, [selectedIdx, totalGroups, groupSummaries, loadSummaryPage, loadDetail])

  // Also load detail when summaries arrive and we haven't loaded detail yet
  useEffect(() => {
    if (!currentDetail && groupSummaries[selectedIdx]) {
      loadDetail(groupSummaries[selectedIdx].id)
    }
  }, [groupSummaries, selectedIdx, currentDetail, loadDetail])

  const [compareLeft, setCompareLeft] = useState<number | null>(null)
  const [compareRight, setCompareRight] = useState<number | null>(null)

  const members = currentDetail?.members ?? []

  // Reset compare selection when group changes, default to first two members
  useEffect(() => {
    if (members.length >= 2) {
      setCompareLeft(members[0].id)
      setCompareRight(members[1].id)
      setCompareNext('left')
    } else {
      setCompareLeft(members[0]?.id ?? null)
      setCompareRight(null)
      setCompareNext(members.length === 1 ? 'right' : 'left')
    }
  }, [currentDetail?.id])

  useEffect(() => {
    if (!currentDetail?.members?.length) return
    callBackend<KeeperRecommendation>('recommend_keeper', { files: currentDetail.members })
      .then(setRecommendation)
      .catch(() => setRecommendation(null))
  }, [currentDetail])

  const [compareNext, setCompareNext] = useState<'left' | 'right'>('left')

  const handleCompareSelect = (fileId: number) => {
    if (compareLeft === fileId) {
      // Deselect left — promote right to left
      setCompareLeft(compareRight)
      setCompareRight(null)
      setCompareNext('right')
    } else if (compareRight === fileId) {
      // Deselect right
      setCompareRight(null)
      setCompareNext('right')
    } else if (compareNext === 'left') {
      setCompareLeft(fileId)
      setCompareNext('right')
    } else {
      setCompareRight(fileId)
      setCompareNext('left')
    }
  }

  const handleFileAction = useCallback(async (fileId: number, action: FileAction) => {
    setActivePreset(null)
    try {
      const result = await callBackend<{ actions: Record<string, FileAction> }>(
        'set_file_action', { file_id: fileId, action, scope: 'file' },
      )
      const updated: Record<number, FileAction> = { ...fileActions }
      for (const [id, act] of Object.entries(result.actions)) {
        updated[Number(id)] = act
      }
      setFileActions(updated)
    } catch {
      // handle error
    }
  }, [fileActions])

  const handleKeepAndDeleteOthers = useCallback(async (fileId: number) => {
    const groupFileIds = members.map((m) => m.id)
    try {
      const result = await callBackend<{ actions: Record<string, FileAction> }>(
        'keep_and_delete_others', { keep_file_id: fileId, group_file_ids: groupFileIds },
      )
      const updated: Record<number, FileAction> = { ...fileActions }
      for (const [id, act] of Object.entries(result.actions)) {
        updated[Number(id)] = act
      }
      setFileActions(updated)
    } catch {
      // handle error
    }
  }, [members, fileActions])

  const [keepMenuOpenId, setKeepMenuOpenId] = useState<number | null>(null)

  // Listen for selection progress/complete events
  useBackendEvent<{ current: number; total: number }>('selection:progress', (payload) => {
    setSelectionProgress({ current: payload.current, total: payload.total })
  })
  useBackendEvent<{ active_preset: string }>('selection:complete', (payload) => {
    setSelectionProgress(null)
    setApplyingPreset(false)
    setActivePreset(payload.active_preset)
  })

  const reloadAfterPreset = useCallback(async () => {
    loadedPages.current.clear()
    setGroupSummaries([])
    await loadSummaryPage(Math.floor(selectedIdx / PAGE_SIZE))
    const summary = groupSummaries[selectedIdx]
    if (summary) loadDetail(summary.id)
  }, [selectedIdx, groupSummaries, loadSummaryPage, loadDetail])

  const handlePreset = useCallback(async (preset: SelectionPreset) => {
    if (!sessionId) return
    setApplyingPreset(true)
    setActivePreset(preset)
    try {
      await callBackend<SelectionResult>('apply_similarity_preset', { session_id: sessionId, preset })
      await reloadAfterPreset()
    } catch {
      // handle error
    } finally {
      setApplyingPreset(false)
      setSelectionProgress(null)
    }
  }, [sessionId, reloadAfterPreset])

  const handleCustomChain = useCallback(async (criteria: SortCriterion[]) => {
    if (!sessionId) return
    setApplyingPreset(true)
    setActivePreset('custom')
    try {
      await callBackend<SelectionResult>('apply_custom_similarity_selection', { session_id: sessionId, criteria })
      await reloadAfterPreset()
    } catch {
      // handle error
    } finally {
      setApplyingPreset(false)
      setSelectionProgress(null)
    }
  }, [sessionId, reloadAfterPreset])

  if (loading) {
    return <div className="text-dv-text-muted p-8 text-center">{t('common.loading')}</div>
  }

  if (totalGroups === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-dv-text-muted gap-4">
        <Images size={48} />
        <p>{t('similarity.no_groups')}</p>
      </div>
    )
  }

  const leftFile = members.find((m) => m.id === compareLeft) ?? null
  const rightFile = members.find((m) => m.id === compareRight) ?? null

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-dv-text">{t('similarity.title')}</h1>
          <p className="text-sm text-dv-text-muted mt-1">
            {t('similarity.groups', { count: totalGroups })}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Preset toolbar */}
          <div className="space-y-2">
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

          {/* Group navigation */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setSelectedIdx(0)}
              disabled={selectedIdx === 0}
              className="px-2 py-1.5 bg-dv-surface hover:bg-dv-surface-hover border border-dv-border rounded-lg text-sm text-dv-text disabled:opacity-30"
              title={t('similarity.first_group')}
            >
              &#x21E4;
            </button>
            <button
              onClick={() => setSelectedIdx(Math.max(0, selectedIdx - 1))}
              disabled={selectedIdx === 0}
              className="px-3 py-1.5 bg-dv-surface hover:bg-dv-surface-hover border border-dv-border rounded-lg text-sm text-dv-text disabled:opacity-30"
            >
              {t('common.back')}
            </button>
            {jumpInput !== null ? (
              <input
                type="number"
                min={1}
                max={totalGroups}
                autoFocus
                className="w-16 px-2 py-1 text-sm text-center bg-dv-bg border border-dv-primary rounded text-dv-text"
                value={jumpInput}
                onChange={(e) => setJumpInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const n = parseInt(jumpInput, 10)
                    if (n >= 1 && n <= totalGroups) setSelectedIdx(n - 1)
                    setJumpInput(null)
                  } else if (e.key === 'Escape') {
                    setJumpInput(null)
                  }
                }}
                onBlur={() => setJumpInput(null)}
              />
            ) : (
              <button
                onClick={() => setJumpInput(String(selectedIdx + 1))}
                className="text-sm text-dv-text-muted px-2 py-1 hover:bg-dv-surface-hover rounded cursor-pointer"
                title={t('similarity.jump_to_group')}
              >
                {selectedIdx + 1} / {totalGroups}
              </button>
            )}
            <button
              onClick={() => setSelectedIdx(Math.min(totalGroups - 1, selectedIdx + 1))}
              disabled={selectedIdx === totalGroups - 1}
              className="px-3 py-1.5 bg-dv-surface hover:bg-dv-surface-hover border border-dv-border rounded-lg text-sm text-dv-text disabled:opacity-30"
            >
              {t('common.next')}
            </button>
            <button
              onClick={() => setSelectedIdx(totalGroups - 1)}
              disabled={selectedIdx === totalGroups - 1}
              className="px-2 py-1.5 bg-dv-surface hover:bg-dv-surface-hover border border-dv-border rounded-lg text-sm text-dv-text disabled:opacity-30"
              title={t('similarity.last_group')}
            >
              &#x21E5;
            </button>
          </div>
        </div>
      </div>

      {detailLoading ? (
        <div className="text-dv-text-muted p-8 text-center">{t('common.loading')}</div>
      ) : (
        <>
          {/* Compare slider */}
          {leftFile && rightFile && (
            <div className="bg-dv-surface rounded-xl border border-dv-border p-4 mb-6">
              <div className="flex justify-between mb-2 text-xs font-medium">
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-full bg-blue-500 inline-block" />
                  <span className="text-blue-400 truncate max-w-48" title={leftFile.path}>
                    {leftFile.path.split(/[/\\]/).pop()}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-red-400 truncate max-w-48" title={rightFile.path}>
                    {rightFile.path.split(/[/\\]/).pop()}
                  </span>
                  <span className="w-3 h-3 rounded-full bg-red-500 inline-block" />
                </div>
              </div>
              <div className="h-96 rounded-lg overflow-hidden ring-1 ring-dv-border">
                <ReactCompareSlider
                  itemOne={
                    <ReactCompareSliderImage
                      src={leftFile.thumbnail_data ?? ''}
                      alt="Left compare"
                    />
                  }
                  itemTwo={
                    <ReactCompareSliderImage
                      src={rightFile.thumbnail_data ?? ''}
                      alt="Right compare"
                    />
                  }
                />
              </div>
              <p className="text-xs text-dv-text-muted mt-2 text-center">
                {t('similarity.compare_hint')}
              </p>
            </div>
          )}

          {/* Recommendation */}
          {recommendation && (
            <div className="bg-dv-success/10 border border-dv-success/30 rounded-xl p-4 mb-6 flex items-center gap-3">
              <Star size={20} className="text-dv-success" />
              <div>
                <div className="text-sm font-medium text-dv-text">
                  {t('similarity.recommended_keeper')}
                </div>
                <div className="text-xs text-dv-text-muted">
                  {t('similarity.reason', { reason: recommendation.reason })}
                </div>
              </div>
            </div>
          )}

          {/* Member list */}
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            {members.map((file: FileInfo) => {
              const action = fileActions[file.id]
              const isLeft = compareLeft === file.id
              const isRight = compareRight === file.id
              const borderClass = isLeft
                ? 'border-blue-500 ring-2 ring-blue-500/30'
                : isRight
                  ? 'border-red-500 ring-2 ring-red-500/30'
                  : recommendation?.file_id === file.id
                    ? 'border-dv-success'
                    : 'border-dv-border'
              return (
                <div
                  key={file.id}
                  className={`bg-dv-surface rounded-xl border p-3 cursor-pointer transition-all ${borderClass}`}
                  onClick={() => handleCompareSelect(file.id)}
                >
                  <div className="relative">
                    {(isLeft || isRight) && (
                      <span className={`absolute top-1 left-1 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold text-white ${
                        isLeft ? 'bg-blue-500' : 'bg-red-500'
                      }`}>
                        {isLeft ? 'L' : 'R'}
                      </span>
                    )}
                    {file.thumbnail_data && (
                      <img
                        src={file.thumbnail_data}
                        alt=""
                        className="w-full h-40 object-cover rounded-lg mb-3"
                      />
                    )}
                  </div>
                  <div className="text-sm text-dv-text truncate" title={file.path}>
                    {file.path.split(/[/\\]/).pop()}
                  </div>
                  <div className="text-xs text-dv-text-muted mt-1 space-y-0.5">
                    <div>{formatBytes(file.size)}</div>
                    {file.width && file.height && <div>{file.width} x {file.height}</div>}
                  </div>
                  <div className="flex gap-1.5 mt-3" onClick={(e) => e.stopPropagation()}>
                    {members.length >= 4 ? (
                      <div className="flex-1 relative">
                        <div className="flex w-full">
                          <button
                            onClick={() => handleFileAction(file.id, 'keep')}
                            className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-l text-xs transition-colors ${
                              action === 'keep'
                                ? 'bg-dv-success text-white'
                                : 'bg-dv-bg hover:bg-dv-surface-hover text-dv-text-muted'
                            }`}
                            title={t('browse.actions.keep')}
                          >
                            <Check size={14} />
                            {t('browse.actions.keep')}
                          </button>
                          <button
                            onClick={() => setKeepMenuOpenId(keepMenuOpenId === file.id ? null : file.id)}
                            className={`px-1 rounded-r border-l text-xs transition-colors ${
                              action === 'keep'
                                ? 'bg-dv-success text-white border-white/30'
                                : 'bg-dv-bg hover:bg-dv-surface-hover text-dv-text-muted border-dv-border'
                            }`}
                            title={t('browse.actions.keep_delete_others')}
                          >
                            <ChevronDown size={10} />
                          </button>
                        </div>
                        {keepMenuOpenId === file.id && (
                          <div className="absolute left-0 top-full mt-1 z-20 bg-dv-surface border border-dv-border rounded shadow-lg min-w-max">
                            <button
                              onClick={() => {
                                handleKeepAndDeleteOthers(file.id)
                                setKeepMenuOpenId(null)
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
                        onClick={() => handleFileAction(file.id, 'keep')}
                        className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded text-xs transition-colors ${
                          action === 'keep'
                            ? 'bg-dv-success text-white'
                            : 'bg-dv-bg hover:bg-dv-surface-hover text-dv-text-muted'
                        }`}
                        title={t('browse.actions.keep')}
                      >
                        <Check size={14} />
                        {t('browse.actions.keep')}
                      </button>
                    )}
                    <button
                      onClick={() => handleFileAction(file.id, 'delete')}
                      className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded text-xs transition-colors ${
                        action === 'delete'
                          ? 'bg-dv-danger text-white'
                          : 'bg-dv-bg hover:bg-dv-surface-hover text-dv-text-muted'
                      }`}
                      title={t('browse.actions.delete')}
                    >
                      <Trash2 size={14} />
                      {t('browse.actions.delete')}
                    </button>
                    <button
                      onClick={() => handleFileAction(file.id, 'ignore')}
                      className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded text-xs transition-colors ${
                        action === 'ignore'
                          ? 'bg-dv-warning text-white'
                          : 'bg-dv-bg hover:bg-dv-surface-hover text-dv-text-muted'
                      }`}
                      title={t('browse.actions.ignore')}
                    >
                      <EyeOff size={14} />
                      {t('browse.actions.ignore')}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
