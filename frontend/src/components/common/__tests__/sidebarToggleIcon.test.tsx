import { renderToStaticMarkup } from "react-dom/server";
import { SidebarToggleIcon } from "../SidebarToggleIcon";

test("sidebar controls use the shared Lucide panel icon at every breakpoint", () => {
  const markup = renderToStaticMarkup(<SidebarToggleIcon />);
  expect(markup).toContain('fill="none"');
  expect(markup).toContain('stroke="currentColor"');
  expect(markup).toContain("data-interactive-icon");
  expect(markup).toContain('aria-hidden="true"');
  expect(markup).toMatch(/class="[^"]*\bsize-4\b/);
  expect(markup.match(/<svg/g)).toHaveLength(1);
  expect(markup).not.toContain("sm:");
});
