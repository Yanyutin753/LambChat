import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import zh from "./locales/zh.json";
import ja from "./locales/ja.json";
import ko from "./locales/ko.json";
import ru from "./locales/ru.json";
import {
  loadPluginLocaleResources,
  mergeLocaleResource,
  type PluginLocaleResource,
} from "./pluginLocales";

const SUPPORTED_LANGUAGES = ["en", "zh", "ja", "ko", "ru"];
const pluginLocaleResources = loadPluginLocaleResources();

function translationWithPluginLocales(
  language: string,
  base: PluginLocaleResource,
): PluginLocaleResource {
  return mergeLocaleResource(base, pluginLocaleResources[language] ?? {});
}

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

function syncDocumentLanguage(language: string) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = language.split("-")[0] || "en";
}

const initialLanguage = detectLanguage();

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: translationWithPluginLocales("en", en) },
    zh: { translation: translationWithPluginLocales("zh", zh) },
    ja: { translation: translationWithPluginLocales("ja", ja) },
    ko: { translation: translationWithPluginLocales("ko", ko) },
    ru: { translation: translationWithPluginLocales("ru", ru) },
  },
  lng: initialLanguage,
  fallbackLng: "en",
  showSupportNotice: false,
  interpolation: {
    escapeValue: false,
  },
});

syncDocumentLanguage(initialLanguage);
i18n.on("languageChanged", syncDocumentLanguage);

export default i18n;
