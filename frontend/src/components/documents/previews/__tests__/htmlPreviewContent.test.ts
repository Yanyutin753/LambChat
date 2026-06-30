import assert from "node:assert/strict";
import test from "node:test";

import { prepareHtmlPreviewContent } from "../htmlPreviewContent.ts";

test("injects an inert base URL into srcdoc HTML previews", () => {
  const html = prepareHtmlPreviewContent(
    '<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body><script src="main.js"></script></body></html>',
  );

  assert.match(html, /<head><base href="about:srcdoc" \/>/);
});

test("does not inject a duplicate base URL into srcdoc HTML previews", () => {
  const html = prepareHtmlPreviewContent(
    '<!doctype html><html><head><base href="https://example.com/"><title>Preview</title></head><body></body></html>',
  );

  assert.equal(html.match(/<base\b/gi)?.length, 1);
  assert.match(html, /<base href="https:\/\/example\.com\/">/);
});
