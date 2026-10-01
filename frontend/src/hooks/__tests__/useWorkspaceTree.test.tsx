/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useWorkspaceTree } from "../useWorkspaceTree";
afterEach(cleanup);

test("refresh keeps expanded nested files even when root is the slowest request", async () => {
  let refreshRoot!: (value: unknown) => void;
  const list = vi
    .fn()
    .mockImplementation(async (_session: string, path: string) => ({
      entries: path
        ? [{ path: "docs/readme.md", is_dir: false }]
        : [{ path: "docs", is_dir: true }],
    }));
  const source = { list, read: vi.fn() };
  const { result } = renderHook(() => useWorkspaceTree("s", "s", source));
  await waitFor(() => expect(result.current.state).toBe("ready"));
  act(() => result.current.toggleDir("docs"));
  await waitFor(() => expect(result.current.root[0].children).toHaveLength(1));
  list.mockImplementation((_session, path) =>
    path
      ? Promise.resolve({
          entries: [{ path: "docs/readme.md", is_dir: false }],
        })
      : new Promise((resolve) => {
          refreshRoot = resolve;
        }),
  );
  act(() => result.current.refresh());
  await act(async () =>
    refreshRoot({ entries: [{ path: "docs", is_dir: true }] }),
  );
  await waitFor(() => expect(result.current.root[0].children).toHaveLength(1));
  expect(result.current.expandedPaths.has("docs")).toBe(true);
});
