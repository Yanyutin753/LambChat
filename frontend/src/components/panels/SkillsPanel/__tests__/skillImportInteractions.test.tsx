/** @vitest-environment jsdom */
import { createRef, useState } from "react";
import userEvent from "@testing-library/user-event";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { GithubImportModal } from "../GithubImportModal";
import { ZipUploadModal } from "../ZipUploadModal";
import { PublishDialog } from "../PublishDialog";

vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function githubProps() {
  return {
    showGithubModal: true,
    setShowGithubModal: vi.fn(),
    githubUrl: "https://github.com/example/skills",
    setGithubUrl: vi.fn(),
    githubBranch: "main",
    setGithubBranch: vi.fn(),
    githubSkills: [
      {
        name: "research",
        path: "research",
        description: "A complete research workflow",
      },
    ],
    selectedGithubSkills: ["research"],
    githubLoading: false,
    githubInstalling: false,
    githubPreviewed: true,
    githubError: null as string | null,
    onGithubPreview: vi.fn(),
    onGithubSkillToggle: vi.fn(),
    onGithubInstall: vi.fn(),
    setSelectedGithubSkills: vi.fn(),
  };
}

test("GitHub import labels its fields and keeps installation explicit on mobile", () => {
  const props = githubProps();
  render(<GithubImportModal {...props} />);
  expect(
    screen.getByRole("textbox", { name: "skills.githubRepoUrl" }),
  ).toHaveValue(props.githubUrl);
  expect(
    screen.getByRole("textbox", { name: "skills.githubBranch" }),
  ).toHaveValue("main");
  expect(
    screen.getByRole("button", { name: "skills.installSelected" }),
  ).toHaveAccessibleName("skills.installSelected");
  expect(screen.queryByRole("button", { name: "skills.exportZip" })).toBeNull();
  const checkbox = screen.getByRole("checkbox", { name: "research" });
  expect(checkbox.closest("label")).not.toBeNull();
  fireEvent.click(screen.getByText("research", { selector: "p" }));
  fireEvent.keyDown(checkbox, { key: " " });
  expect(props.onGithubSkillToggle).toHaveBeenCalledTimes(2);
});

test("GitHub preview failure stays inside the form with a retry action", () => {
  const props = {
    ...githubProps(),
    githubSkills: [],
    selectedGithubSkills: [],
    githubPreviewed: false,
    githubError: "Preview unavailable",
  };
  render(<GithubImportModal {...props} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Preview unavailable");
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(props.onGithubPreview).toHaveBeenCalledOnce();
});

test("ZIP selection opens a native file chooser from the keyboard-accessible upload button", () => {
  const ref = createRef<HTMLInputElement>();
  const click = vi
    .spyOn(HTMLInputElement.prototype, "click")
    .mockImplementation(() => {});
  render(
    <ZipUploadModal
      showZipModal
      setShowZipModal={vi.fn()}
      zipFile={null}
      zipUploading={false}
      zipPreviewing={false}
      zipSkills={[]}
      selectedZipSkills={[]}
      zipInputRef={ref}
      isDragging={false}
      onZipFileChange={vi.fn()}
      onDragOver={vi.fn()}
      onDragLeave={vi.fn()}
      onDrop={vi.fn()}
      onZipSkillToggle={vi.fn()}
      onZipSelectAll={vi.fn()}
      onZipUpload={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "skills.dropZoneTitle" }));
  expect(click).toHaveBeenCalledOnce();
});

test("publishing exposes a busy state and prevents duplicate submission or dismissal", () => {
  const close = vi.fn();
  const confirm = vi.fn();
  render(
    <PublishDialog
      publishConfirm={{
        isOpen: true,
        localSkillName: "research",
        marketplaceSkillName: "research",
        description: "Research",
        tagsInput: "one,two,three,four,five,six,seven",
        isPublished: false,
      }}
      isPublishing
      setPublishConfirm={close}
      onConfirm={confirm}
    />,
  );
  expect(
    screen.getByRole("form", { name: "skills.publishTitle" }),
  ).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("button", { name: "skills.publish" })).toBeDisabled();
  expect(
    screen.getByRole("textbox", { name: "skills.publishMarketplaceName" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "common.cancel" })).toBeDisabled();
  expect(screen.getByText("+4")).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).not.toHaveBeenCalled();
});

test("publication retains its modal keyboard boundary during submission and after failure", async () => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([
    {} as DOMRect,
  ] as unknown as DOMRectList);
  let release!: () => void;
  function PendingPublication() {
    const [pending, setPending] = useState(false);
    release = () => setPending(false);
    return (
      <PublishDialog
        publishConfirm={{
          isOpen: true,
          localSkillName: "research",
          marketplaceSkillName: "research",
          description: "Research",
          tagsInput: "",
          isPublished: false,
        }}
        isPublishing={pending}
        setPublishConfirm={vi.fn()}
        onConfirm={() => setPending(true)}
      />
    );
  }
  render(<PendingPublication />);
  await userEvent.click(screen.getByRole("button", { name: "skills.publish" }));
  expect(screen.getByRole("dialog")).toHaveFocus();
  act(() => release());
  expect(fireEvent.keyDown(document, { key: "Tab", shiftKey: true })).toBe(
    false,
  );
  expect(screen.getByRole("dialog")).toContainElement(
    document.activeElement as HTMLElement,
  );
  expect(screen.getByRole("dialog")).not.toHaveFocus();
});
