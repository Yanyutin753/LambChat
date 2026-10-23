/** @vitest-environment jsdom */
import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { authenticatedRequest } from "../authenticatedRequest";
import { resolveUploadFileUrl } from "../uploadFileUrl";

vi.mock("../authenticatedRequest", () => ({ authenticatedRequest: vi.fn() }));
const request = vi.mocked(authenticatedRequest);
const signed = (key = "uploads/a.png", token = "capability") =>
  new Response(
    JSON.stringify({
      url: `/api/upload/file/${key}?file_token=${token}`,
      expires_in: 3600,
    }),
  );

beforeEach(() => {
  localStorage.setItem("access_token", `account-${Math.random()}`);
  request.mockReset();
});
afterEach(() => vi.useRealTimers());

test("resolves owner uploads through app capabilities and preserves variants", async () => {
  request.mockResolvedValueOnce(signed());
  const result = await resolveUploadFileUrl(
    "/api/upload/file/uploads/a.png?thumb=1&cover=true&proxy=false#preview",
  );
  const url = new URL(result, window.location.origin);
  expect(url.searchParams.get("file_token")).toBe("capability");
  expect(url.searchParams.get("thumb")).toBe("1");
  expect(url.searchParams.get("cover")).toBe("true");
  expect(url.searchParams.get("proxy")).toBe("false");
  expect(url.hash).toBe("#preview");
  expect(request).toHaveBeenCalledTimes(1);
  const endpoint = new URL(
    String(request.mock.calls[0][0]),
    window.location.origin,
  );
  expect(endpoint.pathname).toBe("/api/upload/signed-url");
  expect(endpoint.searchParams.get("key")).toBe("uploads/a.png");
  expect(endpoint.searchParams.get("app_url")).toBe("true");
});

test("never sends account authentication to foreign origins or resolves shared capabilities again", async () => {
  for (const url of [
    "https://evil.example/api/upload/file/uploads/a.png",
    "//evil.example/api/upload/file/uploads/a.png",
    "data:image/png;base64,abc",
    "blob:example",
    "/api/upload/file/uploads/a.png?file_token=shared&thumb=1",
    "/api/upload/file/cua_screenshots/u/s/a.png",
  ]) {
    expect(await resolveUploadFileUrl(url)).toContain(url);
  }
  expect(request).not.toHaveBeenCalled();
});

test("deduplicates concurrent thumbnail and original requests by key", async () => {
  let finish!: (response: Response) => void;
  request.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const first = resolveUploadFileUrl("/api/upload/file/uploads/a.png?thumb=1");
  const second = resolveUploadFileUrl("/api/upload/file/uploads/a.png");
  await Promise.resolve();
  finish(signed());
  const urls = await Promise.all([first, second]);
  expect(request).toHaveBeenCalledTimes(1);
  expect(
    new URL(urls[0], window.location.origin).searchParams.get("thumb"),
  ).toBe("1");
  expect(
    new URL(urls[1], window.location.origin).searchParams.has("thumb"),
  ).toBe(false);
});

test("capability cache expires and never crosses account tokens", async () => {
  vi.useFakeTimers();
  request.mockImplementation(async () => signed());
  await resolveUploadFileUrl("/api/upload/file/uploads/a.png");
  await resolveUploadFileUrl("/api/upload/file/uploads/a.png");
  expect(request).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(3600_000);
  await resolveUploadFileUrl("/api/upload/file/uploads/a.png");
  expect(request).toHaveBeenCalledTimes(2);
  localStorage.setItem("access_token", "another-account");
  await resolveUploadFileUrl("/api/upload/file/uploads/a.png");
  expect(request).toHaveBeenCalledTimes(3);
});

test("rejects late capabilities after logout and retries failed signing", async () => {
  let finish!: (response: Response) => void;
  request.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const pending = resolveUploadFileUrl("/api/upload/file/uploads/a.png");
  await Promise.resolve();
  localStorage.removeItem("access_token");
  finish(signed());
  await expect(pending).rejects.toThrow();
  request.mockResolvedValueOnce(new Response("denied", { status: 404 }));
  await expect(
    resolveUploadFileUrl("/api/upload/file/uploads/a.png"),
  ).rejects.toThrow();
  request.mockResolvedValueOnce(signed());
  await expect(
    resolveUploadFileUrl("/api/upload/file/uploads/a.png"),
  ).resolves.toContain("file_token=capability");
});

test("bounds the capability cache", async () => {
  request.mockImplementation(async (input) =>
    signed(
      new URL(String(input), window.location.origin).searchParams.get("key")!,
    ),
  );
  for (let i = 0; i < 260; i++)
    await resolveUploadFileUrl(`/api/upload/file/uploads/${i}.png`);
  await resolveUploadFileUrl("/api/upload/file/uploads/0.png");
  expect(request).toHaveBeenCalledTimes(261);
});

test.each(["generated.png", "generated.mp4", "generated.mp3"])(
  "ordinary tool binary %s resolves an owner capability for media elements",
  async (name) => {
    request.mockResolvedValueOnce(
      signed(`tool_binaries/${name}`, "tool-media-capability"),
    );
    const result = await resolveUploadFileUrl(
      `/api/upload/file/tool_binaries/${name}`,
    );
    expect(
      new URL(result, window.location.origin).searchParams.get("file_token"),
    ).toBe("tool-media-capability");
    expect(request).toHaveBeenCalledTimes(1);
  },
);

test("legacy capture signing cannot expose an unsigned URL to generic media elements", async () => {
  request.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        url: "/api/upload/file/tool_binaries/private-capture.jpg",
      }),
    ),
  );
  await expect(
    resolveUploadFileUrl("/api/upload/file/tool_binaries/private-capture.jpg"),
  ).rejects.toThrow("Invalid file capability");
});
