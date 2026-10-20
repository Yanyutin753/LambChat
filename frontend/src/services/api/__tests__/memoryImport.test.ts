import { beforeEach, expect, test, vi } from "vitest";
import { memoryApi, MemoryImportError } from "../memory";

const { authFetch } = vi.hoisted(() => ({ authFetch: vi.fn() }));
vi.mock("../fetch", () => ({ authFetch }));
const limits = {
  max_records: 1000,
  max_content_chars: 64_000,
  max_total_content_chars: 2_000_000,
};
const backup = (count: number) => ({
  version: 1,
  memories: Array.from({ length: count }, (_, i) => ({
    memory_id: `memory-${i}`,
    content: `业务记忆 ${i}: retain 45 days.`,
    scope: "project",
    project_id: "alpha",
  })),
});

beforeEach(() => vi.resetAllMocks());

test("provenance budget splits restore batches without dropping source IDs", async () => {
  const written: Array<Array<{ origin_session_ids: string[] }>> = [];
  authFetch.mockImplementation(async (url: string, init: RequestInit) => {
    const rows = JSON.parse(String(init.body)).memories;
    if (url.endsWith("?validate_only=true"))
      return {
        success: true,
        validated: rows.length,
        limits: { ...limits, max_origin_sessions: 3 },
      };
    written.push(rows);
    return {
      success: true,
      imported: rows.length,
      created: rows.length,
      overwritten: 0,
    };
  });
  await memoryApi.importAll({
    memories: [0, 1, 2].map((i) => ({
      content: `Durable fact ${i}`,
      origin_session_ids: [`${i}-a`, `${i}-b`],
    })),
  });
  expect(written.map((rows) => rows.length)).toEqual([1, 1, 1]);
  expect(written.flat().map((row) => row.origin_session_ids)).toEqual([
    ["0-a", "0-b"],
    ["1-a", "1-b"],
    ["2-a", "2-b"],
  ]);
});

test.each(["invalid", ["source", 9], [""]])(
  "invalid provenance rejects before writes: %j",
  async (origins) => {
    authFetch.mockResolvedValue({ success: true, validated: 0, limits });
    await expect(
      memoryApi.importAll({
        memories: [{ content: "Durable fact", origin_session_ids: origins }],
      }),
    ).rejects.toThrow();
    expect(authFetch.mock.calls).toHaveLength(1);
  },
);

test("50k memories preflight every bounded batch before sequential writes and keep IDs", async () => {
  let writing = false;
  let validations = 0;
  const ids: string[] = [];
  let active = 0;
  authFetch.mockImplementation(async (url: string, init: RequestInit) => {
    expect(++active).toBe(1);
    await Promise.resolve();
    const body = JSON.parse(String(init.body));
    expect(body.memories.length).toBeLessThanOrEqual(1000);
    if (url.endsWith("?validate_only=true")) {
      expect(writing).toBe(false);
      if (body.memories.length) validations++;
      active--;
      return { success: true, validated: body.memories.length, limits };
    }
    writing = true;
    expect(validations).toBe(50);
    ids.push(...body.memories.map((m: { memory_id: string }) => m.memory_id));
    active--;
    return {
      success: true,
      imported: body.memories.length,
      created: body.memories.length,
      overwritten: 0,
    };
  });
  const data = backup(50_000);
  const result = await memoryApi.importAll(data);
  expect(result).toEqual({
    success: true,
    imported: 50_000,
    created: 50_000,
    overwritten: 0,
  });
  expect(ids).toEqual(data.memories.map((m) => m.memory_id));
});

test("a late invalid or truncated record rejects the whole file before any writes", async () => {
  authFetch.mockResolvedValue({ success: true, validated: 0, limits });
  const data = backup(2001);
  Object.assign(data.memories[2000], { content_truncated: true });
  await expect(memoryApi.importAll(data)).rejects.toThrow();
  expect(
    authFetch.mock.calls.every(([url]) =>
      String(url).endsWith("?validate_only=true"),
    ),
  ).toBe(true);
});

test("preflight denial in the last batch prevents all earlier writes", async () => {
  authFetch.mockImplementation(async (url: string, init: RequestInit) => {
    expect(url.endsWith("?validate_only=true")).toBe(true);
    const rows = JSON.parse(String(init.body)).memories;
    if (rows.some((m: { memory_id: string }) => m.memory_id === "memory-2000"))
      throw new Error("foreign project");
    return { success: true, validated: rows.length, limits };
  });
  await expect(memoryApi.importAll(backup(2001))).rejects.toThrow(
    "foreign project",
  );
});

test("a lost write response reports only confirmed batches and never automatically replays", async () => {
  let writes = 0;
  authFetch.mockImplementation(async (url: string, init: RequestInit) => {
    const rows = JSON.parse(String(init.body)).memories;
    if (url.endsWith("?validate_only=true"))
      return { success: true, validated: rows.length, limits };
    if (++writes === 2) throw new Error("response lost after unknown writes");
    return {
      success: true,
      imported: rows.length,
      created: rows.length,
      overwritten: 0,
    };
  });
  try {
    await memoryApi.importAll(backup(2001));
    expect.unreachable();
  } catch (error) {
    expect(error).toBeInstanceOf(MemoryImportError);
    expect((error as MemoryImportError).confirmed.imported).toBe(1000);
  }
  expect(writes).toBe(2);
});

test("batching respects current server body limits and keeps Unicode facts", async () => {
  const smallLimits = {
    ...limits,
    max_records: 3,
    max_content_chars: 30,
    max_total_content_chars: 40,
  };
  const written: unknown[][] = [];
  const validatedIds: string[] = [];
  authFetch.mockImplementation(async (url: string, init: RequestInit) => {
    const rows = JSON.parse(String(init.body)).memories;
    expect(
      rows.reduce(
        (n: number, m: { content: string }) => n + [...m.content.trim()].length,
        0,
      ),
    ).toBeLessThanOrEqual(40);
    if (url.endsWith("?validate_only=true")) {
      validatedIds.push(...rows.map((m: { memory_id: string }) => m.memory_id));
      return { success: true, validated: rows.length, limits: smallLimits };
    }
    written.push(rows);
    return {
      success: true,
      imported: rows.length,
      created: rows.length,
      overwritten: 0,
    };
  });
  const data = {
    memories: Array.from({ length: 7 }, () => ({
      content: "😀 保修 53 个月 😀",
    })),
  };
  const result = await memoryApi.importAll(data);
  expect(result.imported).toBe(7);
  expect(written.map((rows) => rows.length)).toEqual([3, 3, 1]);
  const ids = written.flat().map((m) => (m as { memory_id: string }).memory_id);
  expect(ids).toEqual(validatedIds);
  expect(new Set(ids).size).toBe(7);
  expect(
    written
      .flat()
      .every(
        (m) => (m as { content: string }).content === "😀 保修 53 个月 😀",
      ),
  ).toBe(true);
});

test("malformed success counts remain unconfirmed and stop later batches", async () => {
  authFetch.mockImplementation(async (url: string, init: RequestInit) => {
    const rows = JSON.parse(String(init.body)).memories;
    if (url.endsWith("?validate_only=true"))
      return { success: true, validated: rows.length, limits };
    return { success: true, imported: 1000, created: -1, overwritten: 1001 };
  });
  await expect(memoryApi.importAll(backup(2001))).rejects.toMatchObject({
    confirmed: { imported: 0 },
  });
  expect(
    authFetch.mock.calls.filter(
      ([url]) => !String(url).endsWith("?validate_only=true"),
    ),
  ).toHaveLength(1);
});

test("missing IDs use the existing UUID fallback when randomUUID is unavailable", async () => {
  vi.stubGlobal("crypto", {});
  try {
    authFetch.mockImplementation(async (url: string, init: RequestInit) => {
      const rows = JSON.parse(String(init.body)).memories;
      if (url.endsWith("?validate_only=true"))
        return { success: true, validated: rows.length, limits };
      expect(rows[0].memory_id).toMatch(/^[0-9a-f]{32}$/);
      return {
        success: true,
        imported: rows.length,
        created: rows.length,
        overwritten: 0,
      };
    });
    await expect(
      memoryApi.importAll({ memories: [{ content: "Durable Unicode 约定." }] }),
    ).resolves.toMatchObject({ imported: 1 });
  } finally {
    vi.unstubAllGlobals();
  }
});
