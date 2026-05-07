import assert from "node:assert/strict";
import test from "node:test";
import {
  prepareFullscreenMermaidSvg,
  stripResponsiveWidthAttribute,
} from "../mermaidSvgUtils.ts";

test('stripResponsiveWidthAttribute removes Mermaid root width="100%"', () => {
  const svg =
    '<svg width="100%" viewBox="0 0 120 80"><rect width="120" height="80" /></svg>';

  assert.equal(
    stripResponsiveWidthAttribute(svg),
    '<svg viewBox="0 0 120 80"><rect width="120" height="80" /></svg>',
  );
});

test("prepareFullscreenMermaidSvg preserves existing styles and adds visibility fallbacks", () => {
  const svg =
    '<svg viewBox="0 0 120 80" style="max-width: 120px; background-color: transparent;"><rect width="120" height="80" /></svg>';

  const prepared = prepareFullscreenMermaidSvg(svg);

  assert.match(
    prepared,
    /style="max-width: 120px; background-color: transparent; display: block; width: auto; height: auto; min-width: 200px; min-height: 100px; max-height: 85vh;"/,
  );
});

test("prepareFullscreenMermaidSvg injects a style attribute when the svg has none", () => {
  const svg =
    '<svg viewBox="0 0 120 80"><rect width="120" height="80" /></svg>';

  const prepared = prepareFullscreenMermaidSvg(svg);

  assert.match(
    prepared,
    /<svg viewBox="0 0 120 80" style="display: block; width: auto; height: auto; min-width: 200px; min-height: 100px; max-height: 85vh;">/,
  );
});

test("prepareFullscreenMermaidSvg normalizes HTML line breaks for XML image parsing", () => {
  const svg =
    '<svg viewBox="0 0 120 80"><foreignObject><div><p>line 1<br>line 2</p></div></foreignObject></svg>';

  const prepared = prepareFullscreenMermaidSvg(svg);

  assert.match(prepared, /<br \/>/);
  assert.doesNotMatch(prepared, /<br>(?!<\/br>)/);
});
