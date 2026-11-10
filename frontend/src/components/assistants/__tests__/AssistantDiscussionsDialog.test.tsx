/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantDiscussionsDialog } from "../AssistantDiscussionsDialog";
import type { Assistant } from "../../../types/assistant";
const { api, navigate, t } = vi.hoisted(() => ({
  api: { discussions: vi.fn() },
  navigate: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t }) }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const assistant = { id: "helper", name: "Researcher" } as Assistant;

test("discussion memory uses the selected audience and revoked binding is visible", async () => {
  api.discussions.mockResolvedValue({
    total: 2,
    discussions: [
      {
        session_id: "group",
        channel_type: "feishu",
        chat_id: "Research",
        available: true,
      },
      {
        session_id: "revoked",
        channel_type: "feishu",
        chat_id: "Old room",
        available: false,
      },
    ],
  });
  render(
    <AssistantDiscussionsDialog assistant={assistant} onClose={() => {}} />,
  );
  await screen.findByText("Research");
  const buttons = screen.getAllByRole("button", { name: "assistants.memory" });
  expect(buttons[1]).toBeDisabled();
  fireEvent.click(buttons[0]);
  expect(navigate).toHaveBeenCalledWith(
    "/assistants/helper/memory?discussion=group",
  );
  expect(
    screen.getByText("assistants.discussionUnavailable"),
  ).toBeInTheDocument();
});

test("failed discussion loading can be retried", async () => {
  api.discussions
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ total: 0, discussions: [] });
  render(
    <AssistantDiscussionsDialog assistant={assistant} onClose={() => {}} />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  fireEvent.click(screen.getByRole("button", { name: "common.refresh" }));
  expect(
    await screen.findByText("assistants.noDiscussions"),
  ).toBeInTheDocument();
});

test("discussion pagination retains its total between pages", async () => {
  api.discussions.mockImplementation((_id, skip) =>
    Promise.resolve({
      total: 11,
      discussions: [
        {
          session_id: "group",
          channel_type: "feishu",
          chat_id: skip ? "Second page" : "First page",
          available: true,
        },
      ],
    }),
  );
  render(
    <AssistantDiscussionsDialog assistant={assistant} onClose={() => {}} />,
  );
  await screen.findByText("First page");
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  expect(await screen.findByText("Second page")).toBeVisible();
  expect(api.discussions).toHaveBeenLastCalledWith("helper", 10, 10);
});

test("an empty channel inbox offers a route back to the assistant conversation", async () => {
  api.discussions.mockResolvedValue({ total: 0, discussions: [] });
  render(
    <AssistantDiscussionsDialog
      assistant={assistant}
      embedded
      onClose={() => {}}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.openConversation" }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/helper");
});
