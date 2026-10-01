/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import toast from "react-hot-toast";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppToaster } from "../AppToaster";
import { ModalSurface } from "../../../common/ModalSurface";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  toast.remove();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});
beforeEach(() => vi.stubGlobal("matchMedia", () => ({ matches: true })));

test("copy feedback stays accessible outside the locked application background", async () => {
  const root = document.createElement("div");
  root.id = "root";
  root.setAttribute("inert", "");
  document.body.append(root);
  const view = render(<AppToaster />, { container: root });
  act(() => {
    toast.error("Copy failed. Please try again.");
  });
  const feedback = await screen.findByText("Copy failed. Please try again.");
  expect(feedback.closest("[inert]")).toBeNull();
  expect(feedback).toHaveAttribute("aria-live", "polite");
  const dismiss = screen.getByRole("button", { name: "common.dismiss" });
  fireEvent.click(dismiss);
  await waitFor(
    () =>
      expect(screen.queryByText("Copy failed. Please try again.")).toBeNull(),
    { timeout: 1500 },
  );
  view.unmount();
  root.remove();
});

test("pointer dismissal keeps focus on the current operation", async () => {
  render(
    <>
      <button>Copy result</button>
      <AppToaster />
    </>,
  );
  const copy = screen.getByRole("button", { name: "Copy result" });
  copy.focus();
  act(() => {
    toast.error("Copy failed");
  });
  const dismiss = await screen.findByRole("button", { name: "common.dismiss" });
  // jsdom does not perform the browser's default mousedown focus action.
  if (fireEvent.mouseDown(dismiss)) dismiss.focus();
  fireEvent.click(dismiss);
  expect(copy).toHaveFocus();
});

test("keyboard dismissal returns focus to the currently open modal", async () => {
  render(
    <>
      <AppToaster />
      <ModalSurface open onClose={() => {}} label="Tool result">
        <button>Copy result</button>
      </ModalSurface>
    </>,
  );
  act(() => {
    toast.error("Copy failed");
  });
  const dismiss = await screen.findByRole("button", { name: "common.dismiss" });
  dismiss.focus();
  fireEvent.click(dismiss);
  await waitFor(() => expect(screen.queryByText("Copy failed")).toBeNull(), {
    timeout: 1500,
  });
  expect(screen.getByRole("dialog", { name: "Tool result" })).toHaveFocus();
});
