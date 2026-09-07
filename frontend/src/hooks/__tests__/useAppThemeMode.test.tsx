/** @vitest-environment jsdom */

import { act, render, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";

import { useAppThemeMode } from "../useAppThemeMode";

function Probe() {
  const mode = useAppThemeMode();
  return <div data-testid="probe">{mode}</div>;
}

function probeText(container: HTMLElement) {
  return container.querySelector<HTMLElement>('[data-testid="probe"]')!
    .textContent;
}

test("reads the current theme mode from html classes on mount", () => {
  const { container } = render(<Probe />);
  expect(probeText(container)).toBe("light");
});

test("follows html class changes into sepia and dark", async () => {
  const { container } = render(<Probe />);
  expect(probeText(container)).toBe("light");

  act(() => {
    document.documentElement.classList.add("theme-sepia");
  });
  await waitFor(() => expect(probeText(container)).toBe("sepia"));

  act(() => {
    document.documentElement.classList.remove("theme-sepia");
    document.documentElement.classList.add("dark");
  });
  await waitFor(() => expect(probeText(container)).toBe("dark"));

  document.documentElement.classList.remove("dark");
});
