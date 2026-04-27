import assert from "node:assert/strict";
import test from "node:test";
import {
  closeBlockPreview,
  getBlockPreview,
  openBlockPreview,
  subscribeBlockPreview,
} from "./blockPreviewStore.ts";

test("opening a preview updates the current block preview", () => {
  closeBlockPreview();

  openBlockPreview({
    type: "text",
    text: "hello",
  });

  assert.deepEqual(getBlockPreview(), {
    type: "text",
    text: "hello",
  });

  closeBlockPreview();
});

test("reopening the same preview payload does not notify listeners twice", () => {
  closeBlockPreview();
  const calls: number[] = [];
  const unsubscribe = subscribeBlockPreview(() => {
    calls.push(calls.length + 1);
  });

  openBlockPreview({
    type: "file",
    url: "https://example.com/file.txt",
    fileName: "file.txt",
  });
  openBlockPreview({
    type: "file",
    url: "https://example.com/file.txt",
    fileName: "file.txt",
  });

  assert.equal(calls.length, 1);

  unsubscribe();
  closeBlockPreview();
});
