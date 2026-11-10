// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantManageItem } from "../AssistantManageItem";
import { TeamItem } from "../TeamItem";
import { WebSearchItem } from "../WebSearchItem";
import { PersonaItem } from "../PersonaItem";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      options?.count !== undefined ? `${key}: ${options.count}` : key,
  }),
}));
vi.mock("../../../../common", () => ({
  CollapsiblePill: ({
    label,
    description,
    suffix,
  }: {
    label: string;
    description?: string;
    suffix?: string;
  }) => (
    <button data-description={description} data-suffix={suffix}>
      {label} {description} {suffix}
    </button>
  ),
  CopyButton: () => null,
}));

afterEach(cleanup);

test("assistant list previews returned names and count", () => {
  const view = render(
    <AssistantManageItem
      toolName="list_assistants"
      args={{}}
      result={{ assistants: [{ name: "Writer" }, { name: "Reviewer" }] }}
    />,
  );
  expect(view.getByRole("button").textContent).toContain("Writer Reviewer");
  expect(view.getByRole("button").textContent).toContain(
    "toolAssistantCount: 2",
  );
});

test("empty assistant list shows zero instead of a bare title", () => {
  const view = render(
    <AssistantManageItem
      toolName="list_assistants"
      args={{}}
      result={{ assistants: [] }}
    />,
  );
  expect(view.getByRole("button").textContent).toContain(
    "toolAssistantCount: 0",
  );
});

test.each([{}, { tag: "writing" }, { query: "editor" }])(
  "role search shows result count with optional filters: %j",
  (args) => {
    const view = render(
      <TeamItem
        toolName="search_persona_presets"
        args={args}
        success
        result={JSON.stringify({ success: true, presets: [] })}
      />,
    );
    expect(view.getByRole("button").textContent).toContain(
      "toolPersonaCount: 0",
    );
    if ("tag" in args)
      expect(view.getByRole("button").textContent).toContain("writing");
    if ("query" in args)
      expect(view.getByRole("button").textContent).toContain("editor");
  },
);

test("search count stays in the text instead of a separate right column", () => {
  const view = render(
    <TeamItem
      toolName="search_persona_presets"
      args={{}}
      success
      result={JSON.stringify({ presets: [{ name: "Editor" }] })}
    />,
  );
  expect(view.getByRole("button").getAttribute("data-suffix")).toBeNull();
  expect(view.getByRole("button").textContent).toContain("Editor");
});

test.each(["created", "updated"])(
  "persona shows the actual %s operation and description",
  (action) => {
    const view = render(
      <PersonaItem
        args={{ name: "Writer" }}
        success
        result={JSON.stringify({
          success: true,
          action,
          preset: { name: "Writer", description: "Draft articles" },
        })}
      />,
    );
    expect(view.getByRole("button").textContent).toContain(
      action === "created" ? "toolPersonaCreated" : "toolPersonaUpdated",
    );
    expect(view.getByRole("button").textContent).toContain("Draft articles");
  },
);

test("web search result counts are plain inline text, including zero", () => {
  const view = render(
    <WebSearchItem
      args={{ query: "数据中心" }}
      success
      result={{ results: [] }}
    />,
  );
  expect(view.getByRole("button").textContent).toContain(
    "数据中心 chat.message.toolWebSearchResults: 0",
  );
  expect(view.container.querySelector(".count-badge")).toBeNull();
});
