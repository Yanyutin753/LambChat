import { createSingletonStore } from "../components/chat/ChatMessage/items/createSingletonStore";

// ponytail: shared for this WebView lifetime; independent WebView reloads need a native pending flag.
export const sandboxDataLocationStore = createSingletonStore<{
  saving: boolean;
  pendingRestart: "set" | "reset" | null;
  root: string | null;
}>({ saving: false, pendingRestart: null, root: null });

/** Native migration continues after its settings view closes. */
export async function updateSandboxDataLocation(
  operation: "set" | "reset",
  request: () => Promise<void>,
  root: string | null = null,
) {
  const current = sandboxDataLocationStore.get();
  if (current.saving || current.pendingRestart)
    throw new Error("Sandbox data location unavailable");
  sandboxDataLocationStore.set({ ...current, saving: true });
  try {
    await request();
    sandboxDataLocationStore.set({
      saving: false,
      pendingRestart: operation,
      root: root?.trim() ?? null,
    });
  } finally {
    sandboxDataLocationStore.set({
      ...sandboxDataLocationStore.get(),
      saving: false,
    });
  }
}
