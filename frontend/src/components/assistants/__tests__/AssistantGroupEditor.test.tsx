/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Assistant } from "../../../types/assistant";
import { AssistantGroupEditor } from "../AssistantGroupEditor";
const { api, t } = vi.hoisted(() => ({
  t: (key: string) => key,
  api: { list: vi.fn(), create: vi.fn(), update: vi.fn(), get: vi.fn() },
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t }),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
test("group creation selects actual members and coordinator, then opens returned group", async () => {
  api.list.mockResolvedValue({
    assistants: [
      { id: "a", name: "Alice", status: "active" },
      { id: "b", name: "Bob", status: "active" },
    ],
    total: 2,
  });
  api.create.mockResolvedValue({ id: "group" });
  const saved = vi.fn();
  render(<AssistantGroupEditor onClose={() => {}} onSaved={saved} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.groupLeader" }),
  );
  fireEvent.click(screen.getByRole("option", { name: "Alice" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Bob" }));
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.createGroup" }),
  );
  await waitFor(() =>
    expect(api.create).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "group",
        member_ids: ["a", "b"],
        leader_id: "a",
      }),
    ),
  );
  expect(saved).toHaveBeenCalledWith("group");
});

test("failed save preserves selection and draft for retry", async () => {
  api.list.mockResolvedValue({
    assistants: [
      { id: "a", name: "Alice", status: "active" },
      { id: "b", name: "Bob", status: "active" },
    ],
    total: 2,
  });
  api.create.mockRejectedValue(new Error("Save unavailable"));
  const saved = vi.fn();
  render(<AssistantGroupEditor onClose={() => {}} onSaved={saved} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.groupLeader" }),
  );
  fireEvent.click(screen.getByRole("option", { name: "Alice" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Bob" }));
  fireEvent.change(screen.getByPlaceholderText("assistants.groupNameHint"), {
    target: { value: "My group" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.createGroup" }),
  );
  expect(await screen.findByText("Save unavailable")).toBeTruthy();
  expect(
    (
      screen.getByPlaceholderText(
        "assistants.groupNameHint",
      ) as HTMLInputElement
    ).value,
  ).toBe("My group");
  expect(
    screen.getByRole("checkbox", { name: "Bob" }).getAttribute("aria-checked"),
  ).toBe("true");
  expect(saved).not.toHaveBeenCalled();
});

test("switching coordinator preserves purpose and the former coordinator as a member", async () => {
  api.list.mockResolvedValue({
    assistants: [
      { id: "a", name: "Alice", status: "active" },
      { id: "b", name: "Bob", status: "active" },
    ],
    total: 2,
  });
  api.update.mockResolvedValue({ id: "group" });
  render(
    <AssistantGroupEditor
      value={
        {
          id: "group",
          name: "Research",
          instructions: "Compare sources",
          member_ids: ["a", "b"],
          leader_id: "a",
          status: "active",
          revision: 4,
        } as Assistant
      }
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.groupLeader" }),
  );
  fireEvent.click(screen.getByRole("option", { name: "Bob" }));
  expect(screen.getByRole("checkbox", { name: "Alice" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  expect(screen.getByLabelText("assistants.groupPurpose")).toHaveValue(
    "Compare sources",
  );
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() =>
    expect(api.update).toHaveBeenCalledWith(
      "group",
      expect.objectContaining({
        leader_id: "b",
        member_ids: ["b", "a"],
        instructions: "Compare sources",
        revision: 4,
      }),
    ),
  );
});

test("coordinator choices respect paused members and the group member limit", async () => {
  const bots = Array.from({ length: 13 }, (_, i) => ({
    id: String(i),
    name: `Bot ${i}`,
    status: i === 1 ? "paused" : "active",
  }));
  api.list.mockResolvedValue({ assistants: bots, total: bots.length });
  render(
    <AssistantGroupEditor
      value={
        {
          id: "group",
          name: "Research",
          member_ids: bots.slice(0, 12).map((bot) => bot.id),
          leader_id: "0",
        } as Assistant
      }
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.groupLeader" }),
  );
  expect(
    screen.getByRole("option", { name: "Bot 1", exact: true }),
  ).toBeDisabled();
  expect(
    screen.getByRole("option", { name: "Bot 12", exact: true }),
  ).toBeDisabled();
  expect(
    screen.getByRole("option", { name: "Bot 2", exact: true }),
  ).toBeEnabled();
});

test("group details use the shared right editor sidebar", async () => {
  api.list.mockResolvedValue({ assistants: [], total: 0 });
  render(<AssistantGroupEditor onClose={() => {}} onSaved={() => {}} />);
  await waitFor(() => expect(api.list).toHaveBeenCalled());
  expect(
    document.querySelector('[data-right-panel-root][data-panel-kind="editor"]'),
  ).toBeTruthy();
});

test("group profile edits save the introduction and localized suggestions", async () => {
  api.list.mockResolvedValue({
    assistants: [
      { id: "a", name: "Alice", status: "active" },
      { id: "b", name: "Bob", status: "active" },
    ],
    total: 2,
  });
  api.update.mockResolvedValue({ id: "group" });
  render(
    <AssistantGroupEditor
      value={
        {
          id: "group",
          kind: "group",
          name: "Room",
          member_ids: ["a", "b"],
          leader_id: "a",
          revision: 2,
          status: "active",
        } as Assistant
      }
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );
  fireEvent.change(await screen.findByLabelText("personaPresets.description"), {
    target: { value: "Team introduction" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "personaPresets.addStarterPrompt" }),
  );
  fireEvent.change(screen.getByLabelText("personaPresets.starterPrompts 1"), {
    target: { value: '{"zh":"开始研究","en":"Research"}' },
  });
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() =>
    expect(api.update).toHaveBeenCalledWith(
      "group",
      expect.objectContaining({
        description: "Team introduction",
        starter_prompts: [
          { icon: null, text: { zh: "开始研究", en: "Research" } },
        ],
      }),
    ),
  );
});

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => false }),
}));
vi.mock("../../../services/api/model", () => ({
  modelApi: { listAvailable: async () => ({ models: [] }) },
}));

test("group conflict reload restores the latest profile and revision before retry", async () => {
  const group = {
    id: "group",
    kind: "group",
    name: "Room",
    member_ids: ["a", "b"],
    leader_id: "a",
    revision: 2,
    status: "active",
  } as Assistant;
  api.list.mockResolvedValue({
    assistants: [
      { id: "a", name: "Alice", status: "active" },
      { id: "b", name: "Bob", status: "active" },
    ],
    total: 2,
  });
  api.update
    .mockRejectedValueOnce(new Error("Conflict"))
    .mockResolvedValue({ id: "group" });
  api.get.mockResolvedValue({
    ...group,
    revision: 3,
    description: "Latest",
    starter_prompts: [{ text: "New prompt" }],
  });
  render(
    <AssistantGroupEditor
      value={group}
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );
  await screen.findByRole("button", { name: "assistants.groupLeader" });
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await screen.findByText("Conflict");
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.reloadSaved" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("personaPresets.description")).toHaveValue(
      "Latest",
    ),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "common.save" })).toBeEnabled(),
  );
  expect(screen.getByLabelText("personaPresets.starterPrompts 1")).toHaveValue(
    "New prompt",
  );
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() =>
    expect(api.update).toHaveBeenLastCalledWith(
      "group",
      expect.objectContaining({ revision: 3, description: "Latest" }),
    ),
  );
});
