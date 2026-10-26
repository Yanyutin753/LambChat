/** @vitest-environment jsdom */
import { expect, test, vi } from "vitest";

vi.mock("../pwaGuards", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../pwaGuards")>()),
  shouldRegisterPwa: () => true,
}));

test("a waiting update is announced and activates only after the user requests it", async () => {
  const registration = {
    waiting: { postMessage: vi.fn() },
    addEventListener: vi.fn(),
    update: vi.fn().mockResolvedValue(undefined),
  };
  vi.stubGlobal("navigator", {
    serviceWorker: {
      controller: {},
      register: vi.fn().mockResolvedValue(registration),
      addEventListener: vi.fn(),
    },
  });
  const { PWA_UPDATE_AVAILABLE_EVENT, PWA_SKIP_WAITING_MESSAGE } = await import(
    "../pwaGuards"
  );
  const available = vi.fn();
  window.addEventListener(PWA_UPDATE_AVAILABLE_EVENT, available);
  try {
    const { registerLambChatPwa, activateWaitingLambChatPwaUpdate } =
      await import("../pwa");
    registerLambChatPwa();
    window.dispatchEvent(new Event("load"));
    await vi.waitFor(() => expect(available).toHaveBeenCalled());
    expect(registration.waiting.postMessage).not.toHaveBeenCalled();
    expect(registration.update).toHaveBeenCalled();
    expect(
      activateWaitingLambChatPwaUpdate(
        registration as unknown as ServiceWorkerRegistration,
      ),
    ).toBe(true);
    expect(registration.waiting.postMessage).toHaveBeenCalledWith({
      type: PWA_SKIP_WAITING_MESSAGE,
    });
  } finally {
    window.removeEventListener(PWA_UPDATE_AVAILABLE_EVENT, available);
    vi.unstubAllGlobals();
  }
});
