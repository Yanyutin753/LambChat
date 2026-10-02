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
import { ShareDialog } from "../ShareDialog";
import { ShareProjectDialog } from "../ShareProjectDialog";

const mocks = vi.hoisted(() => ({
  copy: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  list: vi.fn(),
  create: vi.fn(),
}));
vi.mock("../../../utils/clipboard", () => ({ copyToClipboard: mocks.copy }));
vi.mock("react-hot-toast", () => ({
  default: { success: mocks.success, error: mocks.error },
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../services/api/share", () => ({
  shareApi: {
    listBySession: mocks.list,
    listByProject: mocks.list,
    create: mocks.create,
  },
}));
vi.mock("../../../services/api/session", () => ({
  sessionApi: { list: vi.fn(), getRuns: vi.fn() },
}));
const share = {
  id: "db-share",
  share_id: "preview-report",
  share_type: "full",
  visibility: "public",
};
beforeEach(() => {
  vi.resetAllMocks();
  mocks.list.mockResolvedValue([share]);
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test.each(["session", "project"])(
  "%s share waits for confirmed copying and preserves retry",
  async (kind) => {
    let complete!: () => void;
    mocks.copy.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          complete = resolve;
        }),
    );
    render(
      kind === "session" ? (
        <ShareDialog
          isOpen
          onClose={vi.fn()}
          sessionId="s"
          sessionName="Review"
        />
      ) : (
        <ShareProjectDialog
          isOpen
          onClose={vi.fn()}
          projectId="p"
          projectName="Review"
        />
      ),
    );
    const button = await screen.findByRole("button", {
      name: "share.copyLink",
    });
    for (const label of kind === "session"
      ? ["share.editShare", "share.deleteShare"]
      : ["share.deleteShare"]) {
      expect(screen.getByRole("button", { name: label })).toHaveClass(
        "min-h-[44px]",
        "min-w-[44px]",
      );
    }
    fireEvent.click(button);
    expect(mocks.copy).toHaveBeenCalledOnce();
    expect(button).toBeInTheDocument();
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(mocks.success).not.toHaveBeenCalled();
    await act(async () => complete());
    const copied = await screen.findByRole("button", {
      name: "chat.message.copied",
    });
    mocks.copy.mockRejectedValueOnce(new Error("Unavailable"));
    fireEvent.click(copied);
    await waitFor(() => expect(mocks.error).toHaveBeenCalledOnce());
    expect(
      screen.getByRole("button", { name: "share.copyLink" }),
    ).toBeEnabled();
    expect(mocks.success).toHaveBeenCalledOnce();
    expect(mocks.copy).toHaveBeenLastCalledWith(
      `${window.location.origin}/shared/preview-report`,
    );
  },
);

test("a created share still refreshes when automatic clipboard copying fails", async () => {
  mocks.list.mockResolvedValueOnce([]).mockResolvedValueOnce([share]);
  mocks.create.mockResolvedValue({ url: "/shared/preview-report" });
  mocks.copy.mockRejectedValueOnce(new Error("Unavailable"));
  render(
    <ShareDialog isOpen onClose={vi.fn()} sessionId="s" sessionName="Review" />,
  );
  await waitFor(() => expect(mocks.list).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "share.createShare" }));
  await screen.findByText("/shared/preview-report");
  expect(mocks.create).toHaveBeenCalledOnce();
  expect(mocks.error).toHaveBeenCalledWith("chat.message.copyFailed");
  expect(mocks.error).not.toHaveBeenCalledWith("share.createFailed");
  expect(screen.getByRole("button", { name: "share.copyLink" })).toBeEnabled();
});
