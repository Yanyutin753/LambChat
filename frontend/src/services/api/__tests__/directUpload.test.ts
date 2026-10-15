import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { uploadDirect } from "../directUpload";

const auth = vi.hoisted(() => vi.fn());
vi.mock("../authenticatedRequest", () => ({ authenticatedRequest: auth }));
vi.mock("i18next", () => ({ default: { t: (key: string) => key } }));
vi.mock("../config", () => ({
  getFullUrl: (path: string) => `https://app.example${path}`,
}));

class FakeXHR extends EventTarget {
  static sent: FakeXHR[] = [];
  upload = new EventTarget();
  status = 200;
  statusText = "OK";
  timeout = 0;
  method = "";
  url = "";
  body?: Blob;
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  send(body: Blob) {
    this.body = body;
    FakeXHR.sent.push(this);
  }
  abort() {
    this.dispatchEvent(new Event("abort"));
  }
  progress(loaded: number) {
    this.upload.dispatchEvent(Object.assign(new Event("progress"), { loaded }));
  }
  finish(status = 200) {
    this.status = status;
    this.dispatchEvent(new Event("load"));
  }
}

const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });
const completed = {
  key: "document/u/key",
  name: "a.txt",
  mime_type: "text/plain",
  size: 6,
  type: "document",
  url: "/file",
};
const fallback = vi.fn();

beforeEach(() => {
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
  FakeXHR.sent = [];
  auth.mockReset();
  fallback.mockReset();
  auth.mockImplementation(async (url: string, init: RequestInit) => {
    if (init.method === "DELETE") return json({ canceled: true });
    if (url.endsWith("/direct"))
      return json({
        mode: "direct",
        id: "ticket",
        part_size: 4,
        part_count: 2,
      });
    if (url.endsWith("/complete")) return json(completed);
    return json({ url: "https://storage.example/scoped-part" });
  });
});
afterEach(() => vi.unstubAllGlobals());

test("reports real server verification progress while completion is pending and stops polling afterward", async () => {
  let finish!: (response: Response) => void;
  const base = auth.getMockImplementation()!;
  auth.mockImplementation((url: string, init: RequestInit) => {
    if (url.endsWith("/complete"))
      return new Promise<Response>((resolve) => {
        finish = resolve;
      });
    if (init.method === "GET")
      return Promise.resolve(json({ state: "completing", progress: 45 }));
    return base(url, init);
  });
  const processing = vi.fn();
  const handle = uploadDirect(
    new File(["abcdef"], "a.txt"),
    { onProcessingProgress: processing },
    fallback,
  );
  (await nextPart(0)).finish();
  (await nextPart(1)).finish();
  await vi.waitFor(() => expect(processing).toHaveBeenCalledWith(45));
  finish(json(completed));
  await handle.promise;
  const calls = auth.mock.calls.length;
  await new Promise((resolve) => setTimeout(resolve, 600));
  expect(auth.mock.calls).toHaveLength(calls);
});

test("cancel during server processing aborts completion and progress polling", async () => {
  let statusSignal: AbortSignal | null | undefined;
  const base = auth.getMockImplementation()!;
  auth.mockImplementation((url: string, init: RequestInit) => {
    if (url.endsWith("/complete"))
      return new Promise<Response>((_resolve, reject) => {
        init.signal!.addEventListener(
          "abort",
          () => reject(new DOMException("Canceled", "AbortError")),
          { once: true },
        );
      });
    if (init.method === "GET") {
      statusSignal = init.signal;
      return Promise.resolve(json({ state: "completing", progress: 40 }));
    }
    return base(url, init);
  });
  const processing = vi.fn();
  const handle = uploadDirect(
    new File(["abcdef"], "a.txt"),
    { onProcessingProgress: processing },
    fallback,
  );
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  (await nextPart(0)).finish();
  (await nextPart(1)).finish();
  await vi.waitFor(() => expect(processing).toHaveBeenCalledWith(40));
  handle.abort();
  await rejected;
  expect(statusSignal?.aborted).toBe(true);
});

test("a failed progress request does not fail successful completion", async () => {
  let finish!: (response: Response) => void;
  const base = auth.getMockImplementation()!;
  auth.mockImplementation((url: string, init: RequestInit) => {
    if (url.endsWith("/complete"))
      return new Promise<Response>((resolve) => {
        finish = resolve;
      });
    if (init.method === "GET") return Promise.resolve(json({}, 503));
    return base(url, init);
  });
  const handle = uploadDirect(
    new File(["abcdef"], "a.txt"),
    { onProcessingProgress: vi.fn() },
    fallback,
  );
  (await nextPart(0)).finish();
  (await nextPart(1)).finish();
  await vi.waitFor(() =>
    expect(auth.mock.calls.some(([, init]) => init.method === "GET")).toBe(
      true,
    ),
  );
  finish(json(completed));
  expect((await handle.promise).key).toBe(completed.key);
});

async function nextPart(index: number) {
  await vi.waitFor(() => expect(FakeXHR.sent.length).toBeGreaterThan(index));
  return FakeXHR.sent[index];
}

test("uploads sliced blobs directly and reports aggregate bytes before final confirmation", async () => {
  const progress = vi.fn();
  const handle = uploadDirect(
    new File(["abcdef"], "a.txt"),
    { onProgress: progress },
    fallback,
  );
  const first = await nextPart(0);
  expect(first.method).toBe("PUT");
  expect(first.url).toBe("https://storage.example/scoped-part");
  expect(first.body?.size).toBe(4);
  first.progress(2);
  expect(progress).toHaveBeenLastCalledWith(33, 2, 6);
  first.finish();
  const second = await nextPart(1);
  expect(second.body?.size).toBe(2);
  second.progress(1);
  expect(progress).toHaveBeenLastCalledWith(83, 5, 6);
  second.finish();
  expect(await handle.promise).toEqual({
    key: completed.key,
    url: completed.url,
    name: completed.name,
    type: completed.type,
    mimeType: "text/plain",
    size: 6,
  });
  expect(progress).toHaveBeenLastCalledWith(100, 6, 6);
  expect(fallback).not.toHaveBeenCalled();
  expect(auth.mock.calls.some(([url]) => url.endsWith("/complete"))).toBe(true);
});

test("retries only a failed part using a fresh signature", async () => {
  const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
  (await nextPart(0)).finish();
  (await nextPart(1)).finish(503);
  const retried = await nextPart(2);
  expect(retried.body?.size).toBe(2);
  retried.finish();
  await handle.promise;
  expect(
    auth.mock.calls.filter(([url]) => url.endsWith("/parts/1")),
  ).toHaveLength(1);
  expect(
    auth.mock.calls.filter(([url]) => url.endsWith("/parts/2")),
  ).toHaveLength(2);
});

test("cancel aborts the current PUT and requests provider cleanup without completion", async () => {
  const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  await nextPart(0);
  handle.abort();
  await rejected;
  expect(
    auth.mock.calls.some(
      ([url, init]) => url.endsWith("/ticket") && init.method === "DELETE",
    ),
  ).toBe(true);
  expect(auth.mock.calls.some(([url]) => url.endsWith("/complete"))).toBe(
    false,
  );
});

test("cancel during initialization cleans up the ticket as soon as its ID arrives", async () => {
  let finish!: (response: Response) => void;
  auth.mockImplementationOnce(
    () =>
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
  );
  const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  handle.abort();
  finish(json({ mode: "direct", id: "ticket", part_size: 4, part_count: 2 }));
  await rejected;
  expect(FakeXHR.sent).toHaveLength(0);
  expect(auth.mock.calls.some(([, init]) => init.method === "DELETE")).toBe(
    true,
  );
});

test("local storage and image-transcode responses use the existing cancellable uploader", async () => {
  auth.mockResolvedValueOnce(json({ mode: "proxy" }));
  const proxyAbort = vi.fn();
  let finish!: (value: typeof completed) => void;
  fallback.mockReturnValue({
    promise: new Promise((resolve) => {
      finish = resolve;
    }),
    abort: proxyAbort,
  });
  const handle = uploadDirect(new File(["abcdef"], "a.tiff"), {}, fallback);
  await vi.waitFor(() => expect(fallback).toHaveBeenCalledOnce());
  handle.abort();
  expect(proxyAbort).toHaveBeenCalledOnce();
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  finish(completed);
  await rejected;
  expect(FakeXHR.sent).toHaveLength(0);
});

test("a permanent part failure cleans up and never registers the file", async () => {
  const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
  const rejected = expect(handle.promise).rejects.toThrow(
    "fileUpload.uploadFailed",
  );
  (await nextPart(0)).finish(400);
  await rejected;
  expect(FakeXHR.sent).toHaveLength(1);
  expect(auth.mock.calls.some(([, init]) => init.method === "DELETE")).toBe(
    true,
  );
});

test.each([404, 405])(
  "a client connected to an older server (%s) retains backend uploads",
  async (status) => {
    auth.mockResolvedValueOnce(json({ detail: "Not Found" }, status));
    fallback.mockReturnValue({
      promise: Promise.resolve(completed),
      abort: vi.fn(),
    });
    const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
    expect(await handle.promise).toEqual(completed);
    expect(fallback).toHaveBeenCalledOnce();
  },
);

test.each([401, 403, 503])(
  "an authorization or service error (%s) never starts an anonymous proxy fallback",
  async (status) => {
    auth.mockResolvedValueOnce(json({ detail: "Request rejected" }, status));
    const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
    await expect(handle.promise).rejects.toMatchObject({ status });
    expect(fallback).not.toHaveBeenCalled();
  },
);

test("older WebViews retain uploads without AbortSignal.timeout", async () => {
  vi.stubGlobal("AbortSignal", {});
  auth.mockResolvedValueOnce(json({ mode: "proxy" }));
  fallback.mockReturnValue({
    promise: Promise.resolve(completed),
    abort: vi.fn(),
  });
  expect(
    await uploadDirect(new File(["abcdef"], "a.tiff"), {}, fallback).promise,
  ).toEqual(completed);
});

test("an unreachable bucket cleans multipart state before falling back to the authenticated backend", async () => {
  fallback.mockReturnValue({
    promise: Promise.resolve(completed),
    abort: vi.fn(),
  });
  const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
  for (let attempt = 0; attempt < 3; attempt++) {
    (await nextPart(attempt)).dispatchEvent(new Event("error"));
  }
  expect(await handle.promise).toEqual(completed);
  expect(fallback).toHaveBeenCalledOnce();
  const cleanupIndex = auth.mock.calls.findIndex(
    ([, init]) => init.method === "DELETE",
  );
  expect(cleanupIndex).toBeGreaterThan(-1);
  expect(fallback.mock.invocationCallOrder[0]).toBeGreaterThan(
    auth.mock.invocationCallOrder[cleanupIndex],
  );
});

test("cancel also aborts the backend fallback after a bucket network failure", async () => {
  let rejectProxy!: (error: Error) => void;
  const abort = vi.fn(() => rejectProxy(new Error("Upload was aborted")));
  fallback.mockReturnValue({
    promise: new Promise((_resolve, reject) => {
      rejectProxy = reject;
    }),
    abort,
  });
  const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
  const rejected = expect(handle.promise).rejects.toMatchObject({
    name: "AbortError",
  });
  for (let attempt = 0; attempt < 3; attempt++)
    (await nextPart(attempt)).dispatchEvent(new Event("error"));
  await vi.waitFor(() => expect(fallback).toHaveBeenCalledOnce());
  handle.abort();
  await rejected;
  expect(abort).toHaveBeenCalledOnce();
});

test("a bucket authorization rejection remains visible instead of switching transports", async () => {
  const handle = uploadDirect(new File(["abcdef"], "a.txt"), {}, fallback);
  const rejected = expect(handle.promise).rejects.toMatchObject({
    status: 403,
  });
  for (let attempt = 0; attempt < 3; attempt++)
    (await nextPart(attempt)).finish(403);
  await rejected;
  expect(fallback).not.toHaveBeenCalled();
});
