/** @vitest-environment jsdom */
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { resolveDroppedDesktopFiles } from "../desktopFiles";

const mock = vi.hoisted(() => ({ listen: vi.fn(), stop: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: mock.listen }));
type Payload = { requestId: string; files: unknown[]; error?: boolean };
let emit: (event: { payload: Payload }) => void;
const post = vi.fn();
const file = new File(["png"], "微信图片.png", { type: "image/png" });
beforeEach(() => {
  vi.clearAllMocks();
  mock.listen.mockImplementation(async (_name, handler) => {
    emit = handler;
    return mock.stop;
  });
  Object.defineProperty(window, "chrome", {
    configurable: true,
    value: { webview: { postMessageWithAdditionalObjects: post } },
  });
});
afterEach(() => {
  Reflect.deleteProperty(window, "chrome");
  vi.useRealTimers();
});

test("the bridge transfers real File objects, preserves nullable positions, and ignores another request", async () => {
  const pending = resolveDroppedDesktopFiles([file, file]);
  await vi.waitFor(() => expect(post).toHaveBeenCalledOnce());
  const [message, objects] = post.mock.calls[0];
  expect(message).toMatchObject({ kind: "lambchat-file-drop" });
  expect(message.requestId).toMatch(/^[a-f0-9]{32}$/);
  expect(objects[0]).toBe(file);
  emit({ payload: { requestId: "wrong", files: [], error: true } });
  const original = {
    token: "a".repeat(32),
    path: "C:\\original.png",
    name: "original.png",
    size: 3,
    modified: "1",
  };
  emit({ payload: { requestId: message.requestId, files: [original, null] } });
  expect(await pending).toEqual([original, null]);
  expect(mock.stop).toHaveBeenCalledOnce();
});

test("a native reply cannot silently drop files from a mixed selection", async () => {
  const pending = resolveDroppedDesktopFiles([file, file]);
  const rejected = expect(pending).rejects.toThrow("file_drop_unavailable");
  await vi.waitFor(() => expect(post).toHaveBeenCalledOnce());
  emit({
    payload: { requestId: post.mock.calls[0][0].requestId, files: [null] },
  });
  await rejected;
  expect(mock.stop).toHaveBeenCalledOnce();
});

test("native bridge failure is bounded by the three-second preparation budget", async () => {
  vi.useFakeTimers();
  const pending = resolveDroppedDesktopFiles([file]);
  const rejected = expect(pending).rejects.toThrow("file_drop_unavailable");
  await vi.advanceTimersByTimeAsync(3000);
  await rejected;
  expect(mock.stop).toHaveBeenCalledOnce();
});

test("cancellation while the event listener initializes never posts the file", async () => {
  let ready!: (stop: () => void) => void;
  mock.listen.mockReturnValue(
    new Promise((resolve) => {
      ready = resolve;
    }),
  );
  const controller = new AbortController();
  const pending = resolveDroppedDesktopFiles([file], controller.signal);
  const rejected = expect(pending).rejects.toMatchObject({
    name: "AbortError",
  });
  await vi.waitFor(() => expect(mock.listen).toHaveBeenCalledOnce());
  controller.abort();
  ready(mock.stop);
  await rejected;
  expect(post).not.toHaveBeenCalled();
  expect(mock.stop).toHaveBeenCalledOnce();
});
