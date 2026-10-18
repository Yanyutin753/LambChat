import { createInstance } from "i18next";
import { expect, test } from "vitest";
import en from "../locales/en.json";
import zh from "../locales/zh.json";
import ja from "../locales/ja.json";
import ko from "../locales/ko.json";
import ru from "../locales/ru.json";

test.each(Object.entries({ en, zh, ja, ko, ru }))(
  "%s resolves the quota reset confirmation from real locale resources",
  async (language, translation) => {
    const i18n = createInstance();
    await i18n.init({
      lng: language,
      resources: { [language]: { translation } },
      fallbackLng: false,
    });
    for (const suffix of [
      "ConfirmTitle",
      "FiveHourConfirm",
      "WeeklyConfirm",
      "LegacyConfirm",
    ]) {
      const key = `usage.reset${suffix}`;
      expect(i18n.exists(key), key).toBe(true);
      expect(i18n.t(key)).not.toBe(key);
    }
  },
);
