/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MCPServerCard } from "../../mcp/MCPServerCard";
import { SkillCard } from "../../skill/SkillCard";
import { PersonaPresetCard } from "../../persona/PersonaPresetCard";
import type { PersonaPreset } from "../../../types";
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("MCP more actions respect edit permission and internal servers", () => {
  const edit = vi.fn();
  const server = {
    name: "Research",
    transport: "sse",
    enabled: true,
    is_system: false,
    can_edit: true,
    allowed_roles: [],
    role_quotas: {},
  };
  const { container, rerender } = render(
    <MCPServerCard
      server={server}
      onToggle={vi.fn()}
      onEdit={edit}
      onDelete={vi.fn()}
    />,
  );
  fireEvent.contextMenu(container.querySelector(".scb")!);
  fireEvent.click(screen.getByRole("menuitem", { name: "mcp.card.edit" }));
  expect(edit).toHaveBeenCalledWith(server);
  rerender(
    <MCPServerCard
      server={{ ...server, is_internal: true }}
      onToggle={vi.fn()}
      onEdit={edit}
      onDelete={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "common.moreOptions" }));
  expect(screen.queryByRole("menuitem", { name: "mcp.card.edit" })).toBeNull();
  expect(
    screen.queryByRole("menuitem", { name: "mcp.card.delete" }),
  ).toBeNull();
  expect(
    screen.getByRole("menuitem", { name: "mcp.card.disable" }),
  ).toBeTruthy();
});
test("skill export remains available in the more menu", () => {
  const exportZip = vi.fn();
  const skill = {
    name: "Research",
    tags: [],
    description: "Notes",
    enabled: true,
    source: "manual",
    files: {},
    file_count: 1,
    installed_from: "manual",
    is_published: false,
    marketplace_is_active: true,
  };
  render(
    <SkillCard
      skill={skill}
      onToggle={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onExportZip={exportZip}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "common.moreOptions" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "skills.exportZip" }));
  expect(exportZip).toHaveBeenCalledWith("Research");
});
test("persona right click offers only permitted secondary actions", () => {
  const preset = {
    id: "role-1",
    name: "Research",
    scope: "global",
    status: "published",
    tags: [],
    skill_names: [],
    usage_count: 0,
  } as unknown as PersonaPreset;
  const copy = vi.fn();
  const { container } = render(
    <PersonaPresetCard
      preset={preset}
      selected={false}
      activeTag={null}
      canWrite
      canAdmin={false}
      onUse={vi.fn()}
      onClear={vi.fn()}
      onCopy={copy}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleTag={vi.fn()}
    />,
  );
  fireEvent.contextMenu(container.querySelector(".scb")!);
  expect(
    screen.queryByRole("menuitem", { name: "personaPresets.edit" }),
  ).toBeNull();
  expect(screen.queryByRole("menuitem", { name: "common.delete" })).toBeNull();
  fireEvent.click(
    screen.getByRole("menuitem", { name: "personaPresets.copy" }),
  );
  expect(copy).toHaveBeenCalledWith(preset);
});
