/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import BytesPreview from "../BytesPreview";
import { fetchUploadFile } from "../../documentFetchCache";
vi.mock("../../documentFetchCache", () => ({ fetchUploadFile: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
test("previews unknown-extension text and Windows Unicode without running it", async () => {
  vi.mocked(fetchUploadFile).mockResolvedValueOnce(
    new Response(new Uint8Array([255, 254, 36, 0, 65, 0])),
  );
  render(<BytesPreview url="/unknown" fileName="script.custom" />);
  expect(await screen.findByText("$A")).toBeTruthy();
  expect(screen.getByText("documents.textPreview")).toBeTruthy();
});
test("bounds binary previews and cancels the remaining download", async () => {
  const cancel = vi.fn();
  const bytes = new Uint8Array(70_000);
  bytes[0] = 80;
  bytes[1] = 75;
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
    },
    cancel,
  });
  vi.mocked(fetchUploadFile).mockResolvedValueOnce(new Response(stream));
  const { container } = render(
    <BytesPreview url="/large" fileName="large.bin" />,
  );
  expect(await screen.findByText(/documents.hexPreview/)).toBeTruthy();
  expect(screen.getByText(/documents.previewBytesLimit/)).toBeTruthy();
  expect(cancel).toHaveBeenCalledOnce();
  const preview = container.querySelector("pre")!.textContent!;
  expect(preview).toContain("0000fff0");
  expect(preview).not.toContain("00010000");
});
