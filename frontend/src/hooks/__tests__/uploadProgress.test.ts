import { afterEach, expect, test, vi } from "vitest";
import {
  createUploadProgressController,
  type UploadProgressUpdate,
} from "../uploadProgress";

afterEach(() => {
  vi.useRealTimers();
});

test("coalesces repeated and high-frequency upload progress", () => {
  vi.useFakeTimers();
  const updates: UploadProgressUpdate[] = [];
  const controller = createUploadProgressController(
    (update) => updates.push(update),
    100,
  );

  controller.report(10);
  controller.report(10);
  controller.report(11);
  controller.report(12);

  expect(updates).toEqual([{ progress: 10, stage: "uploading" }]);
  vi.advanceTimersByTime(100);
  expect(updates).toEqual([
    { progress: 10, stage: "uploading" },
    { progress: 12, stage: "uploading" },
  ]);
});

test("switches to processing immediately instead of emitting 100 percent", () => {
  vi.useFakeTimers();
  const updates: UploadProgressUpdate[] = [];
  const controller = createUploadProgressController((update) =>
    updates.push(update),
  );

  controller.report(50);
  controller.report(75);
  controller.report(100);

  expect(updates).toEqual([
    { progress: 50, stage: "uploading" },
    { progress: 99, stage: "processing" },
  ]);
  vi.advanceTimersByTime(100);
  expect(updates).toHaveLength(2);
});

test("dispose drops a pending trailing update", () => {
  vi.useFakeTimers();
  const updates: UploadProgressUpdate[] = [];
  const controller = createUploadProgressController((update) =>
    updates.push(update),
  );

  controller.report(20);
  controller.report(30);
  controller.dispose();
  vi.advanceTimersByTime(100);

  expect(updates).toEqual([{ progress: 20, stage: "uploading" }]);
});
