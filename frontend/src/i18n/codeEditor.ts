import i18n from "./index";
import en from "./locales/codeEditor/en.json";
import zh from "./locales/codeEditor/zh.json";
import ja from "./locales/codeEditor/ja.json";
import ko from "./locales/codeEditor/ko.json";
import ru from "./locales/codeEditor/ru.json";

// Keep editor phrases lazy without making an unloaded locale look complete.
function registerLoadedLocales() {
  for (const [language, codeEditor] of Object.entries({ en, zh, ja, ko, ru })) {
    if (i18n.hasResourceBundle(language, "translation")) {
      i18n.addResourceBundle(language, "translation", { codeEditor }, true, true);
    }
  }
}

registerLoadedLocales();
i18n.on("loaded", registerLoadedLocales);
