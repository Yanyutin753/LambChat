/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { MarkdownContent } from "../MarkdownContent";

afterEach(cleanup);

test.each([
  "一个月 81~108 块，一年 985~1314 块。",
  "108~144 度，×0.75 就是 81~108 元/月。",
  "日常 150~200W，能往 130~150W 靠。",
  "一个月 81～108 块，一年 985～1314 块。",
  "~普通文本~",
])("Markdown preserves literal tildes in %s", (content) => {
  const { container } = render(<MarkdownContent content={content} />);
  expect(container.querySelector("del")).toBeNull();
  expect(container).toHaveTextContent(content);
});

test("Markdown keeps double-tilde strikethrough next to Chinese text", () => {
  const { container } = render(
    <MarkdownContent content="原价~~（已作废）~~，现价 81~108 元，功耗 130~150W。" />,
  );
  expect(container.querySelectorAll("del")).toHaveLength(1);
  expect(container.querySelector("del")).toHaveTextContent("（已作废）");
  expect(container).toHaveTextContent("现价 81~108 元，功耗 130~150W。");
});

test("ordered Markdown lists preserve their starting number", () => {
  render(<MarkdownContent content={"3. Review the results\n4. Publish the report"} />);
  expect(screen.getByRole("list")).toHaveAttribute("start", "3");
});

test("Markdown tables preserve numeric column alignment", () => {
  render(
    <MarkdownContent
      content={"| Name | Size | Status |\n| :--- | ---: | :---: |\n| Cache | 3.3G | Ready |"}
    />,
  );
  expect(screen.getByRole("columnheader", { name: "Size" })).toHaveStyle({
    textAlign: "right",
  });
  expect(screen.getByRole("cell", { name: "3.3G" })).toHaveStyle({
    textAlign: "right",
  });
  expect(screen.getByRole("cell", { name: "Ready" })).toHaveStyle({
    textAlign: "center",
  });
});
