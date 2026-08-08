import en from "../locales/en.json";
import ja from "../locales/ja.json";
import ko from "../locales/ko.json";
import ru from "../locales/ru.json";
import zh from "../locales/zh.json";

const locales = { en, ja, ko, ru, zh };

const PROJECT_SHARE_KEYS = [
  "conversations",
  "created",
  "deleted",
  "emptyProject",
  "fullProject",
  "fullProjectHint",
  "loadMore",
  "noSessions",
  "pageUnavailable",
  "partialSessions",
  "partialSessionsHint",
  "project",
  "selectAtLeastOneSession",
  "selectionLimitReached",
  "selectSessions",
  "sharedProject",
  "untitledSession",
] as const;

test("project-sharing copy exists in every supported locale", () => {
  for (const [locale, messages] of Object.entries(locales)) {
    const share = messages.share as Record<string, string>;
    const sidebar = messages.sidebar as Record<string, string>;

    for (const key of PROJECT_SHARE_KEYS) {
      expect(share[key], `${locale}.share.${key}`).toBeTruthy();
    }
    expect(sidebar.shareProject, `${locale}.sidebar.shareProject`).toBeTruthy();
  }
});

test("non-Chinese project-sharing copy does not reuse the Chinese fallback", () => {
  const chineseShare = zh.share as Record<string, string>;
  for (const locale of ["en", "ja", "ko", "ru"] as const) {
    const share = locales[locale].share as Record<string, string>;

    for (const key of PROJECT_SHARE_KEYS) {
      expect(share[key], `${locale}.share.${key}`).not.toBe(chineseShare[key]);
    }
  }
});
