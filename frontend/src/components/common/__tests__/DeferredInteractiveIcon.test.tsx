/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Plus } from "lucide-react";
import { DeferredInteractiveIcon } from "../DeferredInteractiveIcon";

const loading = vi.hoisted(() => ({
  reject: undefined as ((reason: Error) => void) | undefined,
}));

vi.mock(
  "../InteractiveIcon",
  () =>
    new Promise((_, reject) => {
      loading.reject = reject;
    }),
);

afterEach(cleanup);

test("the original icon and action remain available while animation loads and after an offline failure", async () => {
  const click = vi.fn();
  render(
    <button onClick={click} aria-label="Add">
      <DeferredInteractiveIcon>
        <Plus size={16} />
      </DeferredInteractiveIcon>
    </button>,
  );
  const button = screen.getByRole("button", { name: "Add" });
  expect(button.querySelector("svg")?.getAttribute("width")).toBe("16");
  fireEvent.click(button);
  expect(click).toHaveBeenCalledOnce();

  await waitFor(() => expect(loading.reject).toBeTypeOf("function"));
  await act(async () => loading.reject!(new Error("offline")));

  expect(button.querySelector("svg.lucide-plus")).not.toBeNull();
  fireEvent.click(button);
  expect(click).toHaveBeenCalledTimes(2);
});
