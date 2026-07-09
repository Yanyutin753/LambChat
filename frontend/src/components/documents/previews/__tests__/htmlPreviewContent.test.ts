import { prepareHtmlPreviewContent } from "../htmlPreviewContent.ts";

test("injects an inert base URL into srcdoc HTML previews", () => {
  const html = prepareHtmlPreviewContent(
    '<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body><script src="main.js"></script></body></html>',
  );

  expect(html).toMatch(/<head><base href="about:srcdoc" \/>/);
});

test("does not inject a duplicate base URL into srcdoc HTML previews", () => {
  const html = prepareHtmlPreviewContent(
    '<!doctype html><html><head><base href="https://example.com/"><title>Preview</title></head><body></body></html>',
  );

  expect(html.match(/<base\b/gi)?.length).toBe(1);
  expect(html).toMatch(/<base href="https:\/\/example\.com\/">/);
});
