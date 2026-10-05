import i18n, { type BackendModule, type ResourceLanguage } from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";

const localeLoaders: Record<
  string,
  () => Promise<{ default: ResourceLanguage }>
> = {
  zh: () => import("./locales/zh.json"),
  ja: () => import("./locales/ja.json"),
  ko: () => import("./locales/ko.json"),
  ru: () => import("./locales/ru.json"),
};

const localeBackend: BackendModule = {
  type: "backend",
  init() {},
  async read(language, _namespace) {
    const load = localeLoaders[language];
    return load ? (await load()).default : {};
  },
};

const SUPPORTED_LANGUAGES = ["en", "zh", "ja", "ko", "ru"];

const detectLanguage = (): string => {
  // Check if running in browser environment
  if (typeof window === "undefined") {
    return "en";
  }

  // 1. Check localStorage for saved preference
  const saved = localStorage.getItem("language");
  if (saved && SUPPORTED_LANGUAGES.includes(saved)) {
    return saved;
  }

  // 2. Detect browser language
  const browserLang = navigator.language.split("-")[0];
  if (SUPPORTED_LANGUAGES.includes(browserLang)) {
    return browserLang;
  }

  // 3. Fallback to English
  return "en";
};

export const i18nReady = i18n.use(localeBackend).use(initReactI18next).init({
  resources: {
    en: { translation: en },
  },
  partialBundledLanguages: true,
  supportedLngs: SUPPORTED_LANGUAGES,
  lng: detectLanguage(),
  fallbackLng: "en",
  showSupportNotice: false,
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
