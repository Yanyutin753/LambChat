import { afterEach, expect, test, vi } from "vitest";

import { authFetch } from "../fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("structured backend error codes become actionable localized errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { error: "invalid_attachments" } }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    ),
  );

  await expect(
    authFetch("/api/chat/stream", { method: "POST", skipAuth: true }),
  ).rejects.toThrow(
    "One or more attachments are no longer available. Remove them and upload them again.",
  );
});
