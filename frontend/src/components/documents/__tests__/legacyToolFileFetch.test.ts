/** @vitest-environment jsdom */
import { expect, test, vi } from "vitest";
import { authenticatedRequest } from "../../../services/api/authenticatedRequest";
import { fetchUploadFile } from "../documentFetchCache";

vi.mock("../../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn(async () => new Response("owned tool bytes")),
}));

test("legacy tool downloads read authenticated proxy bytes without following storage redirects", async () => {
  vi.mocked(authenticatedRequest).mockClear();
  const source = `${window.location.origin}/api/upload/file/tool_binaries/generated.pdf`;
  expect(await (await fetchUploadFile(source)).text()).toBe("owned tool bytes");
  expect(authenticatedRequest).toHaveBeenCalledTimes(1);
  expect(authenticatedRequest).toHaveBeenCalledWith(
    `${source}?proxy=true`,
    expect.objectContaining({
      cache: "no-store",
      redirect: "error",
    }),
  );
});

test("shared tool downloads use the supplied capability without owner authentication", async () => {
  vi.mocked(authenticatedRequest).mockClear();
  const request = vi.fn(async () => new Response("shared tool bytes"));
  vi.stubGlobal("fetch", request);
  try {
    const source = `${window.location.origin}/api/upload/file/tool_binaries/shared.pdf?file_token=shared-download`;
    expect(await (await fetchUploadFile(source)).text()).toBe(
      "shared tool bytes",
    );
    expect(request).toHaveBeenCalledWith(source, undefined);
    expect(authenticatedRequest).not.toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});
