/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { authenticatedRequest } from "../authenticatedRequest";
import { setStoredServerUrl } from "../serverUrlStore";
import { resolveUploadFileUrl } from "../uploadFileUrl";
import { buildUploadProxyUrl } from "../config";
import {
  clearDocumentFetchCaches,
  fetchDocumentText,
} from "../../../components/documents/documentFetchCache";

vi.mock("../authenticatedRequest", () => ({ authenticatedRequest: vi.fn() }));
const server = "https://lc.example.com";
const path = "/api/upload/file/uploads/private.png";
const runtimes = [
  ["Tauri macOS/Linux", "tauri://localhost", "__TAURI_INTERNALS__", {}],
  ["Tauri Windows", "http://tauri.localhost", "__TAURI_INTERNALS__", {}],
  [
    "iOS",
    "capacitor://localhost",
    "Capacitor",
    { isNativePlatform: () => true },
  ],
  [
    "Android",
    "https://localhost",
    "Capacitor",
    { isNativePlatform: () => true },
  ],
] as const;

beforeEach(() => {
  localStorage.clear();
  clearDocumentFetchCaches();
  vi.mocked(authenticatedRequest).mockReset();
  setStoredServerUrl(server);
  localStorage.setItem("access_token", `owner-${Math.random()}`);
});
afterEach(() => vi.unstubAllGlobals());

test.each(runtimes)(
  "%s can explicitly proxy a private preview without losing its capability",
  (_name, origin, global, runtime) => {
    vi.stubGlobal(global, runtime);
    vi.stubGlobal("window", { location: new URL(origin), localStorage });
    expect(buildUploadProxyUrl(`${path}?file_token=owner&thumb=1`)).toBe(
      `${server}${path}?file_token=owner&thumb=1&proxy=true`,
    );
  },
);

test.each(runtimes)(
  "%s resolves private images and documents against the configured server",
  async (_name, origin, global, runtime) => {
    vi.stubGlobal(global, runtime);
    vi.stubGlobal("window", { location: new URL(origin), localStorage });
    vi.mocked(authenticatedRequest).mockResolvedValue(
      new Response(
        JSON.stringify({ url: `${path}?file_token=owner-capability` }),
      ),
    );
    const resolved = await resolveUploadFileUrl(`${path}?thumb=1`);
    expect(resolved).toBe(
      `${server}${path}?file_token=owner-capability&thumb=1`,
    );
    expect(authenticatedRequest).toHaveBeenCalledWith(
      expect.stringContaining(`${server}/api/upload/signed-url?`),
      { cache: "no-store" },
    );

    const request = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("storage unavailable"))
      .mockResolvedValueOnce(new Response("private document"));
    vi.stubGlobal("fetch", request);
    expect(await fetchDocumentText(path)).toBe("private document");
    expect(String(request.mock.calls[0][0])).toBe(
      `${server}${path}?file_token=owner-capability&resolve_resources=true`,
    );
    expect(String(request.mock.calls[1][0])).toBe(
      `${server}${path}?file_token=owner-capability&resolve_resources=true&proxy=true`,
    );
    expect(authenticatedRequest).toHaveBeenCalledTimes(1);
    expect(request.mock.calls.every((call) => !call[1]?.headers)).toBe(true);
  },
);

test.each(runtimes)(
  "%s denies unavailable files and never signs another server's URLs",
  async (_name, origin, global, runtime) => {
    vi.stubGlobal(global, runtime);
    vi.stubGlobal("window", { location: new URL(origin), localStorage });
    vi.mocked(authenticatedRequest).mockResolvedValue(
      new Response("denied", { status: 404 }),
    );
    await expect(resolveUploadFileUrl(path)).rejects.toThrow(
      "File unavailable",
    );
    const foreign = `https://other.example.com${path}`;
    expect(await resolveUploadFileUrl(foreign)).toBe(foreign);
    expect(authenticatedRequest).toHaveBeenCalledTimes(1);
  },
);
