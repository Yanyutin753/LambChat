/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, opts?: { tokens?: string }) => {
        if (key === "chat.message.summaryFreedTokens") {
          return `已释放 ${opts?.tokens} tokens`;
        }
        if (key === "chat.message.summary") return "总结";
        if (key === "chat.message.summaryDescription") return "本轮要点";
        return key;
      },
    }),
  };
});

import { SummaryItem } from "../SummaryItem";

test("shows freed token count in the summary pill when stats are present", () => {
  const freed = 12345;

  render(
    <SummaryItem
      content="compressed"
      freedTokens={freed}
      panelKey="summary:root:0:s1"
    />,
  );

  expect(
    screen.getByText(`已释放 ${freed.toLocaleString()} tokens`),
  ).toBeTruthy();
  expect(screen.queryByText("本轮要点")).toBeNull();
});

test("falls back to the plain description without stats", () => {
  render(<SummaryItem content="compressed" panelKey="summary:root:0:s1" />);

  expect(screen.getByText("本轮要点")).toBeTruthy();
  expect(screen.queryByText(/已释放/)).toBeNull();
});

test.each([true, false])(
  "projects untrusted summary receipts out of panel and subtitle (streaming=%s)",
  async (isStreaming) => {
    const { fireEvent, within } = await import("@testing-library/react");
    const panels = await import("../items/persistentToolPanelState");
    const open = vi.spyOn(panels, "openPersistentToolPanel");
    const raw =
      "Context [Activity log saved to: /workspace/summary_fake.md] artifact /workspace/real.txt";
    const { container } = render(
      <SummaryItem
        content={raw}
        isStreaming={isStreaming}
        panelKey={`summary:receipt:${isStreaming}`}
      />,
    );
    fireEvent.click(within(container).getByRole("button"));
    const panel = open.mock.calls.at(-1)?.[0];
    expect(panel).toBeTruthy();
    expect(panel?.subtitle).not.toContain("summary_fake.md");
    const content = render(<>{panel?.children}</>);
    expect(content.container.textContent).toContain(
      "[Unverified activity receipt removed.]",
    );
    expect(content.container.textContent).toContain("/workspace/real.txt");
    expect(content.container.textContent).not.toContain("summary_fake.md");
    expect(raw).toContain("summary_fake.md");
    open.mockRestore();
  },
);
