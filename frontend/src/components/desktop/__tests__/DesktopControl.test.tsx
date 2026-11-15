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
const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    startDragging: vi.fn().mockResolvedValue(undefined),
  }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
import { DesktopControl } from "../DesktopControl";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
test("takeover waits for daemon acknowledgement before enabling resume", async () => {
  let state = "active";
  invoke.mockImplementation(
    async (command: string, args: { paused?: boolean }) => {
      if (command === "desktop_control_status") return state;
      if (args.paused) state = "stopping";
    },
  );
  render(<DesktopControl />);
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent(
      "desktopControl.active",
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "desktopControl.pause" }));
  await waitFor(() => expect(screen.getByRole("button")).toBeDisabled());
  expect(invoke).toHaveBeenCalledWith("desktop_control_set_paused", {
    paused: true,
  });
  await act(async () => {
    state = "paused";
  });
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "desktopControl.resume" }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "desktopControl.resume" }),
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("desktop_control_set_paused", {
      paused: false,
    }),
  );
});
test("disconnected daemon cannot be resumed", async () => {
  invoke.mockResolvedValue("disconnected");
  render(<DesktopControl />);
  await waitFor(() => expect(screen.getByRole("button")).toBeDisabled());
  expect(screen.getByRole("status")).toHaveTextContent(
    "desktopControl.disconnected",
  );
});
