/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ChannelAssistantSelect } from "../ChannelAssistantSelect";
const { list, t } = vi.hoisted(() => ({
  list: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../../services/api/assistant", () => ({
  assistantApi: { list },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t }) }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
test("binding chooses an owned assistant and can explicitly remove the binding", async () => {
  list.mockResolvedValue({
    assistants: [{ id: "helper", name: "Researcher", status: "active" }],
    total: 1,
  });
  const change = vi.fn();
  const { rerender } = render(
    <ChannelAssistantSelect value={null} onChange={change} />,
  );
  const select = screen.getByRole("button", {
    name: "assistants.channelBinding",
  });
  await waitFor(() => expect(select).not.toBeDisabled());
  fireEvent.click(select);
  fireEvent.click(await screen.findByRole("option", { name: "Researcher" }));
  expect(change).toHaveBeenCalledWith("helper");
  rerender(<ChannelAssistantSelect value="helper" onChange={change} />);
  fireEvent.click(select);
  fireEvent.click(
    await screen.findByRole("option", { name: "assistants.noChannelBinding" }),
  );
  expect(change).toHaveBeenLastCalledWith(null);
});
