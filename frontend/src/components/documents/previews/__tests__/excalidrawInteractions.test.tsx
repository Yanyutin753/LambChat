/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ExcalidrawPreview from "../ExcalidrawPreview";
import { ExcalidrawDirectViewer } from "../ExcalidrawDirectViewer";
import { ModalSurface } from "../../../common/ModalSurface";
import { clearDocumentFetchCaches } from "../../documentFetchCache";
import { ExcalidrawThumbnail } from "../../../common/ExcalidrawThumbnail";
import { ExcalidrawCardPreview } from "../ExcalidrawCardPreview";

const mocks = vi.hoisted(() => ({
  exportSvg: vi.fn(),
  t: (key: string) => key,
  exportError: vi.fn(),
}));
vi.mock("react-hot-toast", () => ({ default: { error: mocks.exportError } }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: mocks.t }),
}));
vi.mock("@excalidraw/excalidraw", () => ({ exportToSvg: mocks.exportSvg }));
const drawing = JSON.stringify({ elements: [{ id: "box" }] });
function svg() {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.setAttribute("viewBox", "0 0 100 100");
  return node;
}
beforeEach(() => {
  mocks.exportSvg.mockReset().mockImplementation(async () => svg());
  mocks.exportError.mockClear();
  clearDocumentFetchCaches();
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:drawing");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

test("failed PNG decoding reports failure and releases its temporary image URL", async () => {
  vi.stubGlobal(
    "Image",
    class {
      onerror?: () => void;
      set src(_value: string) {
        queueMicrotask(() => this.onerror?.());
      }
    },
  );
  render(<ExcalidrawPreview data={drawing} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "imageViewer.fullscreen" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "documents.download" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "PNG" }));
  await act(async () => {});
  expect(mocks.exportError).toHaveBeenCalledWith("chat.message.downloadFailed");
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:drawing");
});

test("thumbnail ignores an older export after switching to an invalid file", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response(drawing))
      .mockResolvedValueOnce(new Response("invalid")),
  );
  let finish!: (node: SVGSVGElement) => void;
  mocks.exportSvg.mockImplementationOnce(
    () =>
      new Promise<SVGSVGElement>((resolve) => {
        finish = resolve;
      }),
  );
  const view = render(
    <ExcalidrawThumbnail url="/old.excalidraw" alt="Drawing" />,
  );
  await act(async () => {});
  view.rerender(<ExcalidrawThumbnail url="/new.excalidraw" alt="Drawing" />);
  await act(async () => {});
  await act(async () => {
    finish(svg());
  });
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

test("file card clears the previous drawing when its URL changes", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response(drawing))
      .mockResolvedValueOnce(new Response("invalid")),
  );
  const view = render(<ExcalidrawCardPreview url="/card-old.excalidraw" />);
  await screen.findByRole("img");
  view.rerender(<ExcalidrawCardPreview url="/card-new.excalidraw" />);
  await act(async () => {});
  expect(screen.queryByRole("img")).toBeNull();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("drawing preview has a keyboard fullscreen entry and nested menu focus boundary", async () => {
  const close = vi.fn();
  render(
    <ModalSurface open onClose={close} label="Document">
      <ExcalidrawPreview data={drawing} />
    </ModalSurface>,
  );
  const opener = await screen.findByRole("button", {
    name: "imageViewer.fullscreen",
  });
  opener.focus();
  fireEvent.click(opener);
  const viewer = screen.getByRole("dialog", {
    name: "documents.excalidrawDiagram",
  });
  expect(viewer).toHaveFocus();
  expect(viewer).not.toHaveAttribute("data-yields-sidebar");
  fireEvent.click(
    within(viewer).getByRole("button", { name: "documents.download" }),
  );
  const menu = screen.getByRole("menu", { name: "documents.download" });
  expect(within(menu).getByRole("menuitem", { name: "SVG" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
  expect(within(menu).getByRole("menuitem", { name: "PNG" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(
    within(viewer).getByRole("button", { name: "documents.download" }),
  ).toHaveFocus();
  expect(viewer).toBeInTheDocument();
  fireEvent.keyDown(document.activeElement!, {
    key: "Escape",
    isComposing: true,
  });
  expect(viewer).toBeInTheDocument();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(
    screen.queryByRole("dialog", { name: "documents.excalidrawDiagram" }),
  ).toBeNull();
  expect(close).not.toHaveBeenCalled();
  expect(opener).toHaveFocus();
});

test("fullscreen image loading indicator disappears when the drawing loads", async () => {
  render(<ExcalidrawPreview data={drawing} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "imageViewer.fullscreen" }),
  );
  const viewer = screen.getByRole("dialog", {
    name: "documents.excalidrawDiagram",
  });
  expect(
    within(viewer).getByRole("status", { name: "documents.loadingImage" }),
  ).toBeInTheDocument();
  fireEvent.load(
    within(viewer).getByRole("img", { name: "documents.excalidrawDiagram" }),
  );
  expect(
    within(viewer).queryByRole("status", { name: "documents.loadingImage" }),
  ).toBeNull();
});

test("empty drawing data clears an earlier drawing instead of leaving stale content", async () => {
  const view = render(<ExcalidrawPreview data={drawing} />);
  await screen.findByRole("img", { name: "documents.excalidrawDiagram" });
  view.rerender(<ExcalidrawPreview data="" />);
  expect(await screen.findByText("documents.noContent")).toBeInTheDocument();
  expect(screen.queryByRole("img")).toBeNull();
});

test("late drawing export cannot overwrite a newer invalid file", async () => {
  let finish!: (node: SVGSVGElement) => void;
  mocks.exportSvg.mockImplementationOnce(
    () =>
      new Promise<SVGSVGElement>((resolve) => {
        finish = resolve;
      }),
  );
  const view = render(<ExcalidrawPreview data={drawing} />);
  await act(async () => {});
  view.rerender(<ExcalidrawPreview data="invalid" />);
  await act(async () => {
    finish(svg());
  });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "documents.invalidExcalidrawFormat",
  );
  expect(screen.queryByRole("img")).toBeNull();
});

test("direct drawing loader is dismissible while the request is pending", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  const close = vi.fn();
  render(
    <ExcalidrawDirectViewer
      url="/preview/drawing.excalidraw"
      onClose={close}
    />,
  );
  const viewer = screen.getByRole("dialog", {
    name: "documents.excalidrawDiagram",
  });
  expect(viewer).toHaveFocus();
  expect(
    within(viewer).getByRole("button", { name: "documents.download" }),
  ).toBeDisabled();
  fireEvent.keyDown(viewer, { key: "Escape" });
  expect(close).toHaveBeenCalledTimes(1);
});

test("direct drawing error can retry without losing its modal boundary", async () => {
  const fetchFile = vi
    .fn()
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce(new Response(drawing));
  vi.stubGlobal("fetch", fetchFile);
  render(
    <ExcalidrawDirectViewer
      url="/preview/retry.excalidraw"
      onClose={vi.fn()}
    />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "documents.excalidrawRenderFailed",
  );
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(
    await screen.findByRole("img", { name: "documents.excalidrawDiagram" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(fetchFile).toHaveBeenCalledTimes(2);
  expect(
    screen.getByRole("dialog", { name: "documents.excalidrawDiagram" }),
  ).toBeInTheDocument();
});
