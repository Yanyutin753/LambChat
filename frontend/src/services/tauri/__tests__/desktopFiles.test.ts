import { beforeEach, expect, test, vi } from "vitest";
import {
  desktopFileAttachment,
  readDesktopFile,
  canUseLocalAttachment,
  resolveDesktopAttachmentEnvironment,
} from "../desktopFiles";
const bridge = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("../sandboxShell", () => ({
  invokeInShell: bridge.invoke,
  isShellAvailable: () => true,
}));
const file = {
  token: "a".repeat(32),
  path: "/tmp/a.txt",
  name: "a.txt",
  size: 3,
  modified: "1",
};
beforeEach(() => bridge.invoke.mockReset());
test("local attachment is immediately sendable without upload or reading bytes", () => {
  const item = desktopFileAttachment(file, "m1");
  expect(item.localFile).toEqual({
    path: file.path,
    machineId: "m1",
    token: file.token,
  });
  expect(item.key).toBe("");
  expect(item.url).toBeUndefined();
  expect(bridge.invoke).not.toHaveBeenCalled();
});
test("only the matching local machine can use a local attachment", () => {
  const item = desktopFileAttachment(file, "m1");
  expect(canUseLocalAttachment(item, "local", "m1")).toBe(true);
  expect(canUseLocalAttachment(item, "cloud", "m1")).toBe(false);
  expect(canUseLocalAttachment(item, "local", "m2")).toBe(false);
});
test("cloud promotion reads only an opaque selected-file receipt", async () => {
  bridge.invoke.mockResolvedValueOnce(file).mockResolvedValueOnce([97, 98, 99]);
  const result = await readDesktopFile(
    file.token,
    10,
    new AbortController().signal,
  );
  expect(result.size).toBe(3);
  expect(bridge.invoke.mock.calls[1][1]).toMatchObject({
    token: file.token,
    offset: 0,
    length: 3,
    modified: "1",
    size: 3,
  });
  expect(bridge.invoke.mock.calls[1][1]).not.toHaveProperty("path");
});
test("oversize and cancelled reads do not load file bytes", async () => {
  bridge.invoke.mockResolvedValue(file);
  await expect(
    readDesktopFile(file.token, 2, new AbortController().signal),
  ).rejects.toThrow();
  expect(bridge.invoke).toHaveBeenCalledTimes(1);
  const controller = new AbortController();
  controller.abort();
  bridge.invoke.mockClear();
  await expect(
    readDesktopFile(file.token, 10, controller.signal),
  ).rejects.toThrow();
  expect(bridge.invoke).not.toHaveBeenCalled();
});

test.each([
  ["HEIC", "image"],
  ["heif", "image"],
  ["avif", "image"],
  ["flac", "audio"],
  ["mkv", "video"],
])("native %s uses its media category", (extension, category) => {
  expect(
    desktopFileAttachment({ ...file, name: `a.${extension}` }, "m1").type,
  ).toBe(category);
});
test("restored drafts wait for agent and local machine resolution", () => {
  const ready = {
    agent: { supports_sandbox: true },
    mode: "local",
    selectedMachine: undefined,
    defaultMachineId: "m1",
    currentMachineId: "m1",
  };
  expect(
    resolveDesktopAttachmentEnvironment({ ...ready, agent: undefined }).mode,
  ).toBe("pending");
  expect(
    resolveDesktopAttachmentEnvironment({ ...ready, defaultMachineId: null })
      .mode,
  ).toBe("pending");
  expect(
    resolveDesktopAttachmentEnvironment({ ...ready, currentMachineId: null })
      .mode,
  ).toBe("pending");
  expect(
    resolveDesktopAttachmentEnvironment({ ...ready, mode: undefined }).mode,
  ).toBe("pending");
  expect(resolveDesktopAttachmentEnvironment(ready)).toEqual({
    mode: "local",
    machineId: "m1",
  });
  expect(
    resolveDesktopAttachmentEnvironment({
      ...ready,
      mode: "cloud",
      currentMachineId: null,
    }).mode,
  ).toBe("cloud");
});

test("TypeScript source remains a document despite the ambiguous ts video extension", () => {
  expect(desktopFileAttachment({ ...file, name: "source.ts" }, "m1").type).toBe(
    "document",
  );
});
