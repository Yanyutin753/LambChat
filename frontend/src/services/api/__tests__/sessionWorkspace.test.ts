import { expect, test, vi } from "vitest";
const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("../fetch", () => ({ authFetch: fetchMock }));
import { saveSessionWorkspaceOption } from "../sessionWorkspace";
import { sandboxFsApi } from "../sandboxFs";

test("file listing waits for the selected workspace to be persisted", async () => {
  let finish!: () => void;
  fetchMock.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  const saved = saveSessionWorkspaceOption("session-1", "sandbox", "local");
  const listing = sandboxFsApi.list("session-1");
  await Promise.resolve();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
    metadata: { "agent_options.sandbox": "local" },
  });
  finish();
  await Promise.all([saved, listing]);
  expect(fetchMock.mock.calls[1][0]).toContain("/api/sandbox/fs/list?");
});

test("rapid machine and directory changes are saved in order", async () => {
  fetchMock.mockClear();
  let finish!: () => void;
  fetchMock.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  const first = saveSessionWorkspaceOption(
    "session-2",
    "sandbox_machine_id",
    "mac",
  );
  const second = saveSessionWorkspaceOption(
    "session-2",
    "sandbox_workspace",
    "selection",
  );
  await Promise.resolve();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  finish();
  await Promise.all([first, second]);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("refresh retries a failed workspace save before reading files", async () => {
  fetchMock.mockReset();
  fetchMock.mockRejectedValueOnce(new Error("offline"));
  await expect(
    saveSessionWorkspaceOption("recover", "sandbox", "local"),
  ).rejects.toThrow("offline");
  await sandboxFsApi.list("recover");
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    expect.stringContaining("/api/sessions/recover"),
    expect.stringContaining("/api/sessions/recover"),
    expect.stringContaining("/api/sandbox/fs/list?"),
  ]);
});

test("a later directory save also persists a machine change that failed", async () => {
  fetchMock.mockReset();
  fetchMock.mockRejectedValueOnce(new Error("offline"));
  const machine = saveSessionWorkspaceOption(
    "recover-machine",
    "sandbox_machine_id",
    "mac",
  );
  const directory = saveSessionWorkspaceOption(
    "recover-machine",
    "sandbox_workspace",
    "selection",
  );
  await expect(machine).rejects.toThrow("offline");
  await directory;
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
    metadata: {
      "agent_options.sandbox_machine_id": "mac",
      "agent_options.sandbox_workspace": "selection",
    },
  });
});
