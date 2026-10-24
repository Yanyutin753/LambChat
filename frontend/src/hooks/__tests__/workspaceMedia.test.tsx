/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useUploadFileUrl } from "../useUploadFileUrl";
import {
  WorkspaceMediaContext,
  workspaceMediaPath,
  workspaceMediaSource,
} from "../workspaceMediaContext";
import { sandboxFsApi, sandboxCloudFsApi } from "../../services/api/sandboxFs";
import { getFullUrl } from "../../services/api/config";

vi.mock("../../services/api/sandboxFs", () => ({
  sandboxFsApi: { read: vi.fn() },
  sandboxCloudFsApi: { read: vi.fn() },
}));
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <WorkspaceMediaContext.Provider
      value={{ sessionId: "session-one", cloud: false }}
    >
      {children}
    </WorkspaceMediaContext.Provider>
  );
}

test.each([
  "/workspace/session-one/frames/a.jpg",
  "C:\\Users\\yang\\a.jpg",
  "file:///C:/Users/yang/a.jpg",
])(
  "preserves local media path %s instead of turning it into a server URL",
  (path) => {
    expect(
      getFullUrl(path, "https://app.example", {
        globalLike: { __TAURI__: {} },
      }),
    ).toBe(path);
  },
);

test("local image uses authenticated workspace reads and releases the blob", async () => {
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:workspace");
      static revokeObjectURL = vi.fn();
    },
  );
  vi.mocked(sandboxFsApi.read).mockResolvedValue({
    encoding: "binary",
    blob: new Blob(["image"]),
  });
  const { result, unmount } = renderHook(
    () => useUploadFileUrl("/workspace/session-one/frames/a.jpg"),
    { wrapper },
  );
  expect(result.current.src).toBeUndefined();
  await waitFor(() => expect(result.current.src).toBe("blob:workspace"));
  expect(sandboxFsApi.read).toHaveBeenCalledWith(
    "session-one",
    "frames/a.jpg",
    0,
    500,
    expect.any(AbortSignal),
  );
  expect(sandboxCloudFsApi.read).not.toHaveBeenCalled();
  unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:workspace");
});

test("a shared view without a bound workspace cannot fetch local files", () => {
  vi.mocked(sandboxFsApi.read).mockClear();
  const { result } = renderHook(() =>
    useUploadFileUrl("C:\\Users\\yang\\a.jpg"),
  );
  expect(result.current).toMatchObject({ src: undefined, failed: true });
  expect(sandboxFsApi.read).not.toHaveBeenCalled();
});

test("late reads cannot reveal a previous file after the source changes", async () => {
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:late");
      static revokeObjectURL = vi.fn();
    },
  );
  let resolve!: (value: { blob: Blob; encoding: "binary" }) => void;
  vi.mocked(sandboxFsApi.read)
    .mockClear()
    .mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
  const { result, rerender } = renderHook(({ src }) => useUploadFileUrl(src), {
    wrapper,
    initialProps: { src: "/workspace/session-one/a.jpg" },
  });
  await waitFor(() => expect(sandboxFsApi.read).toHaveBeenCalled());
  rerender({ src: "https://example.com/public.jpg" });
  await act(async () =>
    resolve({ blob: new Blob(["old"]), encoding: "binary" }),
  );
  expect(result.current.src).toBe("https://example.com/public.jpg");
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

test("changing machines discards an in-flight read for the same media path", async () => {
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:old-machine");
      static revokeObjectURL = vi.fn();
    },
  );
  let resolve!: (value: { blob: Blob; encoding: "binary" }) => void;
  vi.mocked(sandboxFsApi.read)
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockImplementationOnce(() => new Promise(() => {}));
  let machineId = "first";
  const { result, rerender } = renderHook(
    () => useUploadFileUrl("/workspace/session-one/a.jpg"),
    {
      wrapper: ({ children }) => (
        <WorkspaceMediaContext.Provider
          value={{ sessionId: "session-one", cloud: false, machineId }}
        >
          {children}
        </WorkspaceMediaContext.Provider>
      ),
    },
  );
  await waitFor(() => expect(resolve).toBeTypeOf("function"));
  machineId = "second";
  rerender();
  await act(async () =>
    resolve({ blob: new Blob(["old"]), encoding: "binary" }),
  );
  expect(result.current.src).toBeUndefined();
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

test("cloud media uses the cloud transport and file URLs are decoded", async () => {
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:cloud");
      static revokeObjectURL = vi.fn();
    },
  );
  vi.mocked(sandboxCloudFsApi.read).mockResolvedValue({
    encoding: "base64",
    content: "aGVsbG8=",
  });
  const { result } = renderHook(
    () => useUploadFileUrl("file:///workspace/session-one/a%20b.png"),
    {
      wrapper: ({ children }) => (
        <WorkspaceMediaContext.Provider
          value={{ sessionId: "session-one", cloud: true }}
        >
          {children}
        </WorkspaceMediaContext.Provider>
      ),
    },
  );
  await waitFor(() => expect(result.current.src).toBe("blob:cloud"));
  expect(sandboxCloudFsApi.read).toHaveBeenCalledWith(
    "session-one",
    "a b.png",
    0,
    500,
    expect.any(AbortSignal),
  );
});

const selection = {
  id: "local-" + "a".repeat(32),
  machineId: "machine",
  path: "C:\\Users\\yang\\Pictures",
};
test.each([
  "/workspace/other/a.jpg",
  "/workspace/session-one/../other/a.jpg",
  "/workspace/session-one/a\0.jpg",
  "C:\\Users\\yang\\private.jpg",
])("refuses out-of-workspace media %s", (source) => {
  expect(() =>
    workspaceMediaPath(source, {
      sessionId: "session-one",
      cloud: false,
      machineId: "machine",
      selection,
    }),
  ).toThrow();
});
test("Windows selected directory paths are made relative without widening daemon access", () => {
  expect(
    workspaceMediaPath("file:///c:/Users/yang/Pictures/a%20b.jpg", {
      sessionId: "session-one",
      cloud: false,
      machineId: "machine",
      selection,
    }),
  ).toBe("a b.jpg");
  expect(() =>
    workspaceMediaPath("C:\\Users\\yang\\Pictures\\a.jpg", {
      sessionId: "session-one",
      cloud: false,
      machineId: "other",
      selection,
    }),
  ).toThrow();
});

test("selected POSIX paths survive existing URL resolution without matching other origins", () => {
  const binding = {
    sessionId: "session-one",
    cloud: false,
    machineId: "machine",
    selection: { ...selection, path: "/Users/yang/Pictures" },
  };
  expect(
    workspaceMediaSource(getFullUrl("/Users/yang/Pictures/a.png"), binding),
  ).toBe("file:///Users/yang/Pictures/a.png");
  expect(
    workspaceMediaSource(
      "https://untrusted.example/Users/yang/Pictures/a.png",
      binding,
    ),
  ).toBe("https://untrusted.example/Users/yang/Pictures/a.png");
});
