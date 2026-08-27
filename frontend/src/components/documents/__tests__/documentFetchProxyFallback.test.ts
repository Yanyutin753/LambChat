import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  buildProxyFallbackUrl,
  clearDocumentFetchCaches,
  fetchDocumentText,
  fetchUploadFile,
  mediaProxyFallbackSrc,
} from "../documentFetchCache";

function okResponse(body: string): Response {
  return new Response(body, { status: 200 });
}

beforeEach(() => {
  clearDocumentFetchCaches();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("buildProxyFallbackUrl", () => {
  test("appends proxy=true to a relative upload proxy URL", () => {
    expect(buildProxyFallbackUrl("/api/upload/file/a/b.txt")).toBe(
      "/api/upload/file/a/b.txt?proxy=true",
    );
  });

  test("appends proxy=true to an absolute upload proxy URL", () => {
    expect(
      buildProxyFallbackUrl("https://lambchat.com/api/upload/file/a/b.txt"),
    ).toBe("https://lambchat.com/api/upload/file/a/b.txt?proxy=true");
  });

  test("merges with an existing query string", () => {
    expect(
      buildProxyFallbackUrl("/api/upload/file/a/b.txt?direct=true"),
    ).toBe("/api/upload/file/a/b.txt?direct=true&proxy=true");
  });

  test("returns null when proxy=true is already present", () => {
    expect(
      buildProxyFallbackUrl("/api/upload/file/a/b.txt?proxy=true"),
    ).toBeNull();
  });

  test("returns null for non upload-proxy URLs", () => {
    expect(buildProxyFallbackUrl("https://oss.example.com/a/b.txt")).toBeNull();
    expect(buildProxyFallbackUrl("https://example.com/api/other")).toBeNull();
  });
});

describe("fetchDocumentText proxy fallback", () => {
  test("retries through the app proxy when the redirect target is unreachable", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(okResponse("# code"));
    vi.stubGlobal("fetch", fetchMock);

    const text = await fetchDocumentText(
      "/api/upload/file/revealed_files/x.R",
    );

    expect(text).toBe("# code");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/upload/file/revealed_files/x.R?proxy=true",
    );
  });

  test("retries through the app proxy when the upstream responds with an error status", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("bad gateway", { status: 502 }))
      .mockResolvedValueOnce(okResponse("ok"));
    vi.stubGlobal("fetch", fetchMock);

    const text = await fetchDocumentText("/api/upload/file/a.txt");

    expect(text).toBe("ok");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("does not retry non upload-proxy URLs on network failure", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchDocumentText("https://oss.example.com/a.txt"),
    ).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("throws when the proxy retry also fails", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchDocumentText("/api/upload/file/a.txt"),
    ).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // 失败后不缓存，下次点击可重试
    await expect(fetchDocumentText("/api/upload/file/a.txt")).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  test("succeeds on the first attempt without touching the proxy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse("fine"));
    vi.stubGlobal("fetch", fetchMock);

    const text = await fetchDocumentText("/api/upload/file/a.txt");

    expect(text).toBe("fine");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("fetchUploadFile init passthrough", () => {
  test("forwards RequestInit (e.g. abort signal) to direct and proxy attempts", async () => {
    const controller = new AbortController();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("bad gateway", { status: 502 }))
      .mockResolvedValueOnce(okResponse("ok"));
    vi.stubGlobal("fetch", fetchMock);

    const res = await fetchUploadFile("/api/upload/file/a.bin", {
      signal: controller.signal,
    });

    expect(await res.text()).toBe("ok");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/upload/file/a.bin");
    expect(fetchMock.mock.calls[0][1]).toEqual({ signal: controller.signal });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/upload/file/a.bin?proxy=true");
    expect(fetchMock.mock.calls[1][1]).toEqual({ signal: controller.signal });
  });

  test("does not proxy-retry a request aborted before the call", async () => {
    const controller = new AbortController();
    controller.abort();
    const abortError = new DOMException("Aborted", "AbortError");
    const fetchMock = vi.fn().mockRejectedValue(abortError);
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchUploadFile("/api/upload/file/a.bin", {
        signal: controller.signal,
      }),
    ).rejects.toThrow(abortError);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("does not proxy-retry when the first attempt is aborted mid-flight", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new DOMException("Aborted", "AbortError"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchUploadFile("/api/upload/file/a.bin"),
    ).rejects.toThrow("Aborted");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("mediaProxyFallbackSrc", () => {
  test("returns the proxy src once for an upload-file element src", () => {
    const el = {
      src: "https://lambchat.com/api/upload/file/a.mp4",
      dataset: {} as Record<string, string | undefined>,
    };
    expect(mediaProxyFallbackSrc(el)).toBe(
      "https://lambchat.com/api/upload/file/a.mp4?proxy=true",
    );
    expect(el.dataset.proxyFallback).toBe("1");
    expect(mediaProxyFallbackSrc(el)).toBeNull();
  });

  test("returns null for non upload element srcs", () => {
    const el = {
      src: "https://oss.example.com/a.mp4",
      dataset: {} as Record<string, string | undefined>,
    };
    expect(mediaProxyFallbackSrc(el)).toBeNull();
    expect(el.dataset.proxyFallback).toBeUndefined();
  });
});
