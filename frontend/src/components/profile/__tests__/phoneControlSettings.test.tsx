/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
const native = vi.hoisted(() => ({
  phoneState: vi.fn(),
  phonePair: vi.fn(),
  phoneConnect: vi.fn(),
  phoneAction: vi.fn(),
  phoneDiscover: vi.fn(),
}));
vi.mock("../../../services/capacitor/localDevice", () => ({
  LocalDevice: native,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
import { PhoneControlSettings } from "../PhoneControlSettings";
beforeEach(() => {
  vi.clearAllMocks();
  native.phoneState.mockResolvedValue({
    connected: false,
    paused: true,
    accessibility: false,
    backgroundSupported: true,
    display: 0,
  });
});
test("requires accessibility and a valid connection port", async () => {
  render(<PhoneControlSettings />);
  await screen.findByText(/profile.localSandbox.phoneNeedsAccessibility/);
  fireEvent.change(
    screen.getByLabelText("profile.localSandbox.phoneConnectPort"),
    { target: { value: "5555" } },
  );
  expect(
    screen.getByRole("button", { name: "profile.localSandbox.phoneConnect" }),
  ).toBeDisabled();
  expect(native.phoneConnect).not.toHaveBeenCalled();
});
test("uses discovered ports without pairing or connecting automatically", async () => {
  native.phoneDiscover.mockResolvedValue({
    pairing: [12345],
    connect: [54321],
  });
  render(<PhoneControlSettings />);
  fireEvent.click(screen.getByText("profile.localSandbox.phoneDiscover"));
  await waitFor(() =>
    expect(
      screen.getByLabelText("profile.localSandbox.phoneConnectPort"),
    ).toHaveValue("54321"),
  );
  expect(
    screen.getByLabelText("profile.localSandbox.phonePairPort"),
  ).toHaveValue("12345");
  expect(native.phoneConnect).not.toHaveBeenCalled();
  expect(native.phonePair).not.toHaveBeenCalled();
});

test("returning from system settings rechecks the permission and connection", async () => {
  render(<PhoneControlSettings />);
  await screen.findByText(/profile.localSandbox.phoneNeedsAccessibility/);
  native.phoneState.mockResolvedValue({
    connected: true,
    accessibility: true,
    paused: false,
  });
  fireEvent.focus(window);
  expect(
    await screen.findByText("profile.localSandbox.phoneConnected"),
  ).toBeTruthy();
  expect(
    screen.queryByText(/profile.localSandbox.phoneNeedsAccessibility/),
  ).toBeNull();
});

test("a failed initial status query leaves settings available and ends loading", async () => {
  native.phoneState.mockRejectedValue(new Error("unavailable"));
  render(<PhoneControlSettings />);
  await screen.findByRole("alert");
  expect(screen.queryAllByText("common.loading")).toHaveLength(0);
  expect(screen.getByRole("button", { name: "common.refresh" })).toBeEnabled();
});
