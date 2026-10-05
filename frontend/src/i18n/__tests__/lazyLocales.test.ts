import { afterEach, beforeEach, expect, test, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.doUnmock("../locales/zh.json");
});

function browserLanguage(saved: string | null, browser = "en-US") {
  vi.stubGlobal("window", {});
  vi.stubGlobal("localStorage", { getItem: () => saved });
  vi.stubGlobal("navigator", { language: browser });
}

test("English startup does not load other language bundles", async () => {
  const { default: i18n, i18nReady } = await import("../index");
  await i18nReady;

  expect(i18n.t("common.cancel")).toBe("Cancel");
  for (const language of ["zh", "ja", "ko", "ru"]) {
    expect(i18n.hasResourceBundle(language, "translation")).toBe(false);
  }
});

test("startup waits for the saved language and keeps English as fallback", async () => {
  browserLanguage("zh", "ja-JP");
  const { default: i18n, i18nReady } = await import("../index");
  await i18nReady;

  expect(i18n.isInitialized).toBe(true);
  expect(i18n.t("common.cancel")).toBe("取消");
  expect(i18n.hasResourceBundle("en", "translation")).toBe(true);
  expect(i18n.hasResourceBundle("ja", "translation")).toBe(false);
});

test("language switches load translations on demand and reuse them", async () => {
  const { default: i18n, i18nReady } = await import("../index");
  await i18nReady;

  for (const language of ["zh", "ja", "ko", "ru"]) {
    await i18n.changeLanguage(language);
    expect(i18n.hasResourceBundle(language, "translation")).toBe(true);
    expect(i18n.t("common.cancel")).not.toBe("Cancel");
    expect(i18n.t("common.cancel")).not.toBe("common.cancel");
  }
  await i18n.changeLanguage("en");
  expect(i18n.t("common.cancel")).toBe("Cancel");
  await i18n.changeLanguage("zh");
  expect(i18n.t("common.cancel")).toBe("取消");
});

test("browser language is loaded when there is no supported saved preference", async () => {
  browserLanguage("unsupported", "ko-KR");
  const { default: i18n, i18nReady } = await import("../index");
  await i18nReady;

  expect(i18n.language).toBe("ko");
  expect(i18n.hasResourceBundle("ko", "translation")).toBe(true);
  expect(i18n.hasResourceBundle("zh", "translation")).toBe(false);
});

test("editor translations do not mark an unloaded language as fully loaded", async () => {
  const { default: i18n, i18nReady } = await import("../index");
  await i18nReady;
  await import("../codeEditor");

  expect(i18n.hasResourceBundle("zh", "translation")).toBe(false);
  await i18n.changeLanguage("zh");
  expect(i18n.t("common.cancel")).toBe("取消");
  expect(i18n.t("codeEditor.find")).toBe("查找");
});

test("a failed locale download still completes startup with English text", async () => {
  browserLanguage("zh");
  vi.doMock("../locales/zh.json", () => {
    throw new Error("locale download unavailable");
  });
  const { default: i18n, i18nReady } = await import("../index");
  await i18nReady;

  expect(i18n.isInitialized).toBe(true);
  expect(i18n.t("common.cancel")).toBe("Cancel");
  expect(i18n.hasResourceBundle("zh", "translation")).toBe(false);
});
