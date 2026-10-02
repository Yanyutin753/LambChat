/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useSkills } from "../../../../hooks/useSkills";
import { useSkillsActions } from "../useSkillsActions";
import { GithubImportModal } from "../GithubImportModal";
import { ZipUploadModal } from "../ZipUploadModal";

vi.mock("../../../../hooks/useSkills", () => ({ useSkills: vi.fn() }));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
const previewGithub = vi.fn();
const previewZip = vi.fn();
const installGithub = vi.fn();
const uploadZip = vi.fn();
beforeEach(() => {
  vi.mocked(useSkills).mockReturnValue({
    skills: [],
    availableTags: [],
    total: 0,
    isLoading: false,
    error: null,
    previewGitHubSkills: previewGithub,
    previewZipSkills: previewZip,
    installGitHubSkills: installGithub,
    uploadSkill: uploadZip,
  } as unknown as ReturnType<typeof useSkills>);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function Imports() {
  const a = useSkillsActions();
  return (
    <>
      <button onClick={a.handleGithubClick}>Open GitHub</button>
      <button onClick={a.handleZipClick}>Open ZIP</button>
      <GithubImportModal
        showGithubModal={a.showGithubModal}
        setShowGithubModal={a.setShowGithubModal}
        githubUrl={a.githubUrl}
        setGithubUrl={a.setGithubUrl}
        githubBranch={a.githubBranch}
        setGithubBranch={a.setGithubBranch}
        githubSkills={a.githubSkills}
        selectedGithubSkills={a.selectedGithubSkills}
        githubLoading={a.githubLoading}
        githubInstalling={a.githubInstalling}
        githubPreviewed={a.githubPreviewed}
        githubError={a.githubError}
        onGithubPreview={a.handleGithubPreview}
        onGithubSkillToggle={a.handleGithubSkillToggle}
        onGithubInstall={a.handleGithubInstall}
        setSelectedGithubSkills={a.setSelectedGithubSkills}
      />
      <ZipUploadModal
        showZipModal={a.showZipModal}
        setShowZipModal={a.setShowZipModal}
        zipFile={a.zipFile}
        zipUploading={a.zipUploading}
        zipPreviewing={a.zipPreviewing}
        zipError={a.zipError}
        onZipRetry={a.handleZipRetry}
        zipSkills={a.zipSkills}
        selectedZipSkills={a.selectedZipSkills}
        zipInputRef={a.zipInputRef}
        isDragging={a.isDragging}
        onZipFileChange={a.handleZipFileChange}
        onDragOver={a.handleDragOver}
        onDragLeave={a.handleDragLeave}
        onDrop={a.handleDrop}
        onZipSkillToggle={a.handleZipSkillToggle}
        onZipSelectAll={a.handleZipSelectAll}
        onZipUpload={a.handleZipUpload}
      />
    </>
  );
}
function openGitHub() {
  render(
    <MemoryRouter>
      <Imports />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open GitHub" }));
  fireEvent.change(
    screen.getByRole("textbox", { name: "skills.githubRepoUrl" }),
    { target: { value: "https://github.com/example/old" } },
  );
}
const found = {
  repo_url: "https://github.com/example/old",
  branch: "main",
  skills: [
    { name: "research", path: "research", description: "Research workflow" },
  ],
};

test("GitHub preview failure can retry inside the same form", async () => {
  previewGithub.mockResolvedValueOnce(null).mockResolvedValueOnce(found);
  openGitHub();
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "skills.preview" })),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "skills.previewGitHubFailed",
  );
  await userEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(document.activeElement).not.toBe(document.body);
  expect(document.activeElement?.isConnected).toBe(true);
  expect(
    screen.getByRole("checkbox", { name: "research" }),
  ).toBeInTheDocument();
  expect(previewGithub).toHaveBeenLastCalledWith(
    "https://github.com/example/old",
    "main",
  );
});

test("changing repository while a preview is pending discards the old result", async () => {
  let resolve!: (value: typeof found) => void;
  previewGithub.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  openGitHub();
  fireEvent.click(screen.getByRole("button", { name: "skills.preview" }));
  fireEvent.change(
    screen.getByRole("textbox", { name: "skills.githubRepoUrl" }),
    { target: { value: "https://github.com/example/new" } },
  );
  await act(async () => resolve(found));
  expect(screen.queryByRole("checkbox", { name: "research" })).toBeNull();
  expect(
    screen.getByRole("button", { name: "skills.installSelected" }),
  ).toBeDisabled();
});

test("reopening GitHub import does not inherit a closed preview request", async () => {
  let resolve!: (value: typeof found) => void;
  previewGithub.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  openGitHub();
  fireEvent.click(screen.getByRole("button", { name: "skills.preview" }));
  fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "Open GitHub" }));
  await act(async () => resolve(found));
  expect(screen.queryByRole("checkbox", { name: "research" })).toBeNull();
  expect(
    screen.getByRole("textbox", { name: "skills.githubRepoUrl" }),
  ).toHaveValue("");
});

test("ZIP preview can retry the chosen file without choosing it again", async () => {
  previewZip.mockResolvedValueOnce(null).mockResolvedValueOnce({
    skills: [
      {
        name: "research",
        description: "Research",
        file_count: 1,
        files: ["SKILL.md"],
        already_exists: false,
      },
    ],
  });
  render(
    <MemoryRouter>
      <Imports />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open ZIP" }));
  const file = new File(["sample"], "research.zip", {
    type: "application/zip",
  });
  await act(async () =>
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "skills.previewZipFailed",
  );
  await userEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(document.activeElement).not.toBe(document.body);
  expect(document.activeElement?.isConnected).toBe(true);
  expect(previewZip).toHaveBeenLastCalledWith(file);
  expect(screen.getByRole("checkbox", { name: "research" })).toBeChecked();
});

test("partial GitHub installation leaves unsuccessful skills available to retry", async () => {
  previewGithub.mockResolvedValueOnce({
    ...found,
    skills: [
      ...found.skills,
      { name: "drafting", path: "drafting", description: "Drafting" },
    ],
  });
  installGithub.mockResolvedValueOnce({
    installed: ["research"],
    errors: ["drafting: unavailable"],
  });
  openGitHub();
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "skills.preview" })),
  );
  fireEvent.click(screen.getByRole("button", { name: "common.selectAll" }));
  await act(async () =>
    fireEvent.click(
      screen.getByRole("button", { name: "skills.installSelected" }),
    ),
  );
  expect(screen.getByRole("checkbox", { name: "drafting" })).toBeChecked();
  if (screen.queryByRole("button", { name: "common.deselectAll" }))
    fireEvent.click(screen.getByRole("button", { name: "common.deselectAll" }));
  fireEvent.click(screen.getByRole("button", { name: "common.selectAll" }));
  installGithub.mockResolvedValueOnce({ installed: ["drafting"], errors: [] });
  await userEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(installGithub).toHaveBeenLastCalledWith(
    "https://github.com/example/old",
    ["drafting"],
    "main",
  );
});

test("dropping another ZIP during upload preserves the active file and clears busy when it settles", async () => {
  previewZip.mockResolvedValue({
    skills: [
      {
        name: "research",
        description: "Research",
        file_count: 1,
        files: ["SKILL.md"],
        already_exists: false,
      },
    ],
  });
  let resolve!: (value: null) => void;
  uploadZip.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  render(
    <MemoryRouter>
      <Imports />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open ZIP" }));
  const file = new File(["sample"], "research.zip", {
    type: "application/zip",
  });
  await act(async () =>
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "skills.installSelected" }),
  );
  fireEvent.drop(screen.getByRole("button", { name: "skills.dropZoneTitle" }), {
    dataTransfer: {
      files: [new File(["other"], "other.zip", { type: "application/zip" })],
    },
  });
  expect(previewZip).toHaveBeenCalledTimes(1);
  expect(screen.getByText("research.zip")).toBeInTheDocument();
  await act(async () => resolve(null));
  expect(screen.getByRole("button", { name: "common.cancel" })).toBeEnabled();
  expect(screen.getByRole("alert")).toHaveTextContent("skills.uploadFailed");
});
