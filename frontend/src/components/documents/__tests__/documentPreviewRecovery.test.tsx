/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  useDocumentPreviewState,
  type DocumentPreviewProps,
} from "../useDocumentPreviewState";
import DocumentPreviewContent from "../DocumentPreviewContent";
import DocumentPreviewToolbar from "../DocumentPreviewToolbar";
import { clearDocumentFetchCaches } from "../documentFetchCache";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../previews/MarkdownRenderer", () => ({
  default: ({ content }: { content: string }) => <pre>{content}</pre>,
}));
vi.mock("../previews/HtmlPreview", () => ({
  default: ({ content }: { content: string }) => <article>{content}</article>,
}));

function Preview(props: Partial<DocumentPreviewProps>) {
  const state = useDocumentPreviewState({
    path: "report.md",
    onClose: vi.fn(),
    ...props,
  });
  return (
    <>
      <DocumentPreviewToolbar {...state} embedded />
      <DocumentPreviewContent {...state} />
    </>
  );
}

const fetchFile = vi.fn();
beforeEach(() => {
  clearDocumentFetchCaches();
  fetchFile.mockReset();
  vi.stubGlobal("fetch", fetchFile);
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test.each(["md", "html"])(
  "failed %s preview can retry and recover without reopening",
  async (ext) => {
    fetchFile
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(new Response("Recovered document"));
    render(
      <Preview path={`report.${ext}`} signedUrl={`/preview/retry.${ext}`} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "documents.failedToLoadFromS3",
    );
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
    expect(await screen.findByText("Recovered document")).toBeInTheDocument();
    expect(fetchFile).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("button", { name: "documents.download" }),
    ).toHaveFocus();
  },
);

test("a late previous response cannot overwrite the current file", async () => {
  let finishOld!: (response: Response) => void;
  fetchFile
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finishOld = resolve;
        }),
    )
    .mockResolvedValueOnce(new Response("Current document"));
  const view = render(<Preview path="old.md" signedUrl="/preview/old.md" />);
  view.rerender(<Preview path="current.md" signedUrl="/preview/current.md" />);
  expect(await screen.findByText("Current document")).toBeInTheDocument();
  await act(async () => {
    finishOld(new Response("Stale document"));
  });
  expect(screen.queryByText("Stale document")).toBeNull();
  expect(screen.getByText("Current document")).toBeInTheDocument();
});

test("unavailable inline content does not offer a retry with no data source", async () => {
  render(<Preview path="missing.md" />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "documents.noContent",
  );
  expect(screen.queryByRole("button", { name: "common.retry" })).toBeNull();
});
