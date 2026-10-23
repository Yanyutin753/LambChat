/** @vitest-environment jsdom */
import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { resolveUploadFileUrl } from "../../../services/api/uploadFileUrl";
import {
  clearDocumentFetchCaches,
  fetchDocumentText,
  fetchUploadFile,
} from "../documentFetchCache";
vi.mock("../../../services/api/uploadFileUrl", async (original) => ({
  ...(await original<typeof import("../../../services/api/uploadFileUrl")>()),
  resolveUploadFileUrl: vi.fn(
    async (url: string) =>
      `${url}${url.includes("?") ? "&" : "?"}file_token=capability`,
  ),
}));
beforeEach(() => {
  clearDocumentFetchCaches();
  vi.mocked(resolveUploadFileUrl).mockClear();
  localStorage.setItem("access_token", "owner-a");
});
afterEach(() => vi.unstubAllGlobals());

test("document reads resolve a capability before direct and proxy fetches", async () => {
  const request = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("unreachable"))
    .mockResolvedValueOnce(new Response("private"));
  vi.stubGlobal("fetch", request);
  expect(await fetchDocumentText("/api/upload/file/uploads/a.txt")).toBe(
    "private",
  );
  expect(request.mock.calls[0][0]).toBe(
    "/api/upload/file/uploads/a.txt?resolve_resources=true&file_token=capability",
  );
  expect(request.mock.calls[1][0]).toBe(
    "/api/upload/file/uploads/a.txt?resolve_resources=true&file_token=capability&proxy=true",
  );
});

test("document content cache does not return another account's file", async () => {
  const request = vi
    .fn()
    .mockResolvedValueOnce(new Response("owner-a"))
    .mockResolvedValueOnce(new Response("owner-b"));
  vi.stubGlobal("fetch", request);
  expect(await fetchDocumentText("/api/upload/file/uploads/a.txt")).toBe(
    "owner-a",
  );
  localStorage.setItem("access_token", "owner-b");
  expect(await fetchDocumentText("/api/upload/file/uploads/a.txt")).toBe(
    "owner-b",
  );
  expect(request).toHaveBeenCalledTimes(2);
});

test("downloads resolve the same private-file capability", async () => {
  const request = vi.fn().mockResolvedValueOnce(new Response("bytes"));
  vi.stubGlobal("fetch", request);
  await fetchUploadFile("/api/upload/file/uploads/a.zip");
  expect(resolveUploadFileUrl).toHaveBeenCalledWith(
    "/api/upload/file/uploads/a.zip",
  );
  expect(request.mock.calls[0][0]).toContain("file_token=capability");
});

test("shared text previews request nested resource projection while downloads keep original bytes", async () => {
  const request = vi.fn().mockResolvedValue(new Response("html"));
  vi.stubGlobal("fetch", request);
  await fetchDocumentText(
    "/api/upload/file/uploads/page.html?file_token=share",
  );
  expect(
    new URL(
      String(request.mock.calls[0][0]),
      window.location.origin,
    ).searchParams.get("resolve_resources"),
  ).toBe("true");
  request.mockResolvedValueOnce(new Response("original"));
  await fetchUploadFile("/api/upload/file/uploads/page.html?file_token=share");
  expect(
    new URL(
      String(request.mock.calls[1][0]),
      window.location.origin,
    ).searchParams.has("resolve_resources"),
  ).toBe(false);
});

test("a same-account token refresh during document loading remains valid", async () => {
  const payload = btoa(JSON.stringify({ sub: "owner" }));
  localStorage.setItem("access_token", `header.${payload}.old`);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      localStorage.setItem("access_token", `header.${payload}.new`);
      return new Response("refreshed owner document");
    }),
  );
  await expect(
    fetchDocumentText("/api/upload/file/uploads/refreshed.txt"),
  ).resolves.toBe("refreshed owner document");
});
