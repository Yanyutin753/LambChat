/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { ResetPassword } from "../ResetPassword";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../common/ThemeToggle", () => ({ ThemeToggle: () => null }));
vi.mock("../../common/LanguageToggle", () => ({ LanguageToggle: () => null }));
vi.mock("../../../hooks/useMobileKeyboardAware", () => ({
  useMobileKeyboardAware: () => false,
}));
afterEach(cleanup);

test("an invalid reset link leads directly to requesting a fresh link", () => {
  render(
    <MemoryRouter initialEntries={["/auth/reset-password"]}>
      <Routes>
        <Route path="/auth/reset-password" element={<ResetPassword />} />
        <Route
          path="/auth/reset-request"
          element={<h1>Request a new link</h1>}
        />
      </Routes>
    </MemoryRouter>,
  );
  fireEvent.click(
    screen.getByRole("link", { name: "auth.requestNewResetLink" }),
  );
  expect(
    screen.getByRole("heading", { name: "Request a new link" }),
  ).toBeTruthy();
});
