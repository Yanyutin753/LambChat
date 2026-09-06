import {
  APP_NOTIFICATION_PERMISSION_PROMPT_STORAGE_KEY,
  shouldPromptForAppNotificationPermission,
  type PromptStorage,
} from "../appNotificationPermissionPrompt";

function storage(initial?: string): PromptStorage {
  const map = new Map<string, string>(
    initial ? [[APP_NOTIFICATION_PERMISSION_PROMPT_STORAGE_KEY, initial]] : [],
  );
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
  };
}

test("prompts in packaged app runtimes after the first message", () => {
  expect(
    shouldPromptForAppNotificationPermission({
      appRuntime: "capacitor-android",
      storage: storage(),
    }),
  ).toBe(true);
  expect(
    shouldPromptForAppNotificationPermission({
      appRuntime: "tauri",
      storage: storage(),
    }),
  ).toBe(true);
});

test("does not prompt in plain browser runtimes", () => {
  expect(
    shouldPromptForAppNotificationPermission({
      appRuntime: "unsupported",
      storage: storage(),
    }),
  ).toBe(false);
});

test("never prompts twice", () => {
  expect(
    shouldPromptForAppNotificationPermission({
      appRuntime: "capacitor-android",
      storage: storage("requested"),
    }),
  ).toBe(false);
});
