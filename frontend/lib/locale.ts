export const LOCALES = ['zh', 'zh-TW', 'en', 'ja'] as const;
export type Locale = (typeof LOCALES)[number];

const LS_KEY = 'locale';

function browserLocale(): Locale {
  if (typeof navigator === 'undefined') return 'zh';
  const lang = navigator.language;
  if (lang.startsWith('zh-TW') || lang.startsWith('zh-HK') || lang.startsWith('zh-MO')) return 'zh-TW';
  if (lang.startsWith('zh')) return 'zh';
  if (lang.startsWith('ja')) return 'ja';
  if (lang.startsWith('en')) return 'en';
  return 'zh';
}

export function detectLocale(): Locale {
  if (typeof localStorage === 'undefined') return 'zh';
  const stored = localStorage.getItem(LS_KEY);
  if (stored && (LOCALES as readonly string[]).includes(stored)) return stored as Locale;
  return browserLocale();
}

export function saveLocale(locale: Locale): void {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(LS_KEY, locale);
  }
}

export function toDateLocale(locale: Locale): string {
  const map: Record<Locale, string> = {
    'zh': 'zh-CN',
    'zh-TW': 'zh-TW',
    'en': 'en-US',
    'ja': 'ja-JP',
  };
  return map[locale];
}
