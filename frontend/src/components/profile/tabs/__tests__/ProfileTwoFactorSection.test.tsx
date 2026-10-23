/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ProfileTwoFactorSection } from "../ProfileTwoFactorSection";

const { setup, update, refresh, qr, user } = vi.hoisted(() => ({
  setup: vi.fn(),
  update: vi.fn(),
  refresh: vi.fn(),
  qr: vi.fn(),
  user: { id: "owner", two_factor_enabled: false },
}));
vi.mock("../../../../services/api", () => ({
  authApi: { setupTwoFactor: setup, updateTwoFactor: update },
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user, refreshUser: refresh }),
}));
vi.mock("qrcode", () => ({ default: { toDataURL: qr } }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  user.two_factor_enabled = false;
});

test("pairing stays pending until confirmation, then displays recovery codes once", async () => {
  setup.mockResolvedValue({
    secret: "PAIRINGKEY",
    otpauth_uri: "otpauth://local",
  });
  qr.mockResolvedValue("data:image/png;base64,qr");
  update.mockResolvedValue({ recovery_codes: ["saved-offline-code"] });
  render(<ProfileTwoFactorSection />);
  fireEvent.click(screen.getByRole("button", { name: "twoFactor.pair" }));
  fireEvent.change(screen.getByLabelText("auth.password"), {
    target: { value: "password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "twoFactor.pair" }));
  await screen.findByText("PAIRINGKEY");
  expect(update).not.toHaveBeenCalled();
  expect(qr).toHaveBeenCalledWith("otpauth://local", { width: 240, margin: 2 });
  fireEvent.change(screen.getByLabelText("twoFactor.code"), {
    target: { value: "123456" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "twoFactor.confirmEnable" }),
  );
  await screen.findByText("saved-offline-code");
  expect(update).toHaveBeenCalledWith("enable", "password", "123456");
  expect(screen.queryByText("PAIRINGKEY")).toBeNull();
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "twoFactor.savedCodes" }));
  expect(screen.queryByText("saved-offline-code")).toBeNull();
});

test("disabling requires password and a second factor and does not run on cancel", () => {
  user.two_factor_enabled = true;
  render(<ProfileTwoFactorSection />);
  fireEvent.click(screen.getByRole("button", { name: "twoFactor.disable" }));
  expect(screen.getByLabelText("auth.password")).toBeTruthy();
  expect(screen.getByLabelText("twoFactor.codeOrRecovery")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "common.cancel" }));
  expect(update).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("auth.password")).toBeNull();
});
