/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
const native = vi.hoisted(() => ({
  overlayStatus: vi.fn(),
  setOverlayEnabled: vi.fn(),
}));
vi.mock("../../../services/capacitor/localDevice", () => ({
  LocalDevice: native,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
import { LocalDeviceOverlaySettings } from "../LocalDeviceOverlaySettings";
beforeEach(() => {
  vi.clearAllMocks();
  native.overlayStatus.mockResolvedValue({ enabled: false, granted: false });
});
test("uses the permission result instead of optimistically enabling the overlay", async () => {
  native.setOverlayEnabled.mockResolvedValue({
    enabled: false,
    granted: false,
  });
  render(<LocalDeviceOverlaySettings />);
  const toggle = await screen.findByRole("checkbox");
  await waitFor(() => expect(toggle).not.toBeDisabled());
  fireEvent.click(toggle);
  await waitFor(() =>
    expect(native.setOverlayEnabled).toHaveBeenCalledWith({ enabled: true }),
  );
  expect(toggle).not.toBeChecked();
});
test("shows a retry after a failed status read", async () => {
  native.overlayStatus.mockRejectedValueOnce(new Error("unavailable"));
  render(<LocalDeviceOverlaySettings />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByText("common.retry"));
  await waitFor(() => expect(screen.getByRole("checkbox")).not.toBeDisabled());
});
