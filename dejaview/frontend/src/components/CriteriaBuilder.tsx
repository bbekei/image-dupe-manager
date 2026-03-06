import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowUp, ArrowDown, X, Plus } from 'lucide-react'
import type { SortCriterion, SortField } from '../types/api.ts'

const ALL_FIELDS: SortField[] = ['size', 'resolution', 'modified_at', 'path_depth', 'filename_length']

interface CriteriaBuilderProps {
  onApply: (criteria: SortCriterion[]) => void
  disabled?: boolean
  progress?: { current: number; total: number } | null
}

export function CriteriaBuilder({ onApply, disabled, progress }: CriteriaBuilderProps) {
  const { t } = useTranslation()
  const [criteria, setCriteria] = useState<SortCriterion[]>([
    { field: 'size', ascending: false },
  ])

  const usedFields = new Set(criteria.map((c) => c.field))
  const availableFields = ALL_FIELDS.filter((f) => !usedFields.has(f))

  const addCriterion = () => {
    if (availableFields.length === 0) return
    setCriteria([...criteria, { field: availableFields[0], ascending: false }])
  }

  const removeCriterion = (index: number) => {
    if (criteria.length <= 1) return
    setCriteria(criteria.filter((_, i) => i !== index))
  }

  const updateField = (index: number, field: SortField) => {
    const next = [...criteria]
    next[index] = { ...next[index], field }
    setCriteria(next)
  }

  const toggleDirection = (index: number) => {
    const next = [...criteria]
    next[index] = { ...next[index], ascending: !next[index].ascending }
    setCriteria(next)
  }

  const moveUp = (index: number) => {
    if (index === 0) return
    const next = [...criteria]
    ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
    setCriteria(next)
  }

  const moveDown = (index: number) => {
    if (index === criteria.length - 1) return
    const next = [...criteria]
    ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
    setCriteria(next)
  }

  const fieldLabel = (field: SortField, ascending: boolean): string => {
    const key = ascending ? `selection.fields.${field}_asc` : `selection.fields.${field}_desc`
    return t(key)
  }

  return (
    <div className="bg-dv-surface rounded-lg border border-dv-border p-4 space-y-3">
      <div className="text-sm font-medium text-dv-text">{t('selection.advanced_title')}</div>

      {criteria.map((c, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-xs text-dv-text-muted w-5 text-right">{i + 1}.</span>
          <select
            value={c.field}
            onChange={(e) => updateField(i, e.target.value as SortField)}
            disabled={disabled}
            className="flex-1 text-xs bg-dv-bg border border-dv-border rounded px-2 py-1.5 text-dv-text"
          >
            {ALL_FIELDS.filter((f) => f === c.field || !usedFields.has(f)).map((f) => (
              <option key={f} value={f}>{fieldLabel(f, c.ascending)}</option>
            ))}
          </select>
          <button
            onClick={() => toggleDirection(i)}
            disabled={disabled}
            className="px-2 py-1.5 text-xs bg-dv-bg border border-dv-border rounded text-dv-text-muted hover:bg-dv-surface-hover"
            title={c.ascending ? t('selection.ascending') : t('selection.descending')}
          >
            {c.ascending ? '↑ Min' : '↓ Max'}
          </button>
          <button
            onClick={() => moveUp(i)}
            disabled={disabled || i === 0}
            className="p-1 text-dv-text-muted hover:bg-dv-surface-hover rounded disabled:opacity-30"
          >
            <ArrowUp size={14} />
          </button>
          <button
            onClick={() => moveDown(i)}
            disabled={disabled || i === criteria.length - 1}
            className="p-1 text-dv-text-muted hover:bg-dv-surface-hover rounded disabled:opacity-30"
          >
            <ArrowDown size={14} />
          </button>
          <button
            onClick={() => removeCriterion(i)}
            disabled={disabled || criteria.length <= 1}
            className="p-1 text-dv-text-muted hover:text-dv-danger rounded disabled:opacity-30"
          >
            <X size={14} />
          </button>
        </div>
      ))}

      {availableFields.length > 0 && (
        <button
          onClick={addCriterion}
          disabled={disabled}
          className="flex items-center gap-1 text-xs text-dv-primary hover:text-dv-primary/80 disabled:opacity-30"
        >
          <Plus size={12} />
          {t('selection.add_criterion')}
        </button>
      )}

      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={() => onApply(criteria)}
          disabled={disabled || criteria.length === 0}
          className="px-3 py-1.5 text-xs bg-dv-primary text-white rounded hover:bg-dv-primary/90 disabled:opacity-50"
        >
          {t('selection.apply_custom')}
        </button>
        {progress && (
          <div className="flex-1 flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-dv-bg rounded-full overflow-hidden">
              <div
                className="h-full bg-dv-primary rounded-full transition-all"
                style={{ width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%` }}
              />
            </div>
            <span className="text-xs text-dv-text-muted whitespace-nowrap">
              {t('selection.applying')}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
