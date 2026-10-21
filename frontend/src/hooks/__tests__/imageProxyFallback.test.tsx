/** @vitest-environment jsdom */
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { usePrivateImage } from "../usePrivateImage";
import { ImageWithSkeleton } from "../../components/chat/ChatMessage/ImageWithSkeleton";
import { ImageViewer } from "../../components/common/ImageViewer";
import { useDocumentPreviewState } from "../../components/documents/useDocumentPreviewState";
import { setStoredServerUrl } from "../../services/api/serverConfig";
import { authenticatedRequest } from "../../services/api/authenticatedRequest";

vi.mock("../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn(),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const source = `${window.location.origin}/api/upload/file/image/u/photo.png`;

test.each(["web", "desktop", "android", "ios"])(
  "%s images start direct and proxy only once after failure",
  (platform) => {
    if (platform === "desktop") vi.stubGlobal("__TAURI_INTERNALS__", {});
    if (platform === "android" || platform === "ios")
      vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
    setStoredServerUrl(window.location.origin);
    const error = vi.fn();
    render(<ImageWithSkeleton src={source} alt="photo" onError={error} />);
    const img = screen.getByAltText("photo");
    expect(img).toHaveAttribute("src", source);
    fireEvent.error(img);
    expect(img).toHaveAttribute("src", `${source}?proxy=true`);
    expect(img.closest(".image-with-skeleton")).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(error).not.toHaveBeenCalled();
    fireEvent.error(img);
    expect(error).toHaveBeenCalledOnce();
    expect(screen.queryByAltText("photo")).toBeNull();
  },
);

test("tries the original directly before spending proxy bandwidth after a thumbnail failure", () => {
  render(
    <ImageWithSkeleton
      src={source}
      thumbSrc={`${source}?thumb=1`}
      alt="thumb"
    />,
  );
  const img = screen.getByAltText("thumb");
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", source);
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", `${source}?thumb=1&proxy=true`);
  fireEvent.load(img);
  expect(img.closest(".image-with-skeleton")).toHaveAttribute(
    "aria-busy",
    "false",
  );
});

test("viewer silently retries with the proxy and resets to direct on manual retry or a new image", () => {
  const view = render(
    <ImageViewer src={source} alt="viewer" isOpen onClose={() => {}} />,
  );
  let img = screen.getByAltText("viewer");
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", `${source}?proxy=true`);
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.error(img);
  expect(screen.getByRole("alert")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  img = screen.getByAltText("viewer");
  expect(img).toHaveAttribute("src", source);
  fireEvent.error(img);
  view.rerender(
    <ImageViewer
      src={`${source}?v=2`}
      alt="viewer"
      isOpen
      onClose={() => {}}
    />,
  );
  expect(screen.getByAltText("viewer")).toHaveAttribute("src", `${source}?v=2`);
});

test("private images retain authenticated no-redirect fetching and never fall back to an unauthenticated URL", async () => {
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:private");
      static revokeObjectURL = vi.fn();
    },
  );
  vi.mocked(authenticatedRequest).mockResolvedValue(
    new Response("image", { headers: { "Content-Type": "image/png" } }),
  );
  const url = `${window.location.origin}/api/upload/file/cua_screenshots/u/s/a.png`;
  const { result, unmount } = renderHook(() => usePrivateImage(url));
  await waitFor(() => expect(result.current.src).toBe("blob:private"));
  expect(authenticatedRequest).toHaveBeenCalledWith(
    url,
    expect.objectContaining({ redirect: "error", cache: "no-store" }),
  );
  let handled = true;
  act(() => {
    handled = result.current.retryWithProxy();
  });
  expect(handled).toBe(false);
  expect(result.current.src).toBe("blob:private");
  unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:private");
});

test("unrelated external upload-looking URLs are never rewritten or sent credentials", () => {
  vi.mocked(authenticatedRequest).mockClear();
  const url = "https://external.example/api/upload/file/picture.png";
  const { result } = renderHook(() => usePrivateImage(url));
  expect(result.current.src).toBe(url);
  expect(result.current.retryWithProxy()).toBe(false);
  expect(authenticatedRequest).not.toHaveBeenCalled();
});

test.each(["desktop", "android", "ios"])(
  "%s document image preview exposes the direct URL without fetching a blob",
  async (platform) => {
    if (platform === "desktop") vi.stubGlobal("__TAURI_INTERNALS__", {});
    else vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
    setStoredServerUrl("https://chat.example");
    vi.stubGlobal("matchMedia", () => ({
      matches: platform !== "desktop",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response("image", { headers: { "Content-Type": "image/png" } }),
      );
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal(
      "URL",
      class extends URL {
        static createObjectURL = vi.fn(() => "blob:unwanted");
      },
    );
    const { result } = renderHook(() =>
      useDocumentPreviewState({
        path: "photo.png",
        s3Key: "image/u/photo.png",
        onClose: vi.fn(),
      }),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.imageUrl).toBe(
      "https://chat.example/api/upload/file/image/u/photo.png",
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  },
);

test("image previews with an object key keep the app redirect URL so failed signed targets can recover", async () => {
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  const { result } = renderHook(() =>
    useDocumentPreviewState({
      path: "photo.png",
      s3Key: "image/u/photo.png",
      signedUrl:
        "https://storage.example/image/u/photo.png?signature=temporary",
      onClose: vi.fn(),
    }),
  );
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.imageUrl).toBe("/api/upload/file/image/u/photo.png");
});

test("a rejected private request never renders a public URL or retries through the public proxy", async () => {
  vi.mocked(authenticatedRequest).mockResolvedValue(
    new Response("Forbidden", { status: 403 }),
  );
  render(
    <ImageWithSkeleton
      src={`${window.location.origin}/api/upload/file/cua_screenshots/u/s/denied.png`}
      alt="denied"
    />,
  );
  await waitFor(() => expect(screen.queryByAltText("denied")).toBeNull());
  expect(screen.getByText("denied")).toBeInTheDocument();
});

test("file-library image cards exhaust direct sources before a single proxy retry", async () => {
  const { FileCardPreview } = await import(
    "../../components/fileLibrary/components/FileCardPreview"
  );
  const { FileImage } = await import("lucide-react");
  render(
    <FileCardPreview
      icon={FileImage}
      preview={{
        kind: "image",
        title: "card",
        subtitle: "",
        badge: "PNG",
        lines: [],
        colorName: "blue",
        imageUrl: source,
      }}
    />,
  );
  const img = screen.getByAltText("card");
  expect(img.getAttribute("src")).toContain("cover=1");
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", source);
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", `${source}?cover=1&proxy=true`);
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", `${source}?proxy=true`);
  fireEvent.error(img);
  expect(screen.queryByAltText("card")).toBeNull();
});

test("after direct sources fail, a thumbnail proxy is tried before the original proxy and neither repeats", () => {
  const error = vi.fn();
  render(
    <ImageWithSkeleton
      src={source}
      thumbSrc={`${source}?thumb=1`}
      alt="small"
      onError={error}
    />,
  );
  const img = screen.getByAltText("small");
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", source);
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", `${source}?thumb=1&proxy=true`);
  fireEvent.error(img);
  expect(img).toHaveAttribute("src", `${source}?proxy=true`);
  fireEvent.error(img);
  expect(screen.queryByAltText("small")).toBeNull();
  expect(error).toHaveBeenCalledOnce();
});

test("loading through the proxy does not mark the failed direct source as cached", () => {
  const src = `${source}?proxy-cache-check=1`;
  const first = render(<ImageWithSkeleton src={src} alt="cache-check" />);
  fireEvent.error(screen.getByAltText("cache-check"));
  fireEvent.load(screen.getByAltText("cache-check"));
  first.unmount();
  render(<ImageWithSkeleton src={src} alt="cache-check" />);
  expect(
    screen.getByAltText("cache-check").closest(".image-with-skeleton"),
  ).toHaveAttribute("aria-busy", "true");
});

test.each(["desktop", "android", "ios"])(
  "%s viewer resolves backend-relative uploads before the first image request",
  (platform) => {
    if (platform === "desktop") vi.stubGlobal("__TAURI_INTERNALS__", {});
    else vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
    setStoredServerUrl("https://chat.example");
    render(
      <ImageViewer
        src="/api/upload/file/image/u/relative.png"
        alt="relative"
        isOpen
        onClose={() => {}}
      />,
    );
    expect(screen.getByAltText("relative")).toHaveAttribute(
      "src",
      "https://chat.example/api/upload/file/image/u/relative.png",
    );
  },
);

test("viewer relocates an upload URL from the webview origin before loading it", () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  setStoredServerUrl("https://chat.example");
  render(
    <ImageViewer
      src="tauri://localhost/api/upload/file/image/u/relative.png"
      alt="webview-origin"
      isOpen
      onClose={() => {}}
    />,
  );
  expect(screen.getByAltText("webview-origin")).toHaveAttribute(
    "src",
    "https://chat.example/api/upload/file/image/u/relative.png",
  );
});
