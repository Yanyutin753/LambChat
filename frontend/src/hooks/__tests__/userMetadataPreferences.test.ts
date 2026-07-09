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
  expect(localStorage.getItem("lamb-agent-theme")).toBe("dark");
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
