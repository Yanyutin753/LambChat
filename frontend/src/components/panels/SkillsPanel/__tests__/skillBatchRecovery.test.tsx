/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Toaster, toast } from "react-hot-toast";
import i18n from "../../../../i18n";
import { useSkillsActions } from "../useSkillsActions";
import { BatchActionBar } from "../BatchActionBar";
import { SkillsList } from "../SkillsList";
import { MemoryPanel } from "../../MemoryPanel";
import { memoryApi } from "../../../../services/api/memory";

const fetchMock = vi.fn<typeof fetch>();
let current = [
  { name: "alpha", enabled: true },
  { name: "beta", enabled: false },
  { name: "gamma", enabled: false },
];
let operation: (body: {
  names: string[];
  enabled?: boolean;
}) => Promise<Response>;
let pendingList: Promise<Response> | null = null;
const bodies: { names: string[]; enabled?: boolean }[] = [];
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });

beforeEach(async () => {
  localStorage.clear();
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addListener() {},
    removeListener() {},
  }));
  await i18n.changeLanguage("zh");
  current = [
    { name: "alpha", enabled: true },
    { name: "beta", enabled: false },
    { name: "gamma", enabled: false },
  ];
  bodies.length = 0;
  pendingList = null;
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url, options) => {
    if (/\/batch\/(toggle|delete)$/.test(String(url))) {
      const body = JSON.parse(String(options?.body));
      bodies.push(body);
      return operation(body);
    }
    if (pendingList) return pendingList;
    return json({
      skills: current.map(({ name, enabled }) => ({
        skill_name: name,
        enabled,
        description: name,
        tags: [],
        files: ["SKILL.md"],
        file_count: 1,
        installed_from: "manual",
        is_published: false,
      })),
      total: current.length,
      available_tags: [],
      enabled_count: current.filter((skill) => skill.enabled).length,
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  toast.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function Skills({ realList = false }: { realList?: boolean }) {
  const a = useSkillsActions();
  return (
    <div data-batch-panel>
      {realList ? (
        <SkillsList
          {...a}
          canWrite
          canPublish={false}
          onPublish={undefined}
          onToggle={a.handleToggle}
          onTogglePreference={a.handleTogglePreference}
          onEdit={a.handleEdit}
          onDelete={a.handleDelete}
          onExportZip={a.handleExportZip}
          onSelectSkill={a.handleSelectSkill}
          onSelectAll={a.handleSelectAll}
          onCreate={a.handleCreate}
          onGithubClick={a.handleGithubClick}
          onZipClick={a.handleZipClick}
        />
      ) : (
        <>
          <input type="text" aria-label="Search skills" />
          {a.error && <div role="alert">{a.error}</div>}
          {a.skills.map((skill) => (
            <label key={skill.name}>
              <input
                type="checkbox"
                aria-label={skill.name}
                checked={a.selectedNames.has(skill.name)}
                onChange={() => a.handleSelectSkill(skill.name)}
              />
              <span>
                {skill.name}: {String(skill.enabled)}
              </span>
            </label>
          ))}
        </>
      )}
      {(a.selectionMode || a.batchLoading) && (
        <BatchActionBar
          selectedCount={a.selectedNames.size}
          batchLoading={a.batchLoading}
          error={a.batchError}
          onRetry={a.canBatchRetry ? a.handleBatchRetry : undefined}
          onBatchToggle={a.handleBatchToggle}
          onBatchDelete={a.handleBatchDelete}
          onClearSelection={a.clearSelection}
        />
      )}
      <Toaster />
    </div>
  );
}
async function select() {
  render(
    <MemoryRouter>
      <Skills />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("checkbox", { name: "alpha" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "beta" }));
}

test.each([
  ["启用", "部分技能切换失败"],
  ["删除", "部分技能删除失败"],
])(
  "failed batch %s preserves selection and offers a persistent retry",
  async (label, message) => {
    operation = async () => json({ detail: { message: "Unavailable" } }, 503);
    await select();
    fireEvent.click(screen.getByRole("button", { name: label, exact: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("checkbox", { name: "alpha" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "beta" })).toBeChecked();
    expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
    expect(screen.queryByText(/已(?:启用|删除) 2 个技能/)).toBeNull();
    expect(screen.getByText("alpha: true")).toBeTruthy();
    expect(screen.getByText("beta: false")).toBeTruthy();
  },
);

test("partial deletion retries only the remaining selected skill and restores search focus on success", async () => {
  operation = async () => {
    current = current.filter((skill) => skill.name !== "alpha");
    return json({
      deleted: ["alpha"],
      errors: [{ name: "beta", reason: "Unavailable" }],
    });
  };
  await select();
  fireEvent.click(screen.getByRole("button", { name: "删除", exact: true }));
  await screen.findByRole("alert");
  expect(screen.queryByRole("checkbox", { name: "alpha" })).toBeNull();
  expect(screen.getByRole("checkbox", { name: "beta" })).toBeChecked();
  operation = async () => {
    current = current.filter((skill) => skill.name !== "beta");
    return json({ deleted: ["beta"], errors: [] });
  };
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await waitFor(() =>
    expect(screen.queryByRole("checkbox", { name: "beta" })).toBeNull(),
  );
  expect(bodies).toEqual([{ names: ["alpha", "beta"] }, { names: ["beta"] }]);
  expect(screen.getByRole("textbox", { name: "Search skills" })).toHaveFocus();
});

test("partial toggle shows server states and retries only the failed selection", async () => {
  operation = async () =>
    json({
      updated: ["alpha"],
      errors: [{ name: "beta", reason: "Unavailable" }],
    });
  await select();
  fireEvent.click(screen.getByRole("button", { name: "启用", exact: true }));
  await screen.findByRole("alert");
  expect(screen.getByText("beta: false")).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: "alpha" })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "beta" })).toBeChecked();
  operation = async () => {
    current = current.map((skill) =>
      skill.name === "beta" ? { ...skill, enabled: true } : skill,
    );
    return json({ updated: ["beta"], errors: [] });
  };
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await waitFor(() => expect(screen.getByText("beta: true")).toBeTruthy());
  expect(bodies).toEqual([
    { names: ["alpha", "beta"], enabled: true },
    { names: ["beta"], enabled: true },
  ]);
});

test("pending batch announces progress and disables duplicate actions while keeping stable focus", async () => {
  let resolve!: (response: Response) => void;
  operation = () =>
    new Promise((done) => {
      resolve = done;
    });
  await select();
  const enable = screen.getByRole("button", { name: "启用", exact: true });
  enable.focus();
  fireEvent.click(enable);
  await waitFor(() => expect(bodies).toHaveLength(1));
  expect(
    within(screen.getByRole("group")).getByRole("status"),
  ).toHaveTextContent(/处理中/);
  expect(screen.getByRole("group")).toHaveFocus();
  expect(screen.getByRole("button", { name: "清除" })).toBeDisabled();
  fireEvent.click(enable);
  expect(bodies).toHaveLength(1);
  await act(async () =>
    resolve(json({ updated: ["alpha", "beta"], errors: [] })),
  );
});

test("batch completion preserves skills selected after submission", async () => {
  let resolve!: (response: Response) => void;
  operation = () =>
    new Promise((done) => {
      resolve = done;
    });
  await select();
  fireEvent.click(screen.getByRole("button", { name: "启用", exact: true }));
  await waitFor(() => expect(bodies).toHaveLength(1));
  fireEvent.click(screen.getByRole("checkbox", { name: "gamma" }));
  await act(async () =>
    resolve(json({ updated: ["alpha", "beta"], errors: [] })),
  );
  expect(screen.getByRole("checkbox", { name: "gamma" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "alpha" })).not.toBeChecked();
});

test("icon-only batch controls retain accessible names", () => {
  render(
    <>
      <style>{".ui-button__label span { display: none; }"}</style>
      <BatchActionBar
        selectedCount={1}
        batchLoading={false}
        onBatchToggle={vi.fn()}
        onBatchDelete={vi.fn()}
        onClearSelection={vi.fn()}
      />
    </>,
  );
  expect(
    screen.getByRole("button", { name: "启用", exact: true }),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "禁用", exact: true }),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "删除", exact: true }),
  ).toBeTruthy();
});

test("memory selection offers deletion and clear without nonfunctional enable controls", async () => {
  vi.spyOn(memoryApi, "list").mockResolvedValue({
    total: 1,
    memories: [
      {
        memory_id: "memory-1",
        title: "Research notes",
        summary: "Notes",
        memory_type: "fact",
        tags: [],
        content: "Notes",
        source: "manual",
        created_at: null,
        updated_at: null,
        access_count: 0,
        has_full_content: false,
      },
    ],
  });
  render(<MemoryPanel />);
  fireEvent.click(
    await screen.findByRole("checkbox", { name: "Research notes" }),
  );
  expect(
    screen.queryByRole("button", { name: "启用", exact: true }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "禁用", exact: true }),
  ).toBeNull();
  expect(
    within(screen.getByRole("group")).getByRole("button", {
      name: "删除",
      exact: true,
    }),
  ).toBeTruthy();
  expect(
    within(screen.getByRole("group")).getByRole("button", {
      name: "清除",
      exact: true,
    }),
  ).toBeTruthy();
});

test("retry excludes skills newly selected during a partially failed deletion", async () => {
  let resolve!: (response: Response) => void;
  operation = () =>
    new Promise((done) => {
      resolve = done;
    });
  await select();
  fireEvent.click(screen.getByRole("button", { name: "删除", exact: true }));
  await waitFor(() => expect(bodies).toHaveLength(1));
  fireEvent.click(screen.getByRole("checkbox", { name: "gamma" }));
  current = current.filter((skill) => skill.name !== "alpha");
  await act(async () =>
    resolve(
      json({
        deleted: ["alpha"],
        errors: [{ name: "beta", reason: "Unavailable" }],
      }),
    ),
  );
  await screen.findByRole("alert");
  operation = async () => {
    current = current.filter((skill) => skill.name !== "beta");
    return json({ deleted: ["beta"], errors: [] });
  };
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await waitFor(() => expect(bodies).toHaveLength(2));
  expect(bodies[1]).toEqual({ names: ["beta"] });
  expect(screen.getByRole("checkbox", { name: "gamma" })).toBeChecked();
});

test("deleting the final skills restores focus to the remounted real list search", async () => {
  current = current.slice(0, 2);
  let releaseList!: (response: Response) => void;
  operation = async () => {
    current = [];
    pendingList = new Promise((done) => {
      releaseList = done;
    });
    return json({ deleted: ["alpha", "beta"], errors: [] });
  };
  render(
    <MemoryRouter>
      <Skills realList />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("checkbox", { name: "alpha" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "beta" }));
  const oldSearch = screen.getByRole("textbox", { name: "搜索技能..." });
  fireEvent.click(
    within(screen.getByRole("group", { name: "已选择 2" })).getByRole(
      "button",
      { name: "删除", exact: true },
    ),
  );
  await waitFor(() => expect(oldSearch.isConnected).toBe(false));
  await act(async () =>
    releaseList(
      json({ skills: [], total: 0, available_tags: [], enabled_count: 0 }),
    ),
  );
  expect(
    await screen.findByRole("textbox", { name: "搜索技能..." }),
  ).toHaveFocus();
});

test("failed batch has no inert retry when its remaining items were unselected", async () => {
  let resolve!: (response: Response) => void;
  operation = () =>
    new Promise((done) => {
      resolve = done;
    });
  await select();
  fireEvent.click(screen.getByRole("button", { name: "启用", exact: true }));
  await waitFor(() => expect(bodies).toHaveLength(1));
  fireEvent.click(screen.getByRole("checkbox", { name: "beta" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "gamma" }));
  await act(async () =>
    resolve(
      json({
        updated: ["alpha"],
        errors: [{ name: "beta", reason: "Unavailable" }],
      }),
    ),
  );
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
  expect(screen.getByRole("checkbox", { name: "gamma" })).toBeChecked();
});
