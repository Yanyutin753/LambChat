import { afterEach, expect, test, vi } from "vitest";
import { sandboxCloudFsApi, sandboxFsApi } from "../sandboxFs";

const response = vi.hoisted(() => vi.fn());
vi.mock("../fetch", () => ({ authFetchResponse: response, authFetch: vi.fn() }));
vi.mock("../sessionWorkspace", () => ({ waitForSessionWorkspace: vi.fn() }));
afterEach(() => vi.clearAllMocks());

test.each([sandboxCloudFsApi, sandboxFsApi])("workspace sources request raw binary with cancellation", async (source) => {
  response.mockResolvedValue(new Response(new Uint8Array([0, 255, 128]), {
    headers: { "Content-Type": "application/octet-stream" },
  }));
  const controller = new AbortController();
  const result = await source.read("s", "image.png", 0, 500, controller.signal);
  expect(result.encoding).toBe("binary");
  expect(Array.from(new Uint8Array(await result.blob!.arrayBuffer()))).toEqual([0, 255, 128]);
  expect(response.mock.calls[0][0]).toContain("stream=true");
  expect(response.mock.calls[0][1].signal).toBe(controller.signal);
});

test("text paging and file errors retain their JSON contract", async () => {
  for (const body of [{ encoding: "utf-8", content: "page", next_offset: 500 }, { error: "file_too_large" }]) {
    response.mockResolvedValue(new Response(JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
    }));
    expect(await sandboxCloudFsApi.read("s", "notes.txt")).toEqual(body);
  }
});
