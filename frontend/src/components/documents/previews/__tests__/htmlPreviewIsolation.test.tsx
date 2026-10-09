/** @vitest-environment jsdom */
import { render, waitFor, cleanup } from "@testing-library/react";
import { expect, test, vi, afterEach } from "vitest";
import HtmlPreview from "../HtmlPreview";
const native = vi.hoisted(() => ({ enabled: false, invoke: vi.fn() }));
vi.mock("../../../../services/tauri/sandboxShell", () => ({
  isShellAvailable: () => native.enabled,
  invokeInShell: native.invoke,
}));
afterEach(() => {
  cleanup();
  native.enabled = false;
  vi.clearAllMocks();
});
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
test("untrusted HTML scripts cannot share the native parent origin", () => {
  const { container } = render(
    <HtmlPreview content="<html><body><script>parent.__TAURI_INTERNALS__.invoke('device_submit_task')</script></body></html>" />,
  );
  const frame = container.querySelector("iframe")!;
  expect(frame).not.toBeNull();
  expect(frame.getAttribute("sandbox")?.split(" ")).not.toContain(
    "allow-same-origin",
  );
});

test("desktop HTML uses the standalone isolated native preview command", async () => {
  native.enabled = true;
  native.invoke.mockResolvedValue("http://127.0.0.1:45000/synthetic-preview");
  const { container } = render(<HtmlPreview content="<p>synthetic</p>" />);
  await waitFor(() =>
    expect(native.invoke).toHaveBeenCalledWith("preview_html", {
      content: expect.any(String),
    }),
  );
  await waitFor(() =>
    expect(container.querySelector("iframe")?.getAttribute("src")).toBe(
      "http://127.0.0.1:45000/synthetic-preview",
    ),
  );
  expect(
    container.querySelector("iframe")?.getAttribute("sandbox"),
  ).not.toContain("allow-same-origin");
});
