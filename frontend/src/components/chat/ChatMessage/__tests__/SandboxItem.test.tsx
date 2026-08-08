/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, string>) => {
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
