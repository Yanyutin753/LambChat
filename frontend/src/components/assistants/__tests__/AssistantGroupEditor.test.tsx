/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantGroupEditor } from "../AssistantGroupEditor";
const { api, t } = vi.hoisted(() => ({
  t: (key: string) => key,
  api: { list: vi.fn(), create: vi.fn(), update: vi.fn() },
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t }) }));
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
  fireEvent.click(await screen.findByRole("radio", { name: "Alice" }));
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
  fireEvent.click(await screen.findByRole("radio", { name: "Alice" }));
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
