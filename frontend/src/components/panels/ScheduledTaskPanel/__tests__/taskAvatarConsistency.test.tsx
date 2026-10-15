/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ScheduledTaskPanel } from "..";
import { AgentIcon } from "../../../agent/AgentIcon";

vi.mock("../../../../hooks/useAuth", () => ({ useAuth: () => ({ hasPermission: () => true }) }));
vi.mock("../../../../contexts/SettingsContext", () => ({ useSettingsContext: () => ({ availableModels: [] }) }));
vi.mock("../../../../services/api/personaPreset", () => ({ personaPresetApi: { list: vi.fn().mockResolvedValue({ presets: [{ id: "role-42", name: "Role", avatar: "generated:role-art" }] }) } }));
vi.mock("../../../../services/api/team", () => ({ teamApi: { list: vi.fn().mockResolvedValue({ teams: [{ id: "team-42", name: "Team", avatar: "generated:team-art", members: [] }] }) } }));
vi.mock("../../../../services/api/scheduledTask", () => ({ scheduledTaskApi: { list: vi.fn().mockResolvedValue({
  items: [
    { id: "one", name: "First task", agent_id: "fast", input_payload: {} },
    { id: "two", name: "Second task", agent_id: "fast", input_payload: {} },
    { id: "role", name: "Role task", agent_id: "fast", input_payload: { persona_preset_id: "role-42" } },
    { id: "team", name: "Team task", agent_id: "team", input_payload: { team_id: "team-42" } },
    { id: "missing", name: "Missing agent task", agent_id: "removed", input_payload: {} },
  ].map(task => ({ ...task, trigger_type: "interval", trigger_config: { seconds: 60 }, status: "paused", total_runs: 0 })), total: 5,
}) } }));
afterEach(cleanup);

function artwork(element: Element) {
  return Array.from(element.querySelectorAll("svg path, svg rect, svg circle"))
    .map(shape => [shape.tagName, shape.getAttribute("d"), shape.getAttribute("fill"), shape.getAttribute("transform")]);
}

test("task headers and agent badges use the configured identity, independent of task title", async () => {
  render(<MemoryRouter><ScheduledTaskPanel agents={[
    { id: "fast", name: "Fast", description: "", icon: "generated:fast-art" },
    { id: "team", name: "Team agent", description: "", icon: "generated:team-agent" },
  ]} /></MemoryRouter>);
  for (const [title, icon, seed] of [
    ["First task", "generated:fast-art", "fast"],
    ["Second task", "generated:fast-art", "fast"],
    ["Role task", "generated:role-art", "role-42"],
    ["Team task", "generated:team-art", "Team"],
    ["Missing agent task", undefined, "removed"],
  ] as const) {
    const card = await screen.findByRole("group", { name: title });
    const expected = render(<AgentIcon icon={icon} seed={seed} />);
    expect(artwork(card.querySelector(".scb__header")!)).toEqual(artwork(expected.container));
    if (title === "First task" || title === "Second task") {
      const badge = within(card).getByText("Fast Agent").closest(".skill-meta-pill")!;
      expect(artwork(badge)).toEqual(artwork(expected.container));
    }
    expected.unmount();
  }
});
