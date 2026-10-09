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
  unmount();
  vi.unstubAllGlobals();
});

test("public legacy image follows its storage redirect only as an unauthenticated img", async () => {
  vi.mocked(authenticatedRequest).mockResolvedValue({
    type: "opaqueredirect",
  } as Response);
  const src = `${window.location.origin}/api/upload/file/tool_binaries/public.jpg`;
  const { result } = renderHook(() => usePrivateImage(src));
  await waitFor(() =>
    expect(authenticatedRequest).toHaveBeenCalledWith(
      src,
      expect.objectContaining({ redirect: "manual" }),
    ),
  );
  await waitFor(() => expect(result.current.src).toBe(src));
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
