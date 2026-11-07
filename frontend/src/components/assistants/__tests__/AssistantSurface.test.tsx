// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantSurface } from "../AssistantSurface";
vi.mock("../../common/EditorSidebar", () => ({
  EditorSidebar: ({
    onClose,
    children,
    footer,
  }: {
    onClose: () => void;
    children: React.ReactNode;
    footer: React.ReactNode;
  }) => (
    <aside>
      <button onClick={onClose}>close</button>
      {children}
      {footer}
    </aside>
  ),
}));
afterEach(cleanup);
test("assistant details use a sidebar and preserve busy close protection", () => {
  const close = vi.fn();
  const view = render(
    <AssistantSurface
      open
      title="Tasks"
      onClose={close}
      dismissible={false}
      footer="actions"
    >
      content
    </AssistantSurface>,
  );
  expect(view.getByRole("complementary")).toBeTruthy();
  fireEvent.click(view.getByText("close"));
  expect(close).not.toHaveBeenCalled();
  view.rerender(
    <AssistantSurface open title="Tasks" onClose={close}>
      content
    </AssistantSurface>,
  );
  fireEvent.click(view.getByText("close"));
  expect(close).toHaveBeenCalledOnce();
});
test("embedded workspace content stays embedded", () => {
  const view = render(
    <AssistantSurface embedded open title="Tasks" onClose={() => {}}>
      content
    </AssistantSurface>,
  );
  expect(view.queryByRole("complementary")).toBeNull();
  expect(view.getByText("content")).toBeTruthy();
});
