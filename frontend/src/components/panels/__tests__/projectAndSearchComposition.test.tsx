/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { NewProjectModal } from "../NewProjectModal";
import { SearchDialog } from "../SearchDialog";

vi.mock("react-intersection-observer", () => ({
  useInView: () => ({ ref: vi.fn(), inView: false }),
}));
vi.mock("../../../services/api", () => ({
  sessionApi: {
    list: vi.fn().mockResolvedValue({
      sessions: [{ id: "one", name: "Research", metadata: {} }],
      has_more: false,
    }),
  },
}));

test.each([{ isComposing: true }, { keyCode: 229 }])(
  "confirming project name composition does not create a project (%j)",
  (composition) => {
    const create = vi.fn();
    const close = vi.fn();
    render(
      <NewProjectModal
        icon=""
        name="Research"
        onIconChange={vi.fn()}
        onNameChange={vi.fn()}
        onCreate={create}
        onClose={close}
      />,
    );
    const name = screen.getByDisplayValue("Research");
    fireEvent.keyDown(name, { key: "Enter", ...composition });
    fireEvent.keyDown(name, { key: "Escape", ...composition });
    expect(create).not.toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();
    fireEvent.keyDown(name, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
  },
);

test("legacy IME confirmation keeps search open without navigating to a session", async () => {
  const select = vi.fn();
  render(<SearchDialog isOpen onClose={vi.fn()} onSelectSession={select} />);
  const result = await screen.findByRole("button", { name: /Research/ });
  result.scrollIntoView = vi.fn();
  const input = screen.getByRole("textbox");
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  expect(select).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(select).toHaveBeenCalledWith("one");
});
