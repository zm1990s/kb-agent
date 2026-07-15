'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import { detectLocale, saveLocale, type Locale } from '@/lib/locale';

interface LocaleContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
}

export const LocaleContext = createContext<LocaleContextValue>({
  locale: 'zh',
  setLocale: () => {},
});

export function useLocale() {
  return useContext(LocaleContext);
}

export default function IntlProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('zh');
  const [messages, setMessages] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    setLocaleState(detectLocale());
  }, []);

  useEffect(() => {
    import(`../messages/${locale}.json`).then((mod) => {
      setMessages(mod.default);
    });
  }, [locale]);

  function setLocale(l: Locale) {
    saveLocale(l);
    setLocaleState(l);
  }

  if (!messages) return null;

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      <NextIntlClientProvider locale={locale} messages={messages}>
        {children}
      </NextIntlClientProvider>
    </LocaleContext.Provider>
  );
}
