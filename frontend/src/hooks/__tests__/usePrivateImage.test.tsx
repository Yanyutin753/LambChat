/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { usePrivateImage } from "../usePrivateImage";
import { authenticatedRequest } from "../../services/api/authenticatedRequest";
vi.mock("../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn(),
}));
afterEach(() => vi.restoreAllMocks());

test("private capture loads with auth and revokes its blob on unmount", async () => {
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:private");
      static revokeObjectURL = vi.fn();
    },
  );
  vi.mocked(authenticatedRequest).mockResolvedValue(
    new Response("image", { headers: { "Content-Type": "image/jpeg" } }),
  );
  const url = `${window.location.origin}/api/upload/file/cua_screenshots/u/s/a.jpg?thumb=1`;
  const { result, unmount } = renderHook(() => usePrivateImage(url));
  await waitFor(() => expect(result.current.src).toBe("blob:private"));
  expect(authenticatedRequest).toHaveBeenCalledWith(
    url,
    expect.objectContaining({ cache: "no-store", redirect: "error" }),
  );
  unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:private");
  vi.unstubAllGlobals();
});

test("external image never receives account credentials", () => {
  vi.mocked(authenticatedRequest).mockClear();
  const src = "https://untrusted.example/api/upload/file/cua_screenshots/a.jpg";
  const { result } = renderHook(() => usePrivateImage(src));
  expect(result.current.src).toBe(src);
  expect(authenticatedRequest).not.toHaveBeenCalled();
});

test("legacy private tool screenshot also loads with authentication", async () => {
  vi.mocked(authenticatedRequest).mockReset();
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:legacy");
      static revokeObjectURL = vi.fn();
    },
  );
  vi.mocked(authenticatedRequest).mockResolvedValue(
    new Response("image", { headers: { "Content-Type": "image/jpeg" } }),
  );
  const src = `${window.location.origin}/api/upload/file/tool_binaries/old.jpg`;
  const { result, unmount } = renderHook(() => usePrivateImage(src));
  await waitFor(() => expect(result.current.src).toBe("blob:legacy"));
  expect(authenticatedRequest).toHaveBeenCalledTimes(1);
  expect(authenticatedRequest).toHaveBeenCalledWith(
    src,
    expect.objectContaining({ cache: "no-store", redirect: "manual" }),
  );
  unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:legacy");
  vi.unstubAllGlobals();
});

test("ordinary tool image resolves an owner capability after its authenticated storage redirect", async () => {
  localStorage.setItem("access_token", "tool-image-owner");
  vi.mocked(authenticatedRequest).mockReset();
  vi.mocked(authenticatedRequest)
    .mockResolvedValueOnce({ type: "opaqueredirect" } as Response)
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          url: "/api/upload/file/tool_binaries/public.jpg?file_token=tool-owner-capability",
        }),
      ),
    );
  const src = `${window.location.origin}/api/upload/file/tool_binaries/public.jpg`;
  const { result } = renderHook(() => usePrivateImage(src));
  await waitFor(() =>
    expect(authenticatedRequest).toHaveBeenCalledWith(
      src,
      expect.objectContaining({ redirect: "manual" }),
    ),
  );
  expect(result.current.src).not.toBe(src);
  await waitFor(() =>
    expect(result.current.src).toContain("file_token=tool-owner-capability"),
  );
  act(() => {
    expect(result.current.retryWithProxy()).toBe(true);
  });
  expect(new URL(result.current.src!).searchParams.get("proxy")).toBe("true");
  expect(new URL(result.current.src!).searchParams.get("file_token")).toBe(
    "tool-owner-capability",
  );
  localStorage.clear();
});

test("late private response cannot replace a newly selected image", async () => {
  let resolve!: (response: Response) => void;
  vi.mocked(authenticatedRequest).mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const source = `${window.location.origin}/api/upload/file/cua_screenshots/u/s/slow.jpg`;
  const { result, rerender } = renderHook(({ src }) => usePrivateImage(src), {
    initialProps: { src: source },
  });
  await waitFor(() => expect(resolve).toBeTypeOf("function"));
  rerender({ src: "https://example.org/next.jpg" });
  await act(async () => {
    resolve(new Response("old", { headers: { "Content-Type": "image/jpeg" } }));
  });
  await waitFor(() =>
    expect(result.current.src).toBe("https://example.org/next.jpg"),
  );
});

test("ordinary upload images wait for owner capability and keep it on proxy fallback", async () => {
  localStorage.setItem("access_token", "image-owner");
  vi.mocked(authenticatedRequest).mockReset();
  vi.mocked(authenticatedRequest).mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        url: "/api/upload/file/uploads/private.png?file_token=owner-capability",
        expires_in: 3600,
      }),
    ),
  );
  const source = `${window.location.origin}/api/upload/file/uploads/private.png?thumb=1`;
  const { result } = renderHook(() => usePrivateImage(source));
  expect(result.current.src).toBeUndefined();
  await waitFor(() =>
    expect(result.current.src).toContain("file_token=owner-capability"),
  );
  expect(new URL(result.current.src!).searchParams.get("thumb")).toBe("1");
  act(() => {
    expect(result.current.retryWithProxy()).toBe(true);
  });
  expect(new URL(result.current.src!).searchParams.get("proxy")).toBe("true");
  expect(new URL(result.current.src!).searchParams.get("file_token")).toBe(
    "owner-capability",
  );
  localStorage.clear();
});

test("shared tool images retain their existing capability without account authentication", () => {
  vi.mocked(authenticatedRequest).mockClear();
  const src = `${window.location.origin}/api/upload/file/tool_binaries/shared.jpg?file_token=share-capability&thumb=1`;
  const { result } = renderHook(() => usePrivateImage(src));
  expect(result.current.src).toBe(src);
  expect(authenticatedRequest).not.toHaveBeenCalled();
});
