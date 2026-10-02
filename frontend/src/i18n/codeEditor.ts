import i18n from "./index";
import en from "./locales/codeEditor/en.json";
import zh from "./locales/codeEditor/zh.json";
import ja from "./locales/codeEditor/ja.json";
import ko from "./locales/codeEditor/ko.json";
import ru from "./locales/codeEditor/ru.json";

// CodeMirror is lazy-loaded; keep its phrases in the same lazy boundary.
for (const [language, codeEditor] of Object.entries({ en, zh, ja, ko, ru })) {
  i18n.addResourceBundle(language, "translation", { codeEditor }, true, true);
}
