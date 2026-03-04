import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Images, Star } from 'lucide-react'
import { ReactCompareSlider, ReactCompareSliderImage } from 'react-compare-slider'
import { callBackend } from '../hooks/usePyBridge.ts'
import { thumbnailUrl } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { SimilarityGroup, FileInfo, KeeperRecommendation } from '../types/api.ts'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

export function SimilarityReview() {
  const { t } = useTranslation()
  const { sessionId } = useScanStore()
  const [groups, setGroups] = useState<SimilarityGroup[]>([])
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [recommendation, setRecommendation] = useState<KeeperRecommendation | null>(null)
  const [loading, setLoading] = useState(true)

  const loadGroups = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const result = await callBackend<SimilarityGroup[]>('get_similarity_groups', sessionId)
      setGroups(result)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { loadGroups() }, [loadGroups])

  const currentGroup = groups[selectedIdx]

  useEffect(() => {
    if (!currentGroup?.members?.length) return
    callBackend<KeeperRecommendation>('recommend_keeper', currentGroup.members)
      .then(setRecommendation)
      .catch(() => setRecommendation(null))
  }, [currentGroup])

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

  const members = currentGroup?.members ?? []
  const file1 = members[0]
  const file2 = members[1]

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-dv-text">{t('similarity.title')}</h1>
          <p className="text-sm text-dv-text-muted mt-1">
            {t('similarity.groups', { count: groups.length })}
          </p>
        </div>
        <div className="flex items-center gap-2">
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

      {/* Compare slider */}
      {file1 && file2 && (
        <div className="bg-dv-surface rounded-xl border border-dv-border p-4 mb-6">
          <div className="h-96 rounded-lg overflow-hidden">
            <ReactCompareSlider
              itemOne={
                <ReactCompareSliderImage
                  src={thumbnailUrl(file1.thumbnail_path)}
                  alt="Image 1"
                />
              }
              itemTwo={
                <ReactCompareSliderImage
                  src={thumbnailUrl(file2.thumbnail_path)}
                  alt="Image 2"
                />
              }
            />
          </div>
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
        {members.map((file: FileInfo) => (
          <div
            key={file.id}
            className={`bg-dv-surface rounded-xl border p-3 ${
              recommendation?.file_id === file.id
                ? 'border-dv-success'
                : 'border-dv-border'
            }`}
          >
            {file.thumbnail_path && (
              <img
                src={thumbnailUrl(file.thumbnail_path)}
                alt=""
                className="w-full h-40 object-cover rounded-lg mb-3"
              />
            )}
            <div className="text-sm text-dv-text truncate" title={file.path}>
              {file.path.split(/[/\\]/).pop()}
            </div>
            <div className="text-xs text-dv-text-muted mt-1 space-y-0.5">
              <div>{formatBytes(file.size)}</div>
              {file.width && file.height && <div>{file.width} x {file.height}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
