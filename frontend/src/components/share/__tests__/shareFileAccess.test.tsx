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
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  copy: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
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
    update: mocks.update,
  },
}));
vi.mock("../../../services/api/session", () => ({
  sessionApi: { list: vi.fn(), getRuns: vi.fn() },
}));

const share = {
  id: "db-share",
  share_id: "report",
  share_type: "full",
  visibility: "public",
  allow_files: true,
};
const allowFilesLabel = "share.allowFiles";
type Kind = "session" | "project";

function dialog(kind: Kind, isOpen = true) {
  return kind === "session" ? (
    <ShareDialog
      isOpen={isOpen}
      onClose={vi.fn()}
      sessionId="s"
      sessionName="Review"
    />
  ) : (
    <ShareProjectDialog
      isOpen={isOpen}
      onClose={vi.fn()}
      projectId="p"
      projectName="Review"
    />
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.list.mockResolvedValue([]);
  mocks.create.mockResolvedValue({ ...share, url: "/shared/report" });
  mocks.copy.mockResolvedValue(undefined);
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test.each<Kind>(["session", "project"])(
  "%s shares deny file access by default and submit that default explicitly",
  async (kind) => {
    render(dialog(kind));
    await waitFor(() => expect(mocks.list).toHaveBeenCalledOnce());
    expect(
      screen.getByRole("checkbox", { name: allowFilesLabel }),
    ).not.toBeChecked();
    expect(screen.getByText("share.allowFilesDesc")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "share.createShare" }));
    await waitFor(() =>
      expect(mocks.create).toHaveBeenCalledWith(
        expect.objectContaining({ allow_files: false }),
      ),
    );
  },
);

test.each<Kind>(["session", "project"])(
  "%s shares include files only after an explicit opt-in",
  async (kind) => {
    render(dialog(kind));
    fireEvent.click(screen.getByRole("checkbox", { name: allowFilesLabel }));
    fireEvent.click(screen.getByRole("button", { name: "share.createShare" }));
    await waitFor(() =>
      expect(mocks.create).toHaveBeenCalledWith(
        expect.objectContaining({ allow_files: true }),
      ),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "share.createShare" }),
      ).toBeEnabled(),
    );
    expect(
      screen.getByRole("checkbox", { name: allowFilesLabel }),
    ).not.toBeChecked();
  },
);

test.each<Kind>(["session", "project"])(
  "%s share dialogs reset file access after closing and reopening",
  async (kind) => {
    const view = render(dialog(kind));
    fireEvent.click(screen.getByRole("checkbox", { name: allowFilesLabel }));
    view.rerender(dialog(kind, false));
    view.rerender(dialog(kind));
    expect(
      screen.getByRole("checkbox", { name: allowFilesLabel }),
    ).not.toBeChecked();
  },
);

test("session editing reads the saved grant, saves revocation and returns to a private new-share default", async () => {
  mocks.list.mockResolvedValue([share]);
  mocks.update.mockResolvedValue({ ...share, allow_files: false });
  render(dialog("session"));
  fireEvent.click(
    await screen.findByRole("button", { name: "share.editShare" }),
  );
  const toggle = screen.getByRole("checkbox", { name: allowFilesLabel });
  expect(toggle).toBeChecked();
  fireEvent.click(toggle);
  fireEvent.click(screen.getByRole("button", { name: "share.saveShare" }));
  await waitFor(() =>
    expect(mocks.update).toHaveBeenCalledWith(
      "db-share",
      expect.objectContaining({ allow_files: false }),
    ),
  );
  await screen.findByRole("button", { name: "share.createShare" });
  expect(
    screen.getByRole("checkbox", { name: allowFilesLabel }),
  ).not.toBeChecked();
});

test("cancelling session editing discards the existing file grant", async () => {
  mocks.list.mockResolvedValue([share]);
  render(dialog("session"));
  fireEvent.click(
    await screen.findByRole("button", { name: "share.editShare" }),
  );
  expect(screen.getByRole("checkbox", { name: allowFilesLabel })).toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "share.cancelEdit" }));
  expect(
    screen.getByRole("checkbox", { name: allowFilesLabel }),
  ).not.toBeChecked();
});

test("legacy session shares without a file grant edit as disabled", async () => {
  const legacyShare = { ...share, allow_files: undefined };
  mocks.list.mockResolvedValue([legacyShare]);
  render(dialog("session"));
  fireEvent.click(
    await screen.findByRole("button", { name: "share.editShare" }),
  );
  expect(
    screen.getByRole("checkbox", { name: allowFilesLabel }),
  ).not.toBeChecked();
});

test("a failed session save retains the draft without claiming a successful revocation", async () => {
  mocks.list.mockResolvedValue([share]);
  mocks.update.mockRejectedValue(new Error("Unavailable"));
  render(dialog("session"));
  fireEvent.click(
    await screen.findByRole("button", { name: "share.editShare" }),
  );
  fireEvent.click(screen.getByRole("checkbox", { name: allowFilesLabel }));
  fireEvent.click(screen.getByRole("button", { name: "share.saveShare" }));
  await waitFor(() =>
    expect(mocks.error).toHaveBeenCalledWith("share.updateFailed"),
  );
  expect(screen.getByRole("button", { name: "share.saveShare" })).toBeEnabled();
  expect(mocks.success).not.toHaveBeenCalled();
});

function existingProjectToggle() {
  const checkboxes = screen.getAllByRole("checkbox", { name: allowFilesLabel });
  expect(checkboxes).toHaveLength(2);
  return checkboxes[1];
}

test("project shares show the saved grant and save revocation once while pending", async () => {
  mocks.list.mockResolvedValue([share]);
  let finish!: (value: typeof share) => void;
  mocks.update.mockImplementation(
    () =>
      new Promise<typeof share>((resolve) => {
        finish = resolve;
      }),
  );
  render(dialog("project"));
  await screen.findByText("/shared/report");
  const toggle = existingProjectToggle();
  expect(toggle).toBeChecked();
  fireEvent.click(toggle);
  expect(toggle).toBeDisabled();
  expect(toggle).toHaveAttribute("aria-busy", "true");
  expect(toggle).toBeChecked();
  fireEvent.click(toggle);
  expect(mocks.update).toHaveBeenCalledExactlyOnceWith("db-share", {
    allow_files: false,
  });
  await act(async () => finish({ ...share, allow_files: false }));
  expect(existingProjectToggle()).not.toBeChecked();
  expect(existingProjectToggle()).toBeEnabled();
});

test("a failed project grant update keeps its saved value and allows retry", async () => {
  mocks.list.mockResolvedValue([share]);
  mocks.update.mockRejectedValueOnce(new Error("Unavailable"));
  render(dialog("project"));
  await screen.findByText("/shared/report");
  fireEvent.click(existingProjectToggle());
  await waitFor(() =>
    expect(mocks.error).toHaveBeenCalledWith("share.updateFailed"),
  );
  expect(existingProjectToggle()).toBeChecked();
  expect(existingProjectToggle()).toBeEnabled();
  expect(mocks.success).not.toHaveBeenCalled();
});

test("legacy project shares without a file grant stay disabled until explicitly enabled", async () => {
  const legacyShare = { ...share, allow_files: undefined };
  mocks.list.mockResolvedValue([legacyShare]);
  mocks.update.mockResolvedValue(share);
  render(dialog("project"));
  await screen.findByText("/shared/report");
  expect(existingProjectToggle()).not.toBeChecked();
  fireEvent.click(existingProjectToggle());
  await waitFor(() =>
    expect(mocks.update).toHaveBeenCalledWith("db-share", {
      allow_files: true,
    }),
  );
  expect(existingProjectToggle()).toBeChecked();
});
