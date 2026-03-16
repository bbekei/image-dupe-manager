const SUPPORTED = ['en', 'hu']

/**
 * Resolve a stored language value to a supported i18next language code.
 * - 'auto' → detect from navigator.language, falling back to 'en'
 * - 'en' / 'hu' → pass through
 * - anything else → 'en'
 */
export function resolveLanguage(lang: string): string {
  if (lang === 'auto') {
    const detected = navigator.language?.toLowerCase() ?? ''
    return SUPPORTED.find((l) => detected.startsWith(l)) ?? 'en'
  }
  return SUPPORTED.includes(lang) ? lang : 'en'
}
