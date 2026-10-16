/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, string>) => {
        if (key === "chat.sandboxInitFailed")
          return "Sandbox initialization failed";
        if (key === "chat.sandbox.initializing") return "Initializing sandbox";
        if (key === "chat.sandbox.name") return "Sandbox";
        if (key === "chat.cancelled") return "Cancelled";
        if (key === "chat.sandbox.ready") return "Sandbox ready";
        if (key === "chat.sandboxId") return `ID: ${values?.id}`;
        if (key === "chat.sandbox.elapsed") {
          return `Elapsed ${values?.duration}`;
        }
        return key;
      },
    }),
  };
});

import { SandboxItem } from "../SandboxItem";

test("ready sandbox shows its ID in the pill and keeps it in expanded details", () => {
  render(
    <SandboxItem
      status="ready"
      sandboxId="SBX-AbC123"
      startedAt="2026-08-09T00:00:00.000Z"
      completedAt="2026-08-09T00:00:01.000Z"
    />,
  );

  expect(screen.getByText("ID: SBX-AbC123")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /sandbox ready/i }));

  expect(screen.getAllByText("ID: SBX-AbC123")).toHaveLength(2);
  expect(screen.getByText("Elapsed 1s")).toBeInTheDocument();
});

test("streamed initialization failure names the failure before details are expanded", () => {
  const { rerender } = render(<SandboxItem status="starting" />);
  expect(
    screen.getByRole("button", { name: /initializing sandbox/i }),
  ).toBeVisible();
  rerender(<SandboxItem status="error" error="Provider unavailable" />);
  const toggle = screen.getByRole("button", {
    name: "Sandbox initialization failed",
  });
  expect(toggle.querySelector(".pill-btn__status")).toBeNull();
  expect(toggle.querySelector(".lucide-box")).not.toBeNull();
  expect(toggle.querySelector(".pill-btn__chevron")).not.toBeNull();
  expect(screen.queryByText("Provider unavailable")).not.toBeInTheDocument();
  fireEvent.click(toggle);
  expect(screen.getByText("Provider unavailable")).toBeVisible();
});

test("failure without provider details still explains the status when expanded", () => {
  render(<SandboxItem status="error" />);
  fireEvent.click(
    screen.getByRole("button", { name: "Sandbox initialization failed" }),
  );
  expect(screen.getAllByText("Sandbox initialization failed")).toHaveLength(2);
});

test("cancelled sandbox has a visible cancellation label", () => {
  render(<SandboxItem status="cancelled" />);
  expect(
    screen.getByRole("button", { name: /sandbox.*cancelled/i }),
  ).toBeVisible();
});

test("sandbox failure exposes its disclosure before first expansion and keeps long details scrollable", () => {
  render(
    <SandboxItem status="error" error={"provider.example/".repeat(100)} />,
  );
  const toggle = screen.getByRole("button", {
    name: "Sandbox initialization failed",
  });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  const details = document.getElementById(
    toggle.getAttribute("aria-controls")!,
  );
  expect(details).toBeVisible();
  expect(details?.querySelector('[tabindex="0"]')).toBeTruthy();
});
