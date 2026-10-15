import { renderToStaticMarkup } from "react-dom/server";
import { SidebarToggleIcon } from "../SidebarToggleIcon";

test("sidebar controls use the filled icon at every breakpoint", () => {
  const markup = renderToStaticMarkup(<SidebarToggleIcon />);
  expect(markup).toContain('fill="currentColor"');
  expect(markup).toContain('class="size-4"');
  expect(markup.match(/<svg/g)).toHaveLength(1);
  expect(markup).not.toContain("<rect");
  expect(markup).not.toContain("sm:");
});
