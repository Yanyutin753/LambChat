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
test("screen indicator acknowledges paint but exposes no takeover controls", async () => {
  invoke.mockResolvedValue("active");
  const { container } = render(<DesktopControl overlay />);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("desktop_control_status", {
      ready: true,
    }),
  );
  expect(screen.queryByRole("button")).toBeNull();
  expect(container.querySelector(".desktop-control-overlay")).not.toBeNull();
  expect(container.querySelector(".desktop-control-overlay")).toHaveTextContent(
    "desktopControl.active",
  );
  expect(invoke).not.toHaveBeenCalledWith(
    "desktop_control_set_paused",
    expect.anything(),
  );
});

test("ended execution cannot be resumed from the control surface", async () => {
  invoke.mockResolvedValue("ended");
  render(<DesktopControl />);
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent(
      "desktopControl.ended",
    ),
  );
  expect(screen.getByRole("button")).toBeDisabled();
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

test("resume stays disabled when the paused state can no longer be confirmed", async () => {
  invoke.mockResolvedValue("paused");
  render(<DesktopControl />);
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "desktopControl.resume" }),
    ).toBeEnabled(),
  );
  invoke.mockRejectedValue(new Error("IPC disconnected"));
  await screen.findByRole("alert");
  expect(
    screen.getByRole("button", { name: "desktopControl.resume" }),
  ).toBeDisabled();
});

test("takeover action describes the current ownership and next step", async () => {
  invoke.mockResolvedValue("active");
  render(<DesktopControl />);
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent(
      "desktopControl.active",
    ),
  );
  expect(
    screen.getByRole("button", { name: "desktopControl.pause" }),
  ).toHaveAccessibleDescription(/desktopControl.active.*desktopControl.hint/);
});
