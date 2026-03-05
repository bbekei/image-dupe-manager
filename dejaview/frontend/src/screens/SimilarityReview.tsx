import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Images, Star, Check, ChevronDown, Trash2, EyeOff, Wand2 } from 'lucide-react'
import { ReactCompareSlider, ReactCompareSliderImage } from 'react-compare-slider'
import { callBackend } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { SimilarityGroup, FileInfo, FileAction, KeeperRecommendation, SelectionPreset } from '../types/api.ts'

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

export function SimilarityReview() {
  const { t } = useTranslation()
  const { sessionId } = useScanStore()
  const [groups, setGroups] = useState<SimilarityGroup[]>([])
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [recommendation, setRecommendation] = useState<KeeperRecommendation | null>(null)
  const [fileActions, setFileActions] = useState<Record<number, FileAction>>({})
  const [loading, setLoading] = useState(true)

  const loadGroups = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const result = await callBackend<SimilarityGroup[]>('get_similarity_groups', sessionId)
      setGroups(result)
      // Populate actions from backend-supplied action field
      const actions: Record<number, FileAction> = {}
      for (const g of result) {
        for (const m of g.members) {
          if (m.action) actions[m.id] = m.action
        }
      }
      setFileActions(actions)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { loadGroups() }, [loadGroups])

  const [compareLeft, setCompareLeft] = useState<number | null>(null)
  const [compareRight, setCompareRight] = useState<number | null>(null)

  const currentGroup = groups[selectedIdx]
  const members = currentGroup?.members ?? []

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
  }, [selectedIdx, currentGroup?.id])

  useEffect(() => {
    if (!currentGroup?.members?.length) return
    callBackend<KeeperRecommendation>('recommend_keeper', currentGroup.members)
      .then(setRecommendation)
      .catch(() => setRecommendation(null))
  }, [currentGroup])

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
    try {
      const result = await callBackend<{ actions: Record<string, FileAction> }>(
        'set_file_action', fileId, action, 'file',
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
        'keep_and_delete_others', fileId, groupFileIds,
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

  const handlePreset = useCallback(async (preset: SelectionPreset) => {
    if (!sessionId) return
    try {
      await callBackend('apply_similarity_preset', sessionId, preset)
      loadGroups()
    } catch {
      // handle error
    }
  }, [sessionId, loadGroups])

  if (loading) {
    return <div className="text-dv-text-muted p-8 text-center">{t('common.loading')}</div>
  }

  if (groups.length === 0) {
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
            {t('similarity.groups', { count: groups.length })}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Preset toolbar */}
          <div className="flex flex-wrap gap-1">
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

          {/* Group navigation */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setSelectedIdx(Math.max(0, selectedIdx - 1))}
              disabled={selectedIdx === 0}
              className="px-3 py-1.5 bg-dv-surface hover:bg-dv-surface-hover border border-dv-border rounded-lg text-sm text-dv-text disabled:opacity-30"
            >
              {t('common.back')}
            </button>
            <span className="text-sm text-dv-text-muted px-2">
              {selectedIdx + 1} / {groups.length}
            </span>
            <button
              onClick={() => setSelectedIdx(Math.min(groups.length - 1, selectedIdx + 1))}
              disabled={selectedIdx === groups.length - 1}
              className="px-3 py-1.5 bg-dv-surface hover:bg-dv-surface-hover border border-dv-border rounded-lg text-sm text-dv-text disabled:opacity-30"
            >
              {t('common.next')}
            </button>
          </div>
        </div>
      </div>

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
    </div>
  )
}
