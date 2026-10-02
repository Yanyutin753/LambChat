/** @vitest-environment jsdom */
import { useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { resetRightPanelCoordinator } from "../../common/rightPanelCoordinator";
import { EditorSidebar } from "../../common/EditorSidebar";
import { PersonaEditorModal } from "../PersonaEditorModal";
import { SkillSelector } from "../PersonaEditorSkillSelector";
import { PersonaEditorBindingSelector } from "../PersonaEditorBindingSelector";
import type { PersonaPreset } from "../../../types";

const api = vi.hoisted(() => ({ skills: vi.fn(), mcp: vi.fn() }));
vi.mock("../../../services/api/skill", () => ({
  skillApi: { list: api.skills },
}));
vi.mock("../../../services/api/mcp", () => ({ mcpApi: { list: api.mcp } }));
beforeEach(() => {
  resetRightPanelCoordinator();
  api.skills.mockReset().mockResolvedValue({
    skills: [
      {
        skill_name: "research",
        description: "Research",
        installed_from: "manual",
        enabled: true,
        tags: [],
        file_count: 1,
      },
    ],
    total: 1,
  });
  api.mcp
    .mockReset()
    .mockResolvedValue({ servers: [{ name: "context", enabled: true }] });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const preset: PersonaPreset = {
  id: "research",
  name: "Research",
  description: "Research assistant",
  avatar: "",
  scope: "global",
  status: "published",
  visibility: "public",
  version: 1,
  usage_count: 0,
  tags: ["research"],
  system_prompt: "Keep the original instructions",
  skill_names: ["research"],
  mcp_server_names: ["context"],
  starter_prompts: [{ icon: "", text: "Summarize the project" }],
  created_at: "2026-10-01",
  updated_at: "2026-10-01",
};
const props = {
  showModal: true,
  editorScope: "global" as const,
  canAdmin: true,
  isMutating: false,
  createPreset: vi.fn(),
  updatePreset: vi.fn().mockResolvedValue(null),
  onClose: vi.fn(),
};

test("persona fields and scope controls have names and explain official visibility", async () => {
  render(<PersonaEditorModal {...props} editingPreset={preset} />);
  expect(
    screen.getByRole("textbox", { name: i18n.t("personaPresets.name") }),
  ).toHaveValue("Research");
  expect(
    screen.getByRole("textbox", { name: i18n.t("personaPresets.description") }),
  ).toHaveValue("Research assistant");
  expect(
    screen.getByRole("textbox", {
      name: i18n.t("personaPresets.systemPrompt"),
    }),
  ).toHaveValue(preset.system_prompt);
  expect(
    screen.getByRole("textbox", { name: i18n.t("personaPresets.tagsInput") }),
  ).toHaveValue("research");
  expect(
    screen.getByRole("button", { name: i18n.t("personaPresets.scope") }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: i18n.t("personaPresets.status") }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(i18n.t("personaPresets.officialHint")),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("textbox", {
      name: `${i18n.t("personaPresets.starterIcon")} 1`,
    }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("textbox", {
      name: `${i18n.t("personaPresets.starterPrompts")} 1`,
    }),
  ).toHaveValue("Summarize the project");
});

test("failed binding catalog can retry without declaring bindings missing or resetting the draft", async () => {
  api.mcp.mockRejectedValueOnce(new Error("Network unavailable"));
  render(<PersonaEditorModal {...props} editingPreset={preset} />);
  fireEvent.change(
    screen.getByPlaceholderText(i18n.t("personaPresets.namePlaceholder")),
    { target: { value: "Edited research" } },
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
  expect(
    screen.queryByText(
      i18n.t("personaPresets.missingSkillsHint", { names: "research" }),
    ),
  ).toBeNull();
  expect(
    screen.queryByText(
      i18n.t("personaPresets.missingMcpHint", { names: "context" }),
    ),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(
    screen.getByPlaceholderText(i18n.t("personaPresets.namePlaceholder")),
  ).toHaveValue("Edited research");
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  await waitFor(() =>
    expect(props.updatePreset).toHaveBeenCalledWith(
      preset.id,
      expect.objectContaining({
        name: "Edited research",
        skill_names: ["research"],
        mcp_server_names: ["context"],
      }),
    ),
  );
});

test("binding availability includes declared skills beyond the first catalog page", async () => {
  api.skills
    .mockResolvedValueOnce({ skills: [{ skill_name: "other" }], total: 2 })
    .mockResolvedValueOnce({ skills: [{ skill_name: "research" }], total: 2 });
  render(<PersonaEditorModal {...props} editingPreset={preset} />);
  await waitFor(() => expect(api.skills).toHaveBeenCalledTimes(2));
  expect(
    screen.queryByText(
      i18n.t("personaPresets.missingSkillsHint", { names: "research" }),
    ),
  ).toBeNull();
});

test("MCP binding picker stays unavailable until its catalog has loaded", async () => {
  let resolve!: (value: unknown) => void;
  api.mcp.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  render(<PersonaEditorModal {...props} editingPreset={preset} />);
  const trigger = screen.getByRole("button", {
    name: i18n.t("personaPresets.mcpServerCount", { count: 1 }),
  });
  expect(trigger).toBeDisabled();
  fireEvent.click(trigger);
  expect(screen.queryByRole("combobox")).toBeNull();
  await act(async () =>
    resolve({ servers: [{ name: "context", enabled: true }] }),
  );
  expect(trigger).toBeEnabled();
});

function PickerHarness({
  binding = false,
  close,
}: {
  binding?: boolean;
  close: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(["research"]);
  return (
    <EditorSidebar open title="Editor" onClose={close}>
      <input aria-label="Draft" defaultValue="Keep this draft" />
      {binding ? (
        <PersonaEditorBindingSelector
          options={[{ name: "context" }]}
          selected={selected}
          onChange={setSelected}
          open={open}
          onOpenChange={setOpen}
          icon={null}
          countLabelKey="personaPresets.mcpServerCount"
          placeholderKey="personaPresets.mcpServersInputPlaceholder"
          searchPlaceholderKey="personaPresets.mcpSearchPlaceholder"
          emptyKey="personaPresets.noMcpServers"
        />
      ) : (
        <SkillSelector
          skillNames={selected}
          onSkillNamesChange={setSelected}
          open={open}
          onOpenChange={setOpen}
        />
      )}
    </EditorSidebar>
  );
}

test.each([false, true])(
  "Escape closes only the capability picker and restores its trigger (MCP=%s)",
  async (binding) => {
    const close = vi.fn();
    render(<PickerHarness binding={binding} close={close} />);
    const trigger = screen.getByRole("button", {
      name: i18n.t(
        binding ? "personaPresets.mcpServerCount" : "personaPresets.skillCount",
        { count: 1 },
      ),
    });
    fireEvent.click(trigger);
    const search = screen.getByRole("combobox");
    fireEvent.keyDown(search, { key: "Escape", isComposing: true });
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox")).toBe(search);
    fireEvent.keyDown(search, { key: "Escape" });
    expect(close).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
    expect(screen.getByRole("textbox", { name: "Draft" })).toHaveValue(
      "Keep this draft",
    );
  },
);

test("Tab and Enter activate the focused skill rather than a stale hover index", async () => {
  const user = userEvent.setup();
  render(<PickerHarness close={vi.fn()} />);
  await user.click(
    screen.getByRole("button", {
      name: i18n.t("personaPresets.skillCount", { count: 1 }),
    }),
  );
  const option = await screen.findByRole("option", {
    name: "research Research",
  });
  option.focus();
  await user.keyboard("{Enter}");
  expect(option).toHaveAttribute("aria-selected", "false");
});

test("touch users can close the capability popup without dismissing their draft", async () => {
  const close = vi.fn();
  render(<PickerHarness close={close} />);
  const trigger = screen.getByRole("button", {
    name: i18n.t("personaPresets.skillCount", { count: 1 }),
  });
  fireEvent.click(trigger);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.close"), exact: true }),
  );
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(close).not.toHaveBeenCalled();
  expect(trigger).toHaveFocus();
});

test.each([false, true])(
  "selected capabilities can be removed with a named keyboard button (MCP=%s)",
  async (binding) => {
    const user = userEvent.setup();
    render(<PickerHarness binding={binding} close={vi.fn()} />);
    const remove = screen.getByRole("button", {
      name: `${i18n.t("common.remove")} research`,
    });
    await act(async () => {});
    remove.focus();
    await user.keyboard(" ");
    expect(
      screen.queryByRole("button", {
        name: `${i18n.t("common.remove")} research`,
      }),
    ).toBeNull();
  },
);

test("a pending skill catalog shows loading instead of no matches", async () => {
  let resolve!: (value: unknown) => void;
  api.skills.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  render(<PickerHarness close={vi.fn()} />);
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("personaPresets.skillCount", { count: 1 }),
    }),
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    i18n.t("common.loading"),
  );
  expect(screen.queryByText(i18n.t("skills.noMatchingSkills"))).toBeNull();
  await act(async () => resolve({ skills: [], total: 0 }));
});

test("a picker uses the visible viewport when neither side of its trigger fits the keyboard", async () => {
  vi.stubGlobal("visualViewport", {
    height: 260,
    width: 320,
    offsetTop: 0,
    offsetLeft: 0,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    new DOMRect(12, 120, 296, 44),
  );
  render(<PickerHarness close={vi.fn()} />);
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("personaPresets.skillCount", { count: 1 }),
    }),
  );
  const popup = screen
    .getByRole("combobox")
    .closest(".ppe-skill-dropdown") as HTMLElement;
  expect(Number.parseFloat(popup.style.maxHeight)).toBeGreaterThanOrEqual(200);
  expect(Number.parseFloat(popup.style.top)).toBeGreaterThanOrEqual(12);
  expect(
    Number.parseFloat(popup.style.top) +
      Number.parseFloat(popup.style.maxHeight),
  ).toBeLessThanOrEqual(248);
});

test("skill catalog failure keeps selected names and retries the same list", async () => {
  api.skills.mockRejectedValueOnce(new Error("Network unavailable"));
  render(<PickerHarness close={vi.fn()} />);
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("personaPresets.skillCount", { count: 1 }),
    }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
  expect(screen.queryByText(i18n.t("skills.noMatchingSkills"))).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  expect(
    await screen.findByRole("option", { name: "research Research" }),
  ).toHaveAttribute("aria-selected", "true");
  expect(api.skills.mock.calls[1][0]).toEqual(api.skills.mock.calls[0][0]);
});
