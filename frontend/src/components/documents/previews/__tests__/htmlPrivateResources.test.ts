/** @vitest-environment jsdom */
import { createElement } from "react";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import HtmlPreview from "../HtmlPreview";
import { resolveUploadFileUrl } from "../../../../services/api/uploadFileUrl";

vi.mock("../../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: () => false,
  invokeInShell: vi.fn(),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../services/api/uploadFileUrl", async (original) => ({
  ...(await original<
    typeof import("../../../../services/api/uploadFileUrl")
  >()),
  resolveUploadFileUrl: vi.fn(async (url: string) => {
    if (url.includes("file_token=")) return url;
    return `${window.location.origin}${url}${
      url.includes("?") ? "&" : "?"
    }file_token=viewer-private-capability`;
  }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

test("untrusted HTML cannot mint viewer capabilities for referenced private files", async () => {
  localStorage.setItem("access_token", "viewer-account");
  const content = `<img src="/api/upload/file/uploads/viewer-private.png"><style>body{background:url('/api/upload/file/uploads/viewer-private.png')}</style><script src="/api/upload/file/uploads/viewer-private.js"></script>`;
  const { container } = render(createElement(HtmlPreview, { content }));
  await waitFor(() => expect(container.querySelector("iframe")).not.toBeNull());
  expect(resolveUploadFileUrl).not.toHaveBeenCalled();
  const frame = container.querySelector("iframe")!;
  expect(frame.getAttribute("srcdoc")).toContain(content);
  expect(frame.getAttribute("srcdoc")).not.toContain(
    "viewer-private-capability",
  );
  expect(frame.getAttribute("sandbox")?.split(" ")).not.toContain(
    "allow-same-origin",
  );
});

test("HTML preserves preauthorized resource capabilities without resolving them as the viewer", async () => {
  const content = `<img src="/api/upload/file/uploads/shared.png?file_token=server-associated&thumb=1">`;
  const { container } = render(createElement(HtmlPreview, { content }));
  await waitFor(() => expect(container.querySelector("iframe")).not.toBeNull());
  expect(container.querySelector("iframe")!.getAttribute("srcdoc")).toContain(
    content,
  );
  expect(resolveUploadFileUrl).not.toHaveBeenCalled();
});
