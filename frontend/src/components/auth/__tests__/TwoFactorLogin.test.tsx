/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { TwoFactorLogin } from "../TwoFactorLogin";

const { verify, refresh } = vi.hoisted(() => ({
  verify: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("../../../services/api", () => ({
  authApi: { verifyTwoFactor: verify },
  getRedirectPath: () => "/chat",
  clearRedirectPath: vi.fn(),
}));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ refreshUser: refresh }),
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../AuthLayout", () => ({
  AuthLayout: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function show() {
  const done = vi.fn();
  const cancel = vi.fn();
  render(
    <MemoryRouter>
      <TwoFactorLogin
        challenge="challenge"
        onSuccess={done}
        onCancel={cancel}
      />
    </MemoryRouter>,
  );
  return { done, cancel };
}

test("only finishes sign-in after the second factor succeeds", async () => {
  verify.mockResolvedValue({ access_token: "access" });
  refresh.mockResolvedValue(undefined);
  const { done } = show();
  fireEvent.change(screen.getByLabelText("twoFactor.code"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "twoFactor.verify" }));
  await waitFor(() => expect(done).toHaveBeenCalledWith("/chat"));
  expect(verify).toHaveBeenCalledWith("challenge", "123456");
  expect(refresh).toHaveBeenCalledOnce();
});

test("recovery login accepts a complete recovery code", async () => {
  verify.mockResolvedValue({ access_token: "access" });
  const { done } = show();
  fireEvent.click(
    screen.getByRole("button", { name: "twoFactor.useRecovery" }),
  );
  fireEvent.change(screen.getByLabelText("twoFactor.recoveryCode"), {
    target: { value: "abcde-f0123-45678-9abcd" },
  });
  fireEvent.click(screen.getByRole("button", { name: "twoFactor.verify" }));
  await waitFor(() => expect(done).toHaveBeenCalledOnce());
  expect(verify).toHaveBeenCalledWith("challenge", "abcde-f0123-45678-9abcd");
});

test("an expired challenge offers restart and never completes login", async () => {
  verify.mockRejectedValue(
    Object.assign(new Error("expired"), { code: "two_factor_expired" }),
  );
  const { done, cancel } = show();
  fireEvent.change(screen.getByLabelText("twoFactor.code"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "twoFactor.verify" }));
  await screen.findByRole("alert");
  expect(done).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
  expect(
    (
      screen.getByRole("button", {
        name: "twoFactor.verify",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "auth.backToLogin" }));
  expect(cancel).toHaveBeenCalledOnce();
});
