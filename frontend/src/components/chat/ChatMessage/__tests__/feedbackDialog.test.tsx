/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { FeedbackDialog } from "../FeedbackDialog";
import { FeedbackButtons } from "../FeedbackButtons";
import { uploadApi } from "../../../../services/api/upload";
import { feedbackApi } from "../../../../services/api/feedback";
import { compressImageFile } from "../../../../utils/imageCompression";
import type { MessageAttachment, UploadResult } from "../../../../types/upload";
import { useState } from "react";

vi.mock("../../../../utils/imageCompression", () => ({
  compressImageFile: vi.fn(async (file: File) => file),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
beforeEach(() =>
  vi.mocked(compressImageFile).mockImplementation(async (file) => file),
);

const attachment: MessageAttachment = {
  id: "photo",
  key: "photo",
  name: "screen.png",
  type: "image",
  mimeType: "image/png",
  size: 8,
  url: "data:image/png;base64,",
};
const uploaded: UploadResult = { ...attachment, url: attachment.url! };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { resolve, promise };
}
function open(
  props: Partial<React.ComponentProps<typeof FeedbackDialog>> = {},
) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  const onAttachmentsChange = vi.fn();
  const view = render(
    <FeedbackDialog
      isOpen
      rating="down"
      comment="Keep my draft"
      onCommentChange={() => {}}
      onClose={onClose}
      onSubmit={onSubmit}
      onSkip={() => {}}
      isSubmitting={false}
      attachments={[]}
      onAttachmentsChange={onAttachmentsChange}
      {...props}
    />,
  );
  return { ...view, onSubmit, onClose, onAttachmentsChange };
}
function chooseFile() {
  fireEvent.change(document.querySelector('input[type="file"]')!, {
    target: {
      files: [new File(["photo"], "screen.png", { type: "image/png" })],
    },
  });
}

test("feedback image actions and comment have native accessible names", () => {
  open();
  expect(
    screen.getByRole("button", { name: "feedback.addImage" }),
  ).toHaveAttribute("type", "button");
  expect(
    screen.getByRole("textbox", { name: "feedback.commentLabel" }),
  ).toHaveFocus();
  expect(
    screen.getByRole("button", { name: /common.dismiss|common.close/ }),
  ).toBeEnabled();
});

test("attachment removal is named and submitting freezes draft controls and dismissal", () => {
  const { onClose } = open({ attachments: [attachment], isSubmitting: true });
  expect(
    screen.getByRole("button", { name: "common.remove: screen.png" }),
  ).toBeDisabled();
  expect(screen.getByRole("textbox")).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "feedback.addImage" }),
  ).toBeDisabled();
  fireEvent.keyDown(document, { key: "Escape" });
  fireEvent.click(document.querySelector("[data-dialog-backdrop]")!);
  expect(onClose).not.toHaveBeenCalled();
});

test("removing a focused attachment returns to the comment field", () => {
  function ControlledFeedback() {
    const [attachments, setAttachments] = useState([attachment]);
    return (
      <FeedbackDialog
        isOpen
        rating="down"
        comment="Keep my draft"
        onCommentChange={() => {}}
        onClose={() => {}}
        onSubmit={() => {}}
        onSkip={() => {}}
        isSubmitting={false}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
      />
    );
  }
  render(<ControlledFeedback />);
  const remove = screen.getByRole("button", {
    name: "common.remove: screen.png",
  });
  remove.focus();
  fireEvent.click(remove);
  expect(screen.queryByRole("img")).toBeNull();
  expect(
    screen.getByRole("textbox", { name: "feedback.commentLabel" }),
  ).toHaveFocus();
});

test.each(["metaKey", "ctrlKey"])(
  "%s + Enter submits once while plain and IME Enter retain the draft",
  (modifier) => {
    const { onSubmit } = open();
    const input = screen.getByRole("textbox");
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, {
      key: "Enter",
      [modifier]: true,
      isComposing: true,
    });
    fireEvent.keyDown(input, { key: "Enter", [modifier]: true, keyCode: 229 });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter", [modifier]: true });
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
  },
);

test("closing during upload aborts it and its late result cannot change another draft", async () => {
  const pending = deferred<UploadResult>();
  const abort = vi.fn();
  vi.spyOn(uploadApi, "uploadFile").mockReturnValue({
    promise: pending.promise,
    abort,
  });
  const { unmount, onAttachmentsChange } = open();
  chooseFile();
  await waitFor(() => expect(uploadApi.uploadFile).toHaveBeenCalledOnce());
  unmount();
  expect(abort).toHaveBeenCalledOnce();
  await act(async () => pending.resolve(uploaded));
  expect(onAttachmentsChange).not.toHaveBeenCalled();
});

test("closing during compression prevents the later upload from starting", async () => {
  const pending = deferred<File>();
  vi.mocked(compressImageFile).mockReturnValueOnce(pending.promise);
  const upload = vi.spyOn(uploadApi, "uploadFile");
  const { unmount } = open();
  chooseFile();
  unmount();
  await act(async () =>
    pending.resolve(new File(["photo"], "screen.png", { type: "image/png" })),
  );
  expect(upload).not.toHaveBeenCalled();
});

test("a failed upload remains visible and Retry uses the original file", async () => {
  vi.spyOn(uploadApi, "uploadFile")
    .mockReturnValueOnce({
      promise: Promise.reject(new Error("Upload unavailable")),
      abort: vi.fn(),
    })
    .mockReturnValueOnce({
      promise: Promise.resolve(uploaded),
      abort: vi.fn(),
    });
  const { onAttachmentsChange } = open();
  chooseFile();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Upload unavailable",
  );
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  await waitFor(() => expect(onAttachmentsChange).toHaveBeenCalledOnce());
  expect(uploadApi.uploadFile).toHaveBeenCalledTimes(2);
  expect(vi.mocked(uploadApi.uploadFile).mock.calls[1][0]).toBe(
    vi.mocked(uploadApi.uploadFile).mock.calls[0][0],
  );
  expect(screen.queryByRole("alert")).toBeNull();
});

test("pending uploads reject another drop and submission", async () => {
  const pending = deferred<UploadResult>();
  vi.spyOn(uploadApi, "uploadFile").mockReturnValue({
    promise: pending.promise,
    abort: vi.fn(),
  });
  const { onSubmit } = open();
  chooseFile();
  await waitFor(() => expect(uploadApi.uploadFile).toHaveBeenCalledOnce());
  const input = screen.getByRole("textbox");
  fireEvent.keyDown(input, { key: "Enter", metaKey: true });
  await act(async () => chooseFile());
  expect(uploadApi.uploadFile).toHaveBeenCalledOnce();
  expect(onSubmit).not.toHaveBeenCalled();
  await act(async () => pending.resolve(uploaded));
});

test("a feedback response after navigation cannot update a later conversation", async () => {
  const pending = deferred<Awaited<ReturnType<typeof feedbackApi.submit>>>();
  vi.spyOn(feedbackApi, "submit").mockReturnValue(pending.promise);
  const onFeedbackChange = vi.fn();
  const { unmount } = render(
    <FeedbackButtons
      sessionId="session"
      runId="run"
      onFeedbackChange={onFeedbackChange}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "feedback.negative" }));
  fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
  unmount();
  await act(async () => pending.resolve({} as never));
  expect(onFeedbackChange).not.toHaveBeenCalled();
});

test("feedback submission failure keeps the comment and offers a persistent retry", async () => {
  vi.spyOn(feedbackApi, "submit")
    .mockRejectedValueOnce(new Error("Feedback unavailable"))
    .mockResolvedValueOnce({} as never);
  render(<FeedbackButtons sessionId="session" runId="run" />);
  fireEvent.click(screen.getByRole("button", { name: "feedback.negative" }));
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Keep my comment" },
  });
  fireEvent.click(screen.getByRole("button", { name: "feedback.submit" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Feedback unavailable",
  );
  expect(screen.getByRole("textbox")).toHaveValue("Keep my comment");
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(feedbackApi.submit).toHaveBeenLastCalledWith(
    expect.objectContaining({ comment: "Keep my comment", rating: "down" }),
  );
});
