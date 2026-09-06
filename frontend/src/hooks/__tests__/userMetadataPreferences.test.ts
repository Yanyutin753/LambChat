import { applyUserMetadataPreferences } from "../userMetadataPreferences.ts";

class LocalStorageMock {
  private store = new Map<string, string>();

  getItem(key: string) {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
}

test("normalizes retired thinking off level to low when applying metadata", () => {
  const localStorage = new LocalStorageMock();
  const events: { type: string; detail: unknown }[] = [];

  applyUserMetadataPreferences({
    metadata: { defaultThinkingLevel: "off" },
    localStorage,
    changeLanguage: () => {},
    dispatchEvent: (event) => {
      events.push({ type: event.type, detail: event.detail });
    },
  });

  expect(localStorage.getItem("defaultThinkingLevel")).toBe("low");
  expect(events).toEqual([
    { type: "thinking-preference-updated", detail: "low" },
  ]);
});

test("applies all persisted user metadata preferences to local storage and events", () => {
  const localStorage = new LocalStorageMock();
  const events: { type: string; detail: unknown }[] = [];
  const languages: string[] = [];

  applyUserMetadataPreferences({
    metadata: {
      language: "zh",
      theme: "dark",
      newlineModifier: "ctrl",
      defaultThinkingLevel: "high",
      sidebarCollapsed: "true",
      defaultModelId: "model-config-id",
      defaultModel: "openai/gpt-4.1",
    },
    localStorage,
    changeLanguage: (language) => {
      languages.push(language);
    },
    dispatchEvent: (event) => {
      events.push({ type: event.type, detail: event.detail });
    },
  });

  expect(localStorage.getItem("language")).toBe("zh");
  expect(localStorage.getItem("lambchat-theme")).toBe("dark");
  expect(localStorage.getItem("newlineModifier")).toBe("ctrl");
  expect(localStorage.getItem("defaultThinkingLevel")).toBe("high");
  expect(localStorage.getItem("lamb-sidebar-collapsed")).toBe("true");
  expect(localStorage.getItem("defaultModelId")).toBe("model-config-id");
  expect(localStorage.getItem("defaultModel")).toBe("openai/gpt-4.1");
  expect(languages).toEqual(["zh"]);
  expect(events).toEqual([
    { type: "theme:external-change", detail: "dark" },
    { type: "thinking-preference-updated", detail: "high" },
    { type: "sidebar-collapsed-changed", detail: true },
    {
      type: "model-preference-updated",
      detail: {
        modelId: "model-config-id",
        modelValue: "openai/gpt-4.1",
      },
    },
  ]);
});

test("restores font scale preference and ignores unknown values", () => {
  const localStorage = new LocalStorageMock();
  const events: { type: string; detail: unknown }[] = [];

  applyUserMetadataPreferences({
    metadata: { fontScale: "large" },
    localStorage,
    changeLanguage: () => {},
    dispatchEvent: (event) => {
      events.push({ type: event.type, detail: event.detail });
    },
  });

  expect(localStorage.getItem("lambchat-font-scale")).toBe("large");
  expect(events).toEqual([
    { type: "font-scale-external-change", detail: "large" },
  ]);

  const untouched = new LocalStorageMock();
  applyUserMetadataPreferences({
    metadata: { fontScale: "giant" },
    localStorage: untouched,
    changeLanguage: () => {},
    dispatchEvent: () => {},
  });

  expect(untouched.getItem("lambchat-font-scale")).toBe(null);
});

test("applies the persisted theme schedule and notifies the theme context", () => {
  const localStorage = new LocalStorageMock();
  const events: { type: string; detail: unknown }[] = [];

  applyUserMetadataPreferences({
    metadata: {
      theme_schedule: {
        enabled: true,
        night_start: "22:00",
        night_end: "07:00",
        night_theme: "sepia",
      },
    },
    localStorage,
    changeLanguage: () => {},
    dispatchEvent: (event) => {
      events.push({ type: event.type, detail: event.detail });
    },
  });

  expect(localStorage.getItem("lambchat-theme-schedule")).toBe(
    JSON.stringify({
      enabled: true,
      night_start: "22:00",
      night_end: "07:00",
      night_theme: "sepia",
    }),
  );
  expect(events).toContainEqual({
    type: "theme-schedule:external-change",
    detail: null,
  });
});
