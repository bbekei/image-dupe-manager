import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import Markdown from 'react-markdown'

import helpEn from '@help/USER_GUIDE.md?raw'
import helpHu from '@help/USER_GUIDE_HU.md?raw'

const guides: Record<string, string> = {
  en: helpEn,
  hu: helpHu,
}

export function Help() {
  const { t, i18n } = useTranslation()

  const content = useMemo(() => {
    return guides[i18n.language] ?? guides.en
  }, [i18n.language])

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-dv-text mb-6">{t('help.title')}</h1>
      <div
        className={[
          'prose max-w-none',
          'prose-headings:text-dv-text',
          'prose-p:text-dv-text-muted',
          'prose-li:text-dv-text-muted',
          'prose-a:text-dv-primary hover:prose-a:text-dv-primary-hover',
          'prose-strong:text-dv-text',
          'prose-code:text-dv-primary prose-code:bg-dv-surface prose-code:px-1 prose-code:rounded',
          'prose-pre:bg-dv-surface prose-pre:border prose-pre:border-dv-border',
          'prose-blockquote:border-dv-primary prose-blockquote:text-dv-text-muted',
          'prose-th:text-dv-text prose-td:text-dv-text-muted',
          'prose-hr:border-dv-border',
        ].join(' ')}
      >
        <Markdown>{content}</Markdown>
      </div>
    </div>
  )
}
