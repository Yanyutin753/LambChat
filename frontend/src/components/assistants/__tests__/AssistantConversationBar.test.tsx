/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantConversationBar } from "../AssistantConversationBar";
const { api, t, navigate, canReadMemory } = vi.hoisted(() => ({
  api: { forConversation: vi.fn() },
  navigate: vi.fn(),
  canReadMemory: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    hasPermission: (permission: string) =>
      permission === "memory:read" && canReadMemory(),
  }),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t }),
}));
vi.mock("../AssistantEditor", () => ({
  AssistantEditor: () => <div role="dialog">editor</div>,
}));
vi.mock("../AssistantTasksDialog", () => ({
  AssistantTasksDialog: () => <div role="dialog">tasks</div>,
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test("a stable assistant identity exposes task activity and configuration ownership", async () => {
  api.forConversation.mockResolvedValue({
    id: "helper",
    session_id: "chat",
    name: "Researcher",
    status: "active",
  });
  render(<AssistantConversationBar sessionId="chat" />);
  expect(await screen.findByText("Researcher")).toBeInTheDocument();
  expect(screen.queryByText("assistants.configurationHint")).toBeNull();
  fireEvent.keyDown(document, { key: "Tab" });
  fireEvent.focus(screen.getByText("Researcher").closest("[tabindex]")!);
  expect(await screen.findByRole("tooltip")).toHaveTextContent(
    "assistants.configurationHint",
  );
  fireEvent.keyDown(screen.getByText("Researcher").closest("[tabindex]")!, {
    key: "Escape",
  });
  await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "assistants.tasks" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "assistants.edit" })).toBeNull();
});

test("switching conversations immediately removes the previous assistant identity", async () => {
  api.forConversation.mockResolvedValueOnce({
    id: "helper",
    session_id: "old",
    name: "Old identity",
    status: "paused",
  });
  const { rerender } = render(<AssistantConversationBar sessionId="old" />);
  await screen.findByText("Old identity");
  api.forConversation.mockResolvedValueOnce(null);
  rerender(<AssistantConversationBar sessionId="ordinary" />);
  expect(screen.queryByText("Old identity")).toBeNull();
  await waitFor(() =>
    expect(api.forConversation).toHaveBeenLastCalledWith("ordinary"),
  );
});

test("identity load failure is visible and retryable", async () => {
  api.forConversation
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce(null);
  render(<AssistantConversationBar sessionId="chat" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  fireEvent.click(screen.getByRole("button", { name: "common.refresh" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
});

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useLocation: () => ({ pathname: "/chat/thread" }),
}));

test("discussion memory opens the audience bank, not private assistant memory", async () => {
  canReadMemory.mockReturnValue(true);
  api.forConversation.mockResolvedValue({
    id: "helper",
    session_id: "private",
    name: "Researcher",
    status: "active",
  });
  render(<AssistantConversationBar sessionId="group-1" />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.memory" }),
  );
  expect(navigate).toHaveBeenCalledWith(
    "/assistants/helper/memory?discussion=group-1",
  );
});

test("publishes the current identity to the composer and refreshes it after focus", async () => {
  const identity = {
    id: "helper",
    session_id: "chat",
    name: "Helper",
    status: "active",
  };
  const onResolved = vi.fn();
  api.forConversation
    .mockResolvedValueOnce(identity)
    .mockResolvedValueOnce(null);
  render(<AssistantConversationBar sessionId="chat" onResolved={onResolved} />);
  await waitFor(() =>
    expect(onResolved).toHaveBeenCalledWith("chat", identity),
  );
  fireEvent.focus(window);
  await waitFor(() =>
    expect(onResolved).toHaveBeenLastCalledWith("chat", null),
  );
});

test("agent configuration changes refresh the resolved conversation identity", async () => {
  const resolved = vi.fn();
  api.forConversation.mockResolvedValue({
    id: "helper",
    session_id: "chat",
    name: "Before",
    status: "active",
  });
  render(<AssistantConversationBar sessionId="chat" onResolved={resolved} />);
  await screen.findByText("Before");
  api.forConversation.mockResolvedValue({
    id: "helper",
    session_id: "chat",
    name: "After",
    status: "active",
    avatar: "🔎",
  });
  fireEvent(window, new Event("assistants:changed"));
  await screen.findByText("After");
  expect(resolved).toHaveBeenLastCalledWith(
    "chat",
    expect.objectContaining({ name: "After", avatar: "🔎" }),
  );
});
