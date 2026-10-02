/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MarketplacePanel } from "../../MarketplacePanel";
import { useMarketplace } from "../../../../hooks/useMarketplace";
import { useSkills } from "../../../../hooks/useSkills";

vi.mock("../../../../hooks/useMarketplace", () => ({
  useMarketplace: vi.fn(),
}));
vi.mock("../../../../hooks/useSkills", () => ({ useSkills: vi.fn() }));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "owner" }, hasAnyPermission: () => true }),
}));
vi.mock("../../../../hooks/useAppThemeMode", () => ({
  useAppThemeMode: () => "light",
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../SkillCard", () => ({
  SkillCard: ({ onEdit }: { onEdit: (name: string) => void }) => (
    <button onClick={() => onEdit("research")}>Edit published skill</button>
  ),
}));

const reference = '{"type":"binary","storage_key":"image"}';
const skill = {
  name: "research",
  description: "Published instructions",
  tags: [],
  enabled: true,
  files: {
    "SKILL.md": "# Published",
    "notes.md": "Keep notes",
    "assets/image.png": reference,
  },
  binaryFiles: {
    "assets/image.png": {
      url: "/image.png",
      mime_type: "image/png",
      size: 100,
    },
  },
};
const load = vi.fn();
const getLocal = vi.fn();
const update = vi.fn();
beforeEach(() => {
  load.mockResolvedValue(skill);
  getLocal.mockResolvedValue(skill);
  update.mockResolvedValue(true);
  vi.mocked(useMarketplace).mockReturnValue({
    filteredSkills: [{ skill_name: "research", tags: [], created_by: "owner" }],
    tags: [],
    selectedTags: [],
    searchQuery: "",
    activeFilter: "all",
    isLoading: false,
    fetchSkills: vi.fn(),
    loadMarketplaceSkillForEdit: load,
    updateMarketplaceSkill: update,
  } as unknown as ReturnType<typeof useMarketplace>);
  vi.mocked(useSkills).mockReturnValue({
    skills: [],
    fetchSkills: vi.fn(),
    isLoading: false,
    getSkill: getLocal,
  } as unknown as ReturnType<typeof useSkills>);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
async function open() {
  render(
    <MemoryRouter>
      <MarketplacePanel />
    </MemoryRouter>,
  );
  await act(async () =>
    fireEvent.click(
      screen.getByRole("button", { name: "Edit published skill" }),
    ),
  );
}
test("marketplace edit reads published files instead of a possibly different local copy", async () => {
  await open();
  expect(load).toHaveBeenCalledWith("research");
  expect(getLocal).not.toHaveBeenCalled();
});
test("text-only marketplace save retains binary references and unrelated files", async () => {
  await open();
  expect(
    screen.queryByRole("button", { name: "skills.form.addBinaryFile" }),
  ).toBeNull();
  fireEvent.change(
    screen.getByRole("textbox", { name: "skills.form.description" }),
    { target: { value: "Updated description" } },
  );
  await act(async () =>
    fireEvent.click(
      screen.getByRole("button", { name: "skills.form.saveChanges" }),
    ),
  );
  expect(update.mock.calls[0][1].files["assets/image.png"]).toBe(reference);
  expect(update.mock.calls[0][1].files["notes.md"]).toBe("Keep notes");
  expect(
    screen.queryByRole("textbox", { name: "skills.form.description" }),
  ).toBeNull();
});
