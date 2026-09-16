/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { AskHumanItem } from "../AskHumanItem";
import { openToolLivePanel } from "../ToolLivePanelContent";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../common", () => ({
  CollapsiblePill: ({ onPanelOpen }: { onPanelOpen: () => void }) => (
    <button onClick={onPanelOpen}>Open</button>
  ),
}));
vi.mock("../ToolLivePanelContent", () => ({ openToolLivePanel: vi.fn() }));
vi.mock("../../MarkdownContent", () => ({
  MarkdownContent: ({ content }: { content: string }) => <p>{content}</p>,
}));
vi.mock("../useToolStreamingLabel", () => ({
  useToolStreamingLabel: (label: string) => ({ label }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function openDetail(status?: string, values: Record<string, unknown> = {}) {
  render(
    <AskHumanItem
      args={{
        message: "A few questions",
        allow_other: false,
        fields: [
          {
            name: "purpose",
            label: "Your purpose?",
            type: "radio",
            options: ["Development", "Writing"],
          },
          {
            name: "notes",
            label: "Background?",
            type: "textarea",
            placeholder: "Project context",
          },
          { name: "confirmed", label: "Enabled?", type: "checkbox" },
        ],
      }}
      isPending={!status}
      result={status ? JSON.stringify({ status, values }) : undefined}
    />,
  );
  fireEvent.click(screen.getByText("Open"));
  const panel = vi.mocked(openToolLivePanel).mock.calls[0][0];
  return render(panel.fallback as ReactNode);
}

test("completed answers appear once without unselected choices or empty inputs", () => {
  openDetail("success", { purpose: "Development", confirmed: false });
  expect(screen.getAllByText("Your purpose?")).toHaveLength(1);
  expect(screen.getAllByText("Development")).toHaveLength(1);
  expect(screen.queryByText("Writing")).toBeNull();
  expect(screen.queryByText("Project context")).toBeNull();
  expect(screen.getByText("Enabled?")).toBeTruthy();
  expect(screen.getByText("✗")).toBeTruthy();
});

test.each([undefined, "timeout", "rejected"])(
  "keeps question context for %s requests",
  (status) => {
    openDetail(status);
    expect(screen.getByText("Your purpose?")).toBeTruthy();
    expect(screen.getByText("Writing")).toBeTruthy();
  },
);

test("confirmation without answers does not leave an empty summary section", () => {
  const view = openDetail("success");
  expect(view.container.querySelector(".approval-result-section")).toBeNull();
});
