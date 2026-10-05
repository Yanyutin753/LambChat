/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ChannelModelSelect } from "../ChannelModelSelect";
import { ChannelAgentSelect } from "../ChannelAgentSelect";
import i18n from "../../../../i18n";

vi.mock("../../../../services/api/model", () => ({ modelApi: { listAvailable: async () => ({ models: [{ id: "model", label: "Chosen model", value: "model" }] }) } }));
vi.mock("../../../../services/api/agent", () => ({ agentApi: { list: async () => ({ agents: [{ id: "agent", name: "Chosen agent", description: "Agent description" }] }) } }));
vi.mock("../../../common/GlassSelect", () => ({ GlassSelect: ({ value, onChange, options, disabled }: { value: string; onChange: (value: string) => void; options: { value: string; label: React.ReactNode }[]; disabled: boolean }) =>
  <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option.value} value={option.value}>{typeof option.label === "string" ? option.label : option.value}</option>)}</select>,
}));
afterEach(cleanup);

test.each(["model", "agent"] as const)("%s selection can be reset to its inherited default", async (kind) => {
  const onChange = vi.fn();
  render(kind === "model" ? <ChannelModelSelect value="model" onChange={onChange} /> : <ChannelAgentSelect value="agent" onChange={onChange} />);
  await screen.findByRole("option", { name: i18n.t(kind === "model" ? "channel.defaultModel" : "channel.defaultAgent") });
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "" } });
  expect(onChange).toHaveBeenCalledWith(null);
});
