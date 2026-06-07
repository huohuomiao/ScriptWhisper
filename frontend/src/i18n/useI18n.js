import { useCallback, useEffect, useMemo, useState } from "react";

import { DEFAULT_LOCALE, dictionaries, languageOptions } from "./dictionaries.js";

const STORAGE_KEY = "scriptwhisper.uiLanguage";

export function useI18n() {
  const [locale, setLocaleState] = useState(loadLocale);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, locale);
  }, [locale]);

  const t = useCallback(
    (key, values = {}) => {
      const template = dictionaries[locale]?.[key] ?? dictionaries[DEFAULT_LOCALE]?.[key] ?? key;
      return Object.entries(values).reduce(
        (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
        template,
      );
    },
    [locale],
  );

  const localeOption = useMemo(
    () => languageOptions.find((language) => language.id === locale) || languageOptions[0],
    [locale],
  );

  const setLocale = useCallback((nextLocale) => {
    setLocaleState(dictionaries[nextLocale] ? nextLocale : DEFAULT_LOCALE);
  }, []);

  return {
    locale,
    localeLabel: localeOption.label,
    languageOptions,
    setLocale,
    t,
  };
}

function loadLocale() {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return dictionaries[saved] ? saved : DEFAULT_LOCALE;
  } catch {
    return DEFAULT_LOCALE;
  }
}
