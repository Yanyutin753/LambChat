/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ThinkingBlock } from "../ThinkingBlock";

vi.mock("../useSmoothStreamText", () => ({
  useSmoothStreamText: (value: string) => value,
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("keeps full reasoning in the single-line preview as streamed text grows and completes", () => {
  vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(640);
  const content = "先分析完整需求。".repeat(40) + "\n再检查边界条件。";
  const { rerender } = render(<ThinkingBlock content={content} isStreaming />);
  expect(screen.getByRole("button").textContent).toContain(content);
  expect(
    screen.getByRole("button").querySelector(".text-clip")?.scrollLeft,
  ).toBe(640);
  const next = content + "\n确认最终方案。";
  rerender(<ThinkingBlock content={next} isStreaming />);
  expect(screen.getByRole("button").textContent).toContain(next);
  rerender(<ThinkingBlock content={next} />);
  expect(screen.getByRole("button").textContent).toContain(next);
  expect(
    screen
      .getByRole("button")
      .querySelector(".pill-btn__label > span:last-child")?.scrollLeft,
  ).toBe(0);
});

test("hides streamed and replayed activity receipts while preserving ordinary references", () => {
  const { rerender } = render(
    <ThinkingBlock content="Before [Act" isStreaming />,
  );
  expect(screen.getByRole("button").textContent).not.toContain("[Act");
  const receipt =
    "Before [Activity log saved to: /workspace/reasoning_fake.md] after";
  rerender(<ThinkingBlock content={receipt} isStreaming />);
  expect(screen.getByRole("button").textContent).toContain(
    "Before [Unverified activity receipt removed.] after",
  );
  expect(screen.getByRole("button").textContent).not.toContain(
    "reasoning_fake",
  );
  rerender(<ThinkingBlock content={receipt} />);
  expect(screen.getByRole("button").textContent).not.toContain(
    "reasoning_fake",
  );
  rerender(
    <ThinkingBlock content="Before [Activity log saved to: /workspace/reasoning_fake.md" />,
  );
  expect(screen.getByRole("button").textContent).not.toContain(
    "reasoning_fake",
  );
  rerender(
    <ThinkingBlock content="No file /workspace/reasoning_fake.md. [Act" />,
  );
  expect(screen.getByRole("button").textContent).toContain(
    "No file /workspace/reasoning_fake.md. [Act",
  );
});

test("explains an actually filtered reasoning receipt without changing the signed source", async () => {
  const { stripActivityReferences } = await import(
    "../../../../utils/activityReferences"
  );
  const raw = "```text\n[Activity log saved to: /workspace/fake.md]\n```";
  const expected = "```text\n[Unverified activity receipt removed.]\n```";
  expect(stripActivityReferences(raw)).toBe(expected);
  expect(stripActivityReferences(expected)).toBe(expected);
  expect(
    stripActivityReferences(
      "[Activity log saved to: /workspace/incomplete.md",
      true,
    ),
  ).toBe("[Unverified activity receipt removed.]");
  const { rerender } = render(<ThinkingBlock content={raw} isStreaming />);
  expect(screen.getByRole("button").textContent).toContain(
    "[Unverified activity receipt removed.]",
  );
  expect(screen.getByRole("button").textContent).not.toContain("fake.md");
  rerender(<ThinkingBlock content={raw} />);
  expect(screen.getByRole("button").textContent).toContain(
    "[Unverified activity receipt removed.]",
  );
  expect(raw).toBe("```text\n[Activity log saved to: /workspace/fake.md]\n```");
});
