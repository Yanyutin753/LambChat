/** @vitest-environment jsdom */
import { renderToStaticMarkup } from "react-dom/server";
import { BrandWordmark } from "../BrandWordmark";

test("BrandWordmark renders an accessible scalable svg by default", () => {
  const html = renderToStaticMarkup(<BrandWordmark className="brand-mark" />);

  expect(html).toMatch(/<svg/);
  expect(html).toMatch(/viewBox="0 0 220 62"/);
  expect(html).toMatch(/role="img"/);
  expect(html).toMatch(/<title[^>]*>LambChat<\/title>/);
  expect(html).toMatch(/aria-labelledby="[^"]+"/);
  expect(html).toMatch(/class="brand-mark"/);
  expect(html).toMatch(/data-wordmark-style="text-only"/);
  expect(html).toMatch(/<text[^>]*>LambChat<\/text>/);
  expect(html).toMatch(/x="110"/);
  expect(html).toMatch(/y="36"/);
  expect(html).toMatch(/text-anchor="middle"/);
  expect(html).toMatch(/dominant-baseline="central"/);
  expect(html).not.toMatch(/<path/);
  expect(html).not.toMatch(/<circle/);
});

test("BrandWordmark can render decoratively when the parent already labels it", () => {
  const html = renderToStaticMarkup(<BrandWordmark decorative />);

  expect(html).toMatch(/aria-hidden="true"/);
  expect(html).not.toMatch(/role="img"/);
  expect(html).not.toMatch(/<title>/);
});
