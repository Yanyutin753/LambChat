import {
  createAppNotificationService,
  detectAppNotificationRuntime,
} from "../appNotificationService.ts";

test("detects Tauri before Capacitor so desktop app uses the Tauri adapter", () => {
  expect(
    detectAppNotificationRuntime({
      locationLike: { protocol: "capacitor:" },
      globalLike: {
        Capacitor: {
          isNativePlatform: () => true,
          getPlatform: () => "android",
        },
        __TAURI_INTERNALS__: {},
      },
    }),
  ).toBe("tauri");
});

test("detects Capacitor Android for native Android builds", () => {
  expect(
    detectAppNotificationRuntime({
      locationLike: { protocol: "https:" },
      globalLike: {
        Capacitor: {
          isNativePlatform: () => true,
          getPlatform: () => "android",
        },
      },
    }),
  ).toBe("capacitor-android");
});

test("treats ordinary web runtimes as unsupported", () => {
  expect(
    detectAppNotificationRuntime({
      locationLike: { protocol: "https:", hostname: "chat.example.com" },
      globalLike: {},
    }),
  ).toBe("unsupported");
});

test("delivers a normalized payload through the selected native adapter", async () => {
  const delivered: unknown[] = [];
  const service = createAppNotificationService({
    runtime: "tauri",
    adapters: {
      tauri: {
        async requestPermission() {
          return "granted";
        },
        async notify(payload) {
          delivered.push(payload);
        },
      },
    },
  });

  const result = await service.notify({
    type: "task",
    title: "Design Review",
    body: "Task completed",
    route: "/chat/session-1",
    dedupeKey: "task:run-1",
    importance: "high",
  });

  expect(result).toBe("delivered");
  expect(delivered).toEqual([
    {
      type: "task",
      title: "Design Review",
      body: "Task completed",
      route: "/chat/session-1",
      dedupeKey: "task:run-1",
      importance: "high",
    },
  ]);
});

test("deduplicates repeated notifications with the same dedupe key", async () => {
  let count = 0;
  const service = createAppNotificationService({
    runtime: "capacitor-android",
    adapters: {
      capacitorAndroid: {
        async requestPermission() {
          return "granted";
        },
        async notify() {
          count += 1;
        },
      },
    },
  });

  expect(
    await service.notify({
      type: "message",
      title: "New reply",
      dedupeKey: "message:session-1:5",
    }),
  ).toBe("delivered");
  expect(
    await service.notify({
      type: "message",
      title: "New reply",
      dedupeKey: "message:session-1:5",
    }),
  ).toBe("deduped");
  expect(count).toBe(1);
});

test("does not deliver app-only notifications on unsupported web runtimes", async () => {
  const service = createAppNotificationService({
    runtime: "unsupported",
    adapters: {},
  });

  expect(
    await service.notify({
      type: "announcement",
      title: "Maintenance",
      route: "/notifications",
    }),
  ).toBe("unsupported");
});

test("reports permission denial without calling the native adapter", async () => {
  let delivered = false;
  const service = createAppNotificationService({
    runtime: "tauri",
    adapters: {
      tauri: {
        async requestPermission() {
          return "denied";
        },
        async notify() {
          delivered = true;
        },
      },
    },
  });

  expect(
    await service.notify({
      type: "auth",
      title: "Permission needed",
    }),
  ).toBe("permission-denied");
  expect(delivered).toBe(false);
});
