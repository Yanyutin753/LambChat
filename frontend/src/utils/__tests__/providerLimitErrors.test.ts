import { createInstance } from "i18next";
import { beforeAll, expect, test } from "vitest";
import { translateApiError } from "../backendErrors";
import en from "../../i18n/locales/en.json";
import zh from "../../i18n/locales/zh.json";
import ja from "../../i18n/locales/ja.json";
import ko from "../../i18n/locales/ko.json";
import ru from "../../i18n/locales/ru.json";

const i18n = createInstance();
const quota =
  "Error code: 429 - {'error': {'type': '1308', 'message': '[1308][Usage limit reached for 5 hour. Your limit will reset at 2026-11-05 18:12:57][request-123]'}, 'type': 'error'}";
const rate =
  "Error code: 429 - {'error': {'type': '1302', 'message': '[1302][Rate limit reached for requests][request-123]'}, 'type': 'error'}";
beforeAll(async () => {
  await i18n.init({
    lng: "en",
    fallbackLng: "en",
    resources: Object.fromEntries(
      Object.entries({ en, zh, ja, ko, ru }).map(([lng, translation]) => [
        lng,
        { translation },
      ]),
    ),
  });
});

test.each(["en", "zh", "ja", "ko", "ru"])(
  "provider quota feedback preserves the supplied reset time without guessing a timezone (%s)",
  (lng) => {
    const t = i18n.getFixedT(lng);
    const result = translateApiError("internal_error", quota, undefined, t);
    expect(result).toBe(
      t("errors.providerQuotaExhaustedUntil", {
        resetAt: "2026-11-05 18:12:57",
      }),
    );
    expect(result).toContain("2026-11-05 18:12:57");
    expect(result).not.toContain("1308");
    expect(result).not.toContain("request-123");
  },
);

test("quota exhaustion without a valid reset timestamp never promises a quick retry", () => {
  const t = i18n.getFixedT("en");
  for (const reset of ["", " tomorrow", " <script>now</script>"]) {
    const error = `Error code: 429 - {'message': '[1308][Usage limit reached for 5 hour. Your limit will reset at${reset}]'}`;
    expect(translateApiError("internal_error", error, undefined, t)).toBe(
      t("errors.providerQuotaExhausted"),
    );
  }
});

test("request throttling is distinct from exhausted model quota", () => {
  const t = i18n.getFixedT("en");
  expect(translateApiError("internal_error", rate, undefined, t)).toBe(
    t("errors.providerRateLimited"),
  );
  expect(translateApiError("internal_error", rate, undefined, t)).not.toBe(
    translateApiError("internal_error", quota, undefined, t),
  );
});

test("unrelated failures and explicit application errors keep their existing meaning", () => {
  const t = i18n.getFixedT("en");
  for (const error of [
    "Usage limit reached in file report.txt",
    "Error code: 429 - unknown provider detail",
    "File 1308 was not found",
  ]) {
    expect(translateApiError("internal_error", error, undefined, t)).toBe(
      error,
    );
  }
  expect(translateApiError("forbidden", quota, undefined, t)).toBe(
    t("backendErrors.forbidden"),
  );
});
