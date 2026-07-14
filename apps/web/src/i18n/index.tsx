import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ZH } from './zh';

export type Locale = 'en' | 'zh';

const STORAGE_KEY = 'cardpilot_locale';

function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'en' || saved === 'zh') return saved;
  } catch {
    /* localStorage unavailable */
  }
  return typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('zh')
    ? 'zh'
    : 'en';
}

/**
 * Gettext-style translate: the English source string is the key.
 * Missing entries fall back to the English text, so untranslated
 * screens keep working while the dictionary grows incrementally.
 * `{name}`-style placeholders are substituted from `vars`.
 */
export type TranslateFn = (text: string, vars?: Record<string, string | number>) => string;

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: TranslateFn;
}

const I18nContext = createContext<I18nContextValue>({
  locale: 'en',
  setLocale: () => {},
  t: (text) => text,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectLocale);

  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-TW' : 'en';
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* localStorage unavailable */
    }
  }, []);

  const t = useCallback<TranslateFn>(
    (text, vars) => {
      let out = locale === 'zh' ? (ZH[text] ?? text) : text;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          out = out.replaceAll(`{${k}}`, String(v));
        }
      }
      return out;
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}

/** Compact 中/EN pill for headers and menus. */
export function LanguageToggle({ className = '' }: { className?: string }) {
  const { locale, setLocale } = useI18n();
  const next: Locale = locale === 'zh' ? 'en' : 'zh';
  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      aria-label={locale === 'zh' ? 'Switch to English' : '切換為中文'}
      title={locale === 'zh' ? 'Switch to English' : '切換為中文'}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-md border border-white/10 bg-white/5 text-[11px] font-semibold text-slate-300 hover:text-white hover:border-white/25 transition-colors ${className}`}
    >
      <span className={locale === 'zh' ? 'text-amber-400' : 'text-slate-500'}>中</span>
      <span className="text-slate-600">/</span>
      <span className={locale === 'en' ? 'text-amber-400' : 'text-slate-500'}>EN</span>
    </button>
  );
}
