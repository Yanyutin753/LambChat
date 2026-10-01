import {
  groupSessionsByTime,
  groupSessionsForSidebar,
} from "../sessionHelpers.ts";
import type { BackendSession } from "../../../services/api.ts";

function makeSession(updatedAt: string): BackendSession {
  return {
    id: updatedAt,
    agent_id: "chat",
    created_at: updatedAt,
    updated_at: updatedAt,
    is_active: true,
    metadata: {},
  };
}

function pinSession(session: BackendSession): BackendSession {
  return { ...session, metadata: { ...session.metadata, is_pinned: true } };
}

const labelPassThrough = ((key: string) => key) as never;

/** 后端时间戳格式（无时区，按 UTC 解析）：now 偏移 days 天。 */
function backendTimestamp(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 23);
}

test("groupSessionsForSidebar excludes pinned sessions from time groups", () => {
  const pinnedOld = pinSession(makeSession(backendTimestamp(30)));
  const pinnedRecent = pinSession(makeSession(backendTimestamp(0.1)));
  const normalToday = makeSession(backendTimestamp(0));

  const groups = groupSessionsForSidebar(
    [pinnedRecent, normalToday, pinnedOld],
    labelPassThrough,
  );

  // 置顶会话由独立「置顶」分类展示，时间分组不再出现
  expect(groups).toHaveLength(1);
  expect(groups[0]?.label).toBe("sidebar.today");
  expect(groups[0]?.sessions).toEqual([normalToday]);
});

test("groupSessionsForSidebar keeps time grouping when nothing is pinned", () => {
  const normalToday = makeSession(backendTimestamp(0));
  const normalOld = makeSession(backendTimestamp(30));

  const groups = groupSessionsForSidebar(
    [normalToday, normalOld],
    labelPassThrough,
  );

  expect(groups.map((group) => group.label)).toEqual([
    "sidebar.today",
    "sidebar.older",
  ]);
});

test("groupSessionsByTime treats timezone-less backend timestamps as UTC", () => {
  const originalTimezone = process.env.TZ;
  const NativeDate = Date;
  process.env.TZ = "Asia/Shanghai";

  class FixedDate extends NativeDate {
    constructor();
    constructor(value: string | number | Date);
    constructor(
      year: number,
      monthIndex: number,
      date?: number,
      hours?: number,
      minutes?: number,
      seconds?: number,
      ms?: number,
    );
    constructor(
      ...args:
        | []
        | [string | number | Date]
        | [number, number, number?, number?, number?, number?, number?]
    ) {
      if (args.length === 0) {
        super("2026-05-08T01:00:00.000Z");
      } else if (args.length === 1) {
        super(args[0]);
      } else if (args.length === 2) {
        super(args[0], args[1]);
      } else if (args.length === 3) {
        super(args[0], args[1], args[2]);
      } else if (args.length === 4) {
        super(args[0], args[1], args[2], args[3]);
      } else if (args.length === 5) {
        super(args[0], args[1], args[2], args[3], args[4]);
      } else if (args.length === 6) {
        super(args[0], args[1], args[2], args[3], args[4], args[5]);
      } else {
        super(args[0], args[1], args[2], args[3], args[4], args[5], args[6]);
      }
    }

    static now(): number {
      return new NativeDate("2026-05-08T01:00:00.000Z").getTime();
    }
  }

  globalThis.Date = FixedDate as DateConstructor;
  try {
    const groups = groupSessionsByTime(
      [makeSession("2026-05-07T16:30:00.000")],
      ((key: string) => key) as never,
    );

    expect(groups[0]?.label).toBe("sidebar.today");
  } finally {
    process.env.TZ = originalTimezone;
    globalThis.Date = NativeDate;
  }
});
