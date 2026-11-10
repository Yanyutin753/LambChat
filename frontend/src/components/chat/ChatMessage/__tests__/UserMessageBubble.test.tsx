/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, options?: { index?: number }) => {
        if (key === "mode.auto") return "自动";
        if (key === "mode.goal") return "目标";
        if (key === "fileUpload.composerReferenceNumber")
          return `引用 ${options?.index}`;
        return key;
      },
    }),
  };
});

import { UserMessageBubble } from "../UserMessageBubble";

test("shows mode icons beside bookmarks without adding labels to the bubble", () => {
  const view = render(
    <UserMessageBubble
      content="ok"
      runModes={["auto", "goal"]}
      extraActions={<button aria-label="bookmark" />}
    />,
  );

  expect(
    view.container.querySelector(".user-message-bubble"),
  ).toHaveTextContent(/^ok$/);
  const auto = screen.getByRole("img", { name: "自动" });
  const goal = screen.getByRole("img", { name: "目标" });
  expect(auto).toHaveAttribute("title", "自动");
  expect(goal).toHaveAttribute("title", "目标");
  expect(auto.querySelector("svg")).not.toBeNull();
  expect(goal.querySelector("svg")).not.toBeNull();
  expect(auto.nextElementSibling).toBe(goal);
  expect(goal.nextElementSibling).toBe(
    screen.getByRole("button", { name: "bookmark" }),
  );
  expect(goal.parentElement).toHaveClass("chat-user-actions");
  expect(screen.queryByText("自动")).toBeNull();
  expect(screen.queryByText("目标")).toBeNull();
});

test("renders no mode icons when the message carries none", () => {
  render(<UserMessageBubble content="ok" />);

  expect(screen.getByText("ok")).toBeTruthy();
  expect(screen.queryByRole("img", { name: "自动" })).toBeNull();
  expect(screen.queryByRole("img", { name: "目标" })).toBeNull();
});

test("keeps inline skills inside the original emphasis and numbered list", () => {
  const view = render(
    <UserMessageBubble
      content={
        "1. **先 [引用技能：writer] 后**\n2. `保留 [引用技能：writer] 原文`\n3. 结束"
      }
      enabledSkills={["writer"]}
    />,
  );
  const list = view.container.querySelector("ol")!;
  expect(list.querySelectorAll("li")).toHaveLength(3);
  expect(list.querySelector("strong .skill-chip-node-name")).toHaveTextContent(
    "writer",
  );
  expect(list.querySelector("strong")).toHaveTextContent("先 writer 后");
  expect(list.querySelector("code")).toHaveTextContent(
    "保留 [引用技能：writer] 原文",
  );
  expect(view.container.querySelectorAll(".skill-chip-node")).toHaveLength(1);
});

test("shows skill-only legacy messages and keeps file references in place", () => {
  const view = render(<UserMessageBubble enabledSkills={["writer"]} />);
  expect(
    view.container.querySelector(".user-message-bubble"),
  ).toHaveTextContent("writer");
  view.rerender(
    <UserMessageBubble
      content="先 [引用技能：writer] 中间 [引用文件：notes.txt] 结尾"
      enabledSkills={["writer"]}
      attachments={[
        {
          id: "file",
          name: "notes.txt",
          key: "notes",
          mimeType: "text/plain",
          size: 12,
          category: "document",
        },
      ]}
    />,
  );
  expect(
    view.container.querySelector(".user-message-inline-markdown"),
  ).toHaveTextContent("先 writer 中间 引用 1 结尾");
  expect(
    screen.getByRole("button", { name: "File notes.txt, ready" }),
  ).toBeInTheDocument();
});

test("keeps math markup and numbering across reference-bearing paragraphs", () => {
  const view = render(
    <UserMessageBubble
      content={
        "$x^2$ [引用文件：notes.txt]\n\n后段 **[引用文件：notes.txt]** [引用技能：unknown]"
      }
      attachments={[
        {
          id: "file",
          name: "notes.txt",
          key: "notes",
          mimeType: "text/plain",
          size: 12,
          category: "document",
        },
      ]}
    />,
  );
  expect(view.container.querySelector(".katex-html")).toHaveAttribute(
    "aria-hidden",
    "true",
  );
  expect(screen.getByText("引用 1")).toBeInTheDocument();
  expect(view.container.querySelector("strong")).toHaveTextContent("引用 2");
  expect(view.container).toHaveTextContent("[引用技能：unknown]");
});
