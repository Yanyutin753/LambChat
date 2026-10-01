/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { MobileMenu } from "../MobileMenu";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("public mobile navigation keeps keyboard focus in the open menu", () => {
  render(
    <MemoryRouter>
      <MobileMenu
        activeSection="hero"
        onClose={vi.fn()}
        onScrollToSection={vi.fn()}
      />
    </MemoryRouter>,
  );
  const nav = screen.getByRole("navigation");
  const first = nav.querySelector("button")!;
  const last = nav.querySelector("a")!;
  expect(document.activeElement).toBe(first);
  first.focus();
  fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
  expect(document.activeElement).toBe(last);
  fireEvent.keyDown(last, { key: "Tab" });
  expect(document.activeElement).toBe(first);
});
