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
  render(
    <MarkdownContent
      content={"3. Review the results\n4. Publish the report"}
    />,
  );
  expect(screen.getByRole("list")).toHaveAttribute("start", "3");
});

test("Markdown tables preserve numeric column alignment", () => {
  render(
    <MarkdownContent
      content={
        "| Name | Size | Status |\n| :--- | ---: | :---: |\n| Cache | 3.3G | Ready |"
      }
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

test("dollar prices in Chinese prose keep their text and Markdown emphasis", () => {
  const content = [
    "**这台（2GB Ryzen/i9，$19.99/年）本身价格确实便宜。** $20/年跑测试机可以。",
    "开盘价只到 **11/27 23:59 EST**，之后**每天涨 $1**，11/30 结束。",
    "要买的话趁今天（11/26）还是开盘价，**明天午夜 EST 起每天 +$1**；$49.99 那档到 11/30 会变 $52.99。",
  ].join("\n\n");
  const { container } = render(<MarkdownContent content={content} />);

  expect(container.querySelector(".katex")).toBeNull();
  expect(
    screen.getByText("这台（2GB Ryzen/i9，$19.99/年）本身价格确实便宜。")
      .tagName,
  ).toBe("STRONG");
  expect(screen.getByText("每天涨 $1").tagName).toBe("STRONG");
  expect(screen.getByText("明天午夜 EST 起每天 +$1").tagName).toBe("STRONG");
  expect(container).toHaveTextContent("；$49.99 那档到 11/30 会变 $52.99。");
});

test("dollar prices stay literal in headings, tables and lists", () => {
  const content = [
    "## $50/年可以买到 $49.99 的方案",
    "| 方案 | 价格 |",
    "| --- | --- |",
    "| 主机 | **$19.99**（原价 $24.99） |",
    "",
    "- 预算 $50，实付 **$47.98**",
  ].join("\n");
  const { container } = render(<MarkdownContent content={content} />);

  expect(container.querySelector(".katex")).toBeNull();
  expect(
    screen.getByRole("heading", { name: "$50/年可以买到 $49.99 的方案" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("cell", { name: "$19.99（原价 $24.99）" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("listitem")).toHaveTextContent(
    "预算 $50，实付 $47.98",
  );
});

test("Markdown retains inline and display math alongside dollar prices", () => {
  const content = [
    "价格 $19.99，公式 $x^2$，再付 $20。",
    "双美元行内公式 $$y+1$$ 和数字公式 $2+2$。",
    "",
    "$$",
    "z^3",
    "$$",
    "",
    "代码 `$19.99 $20`，转义 \\$30，链接 [账单](https://example.com/$40)。",
  ].join("\n");
  const { container } = render(<MarkdownContent content={content} />);

  expect(
    Array.from(
      container.querySelectorAll("annotation"),
      (node) => node.textContent,
    ),
  ).toEqual(["x^2", "y+1", "2+2", "z^3"]);
  expect(container.querySelector(".katex-display")).toBeInTheDocument();
  expect(container.querySelector("code")).toHaveTextContent("$19.99 $20");
  expect(container).toHaveTextContent("转义 $30");
  expect(screen.getByRole("link", { name: "账单" })).toHaveAttribute(
    "href",
    "https://example.com/$40",
  );
});

test("single-dollar math requires non-whitespace next to both delimiters", () => {
  const content = [
    "Text $ x$.",
    "Text $y $.",
    "The fee is $ and the formula is $x^2$.",
    "Prices range from $20,000 to $30,000.",
    "Double-dollar math keeps spaces: $$ y^2 $$.",
  ].join("\n\n");
  const { container } = render(<MarkdownContent content={content} />);
  expect(
    Array.from(
      container.querySelectorAll("annotation"),
      (node) => node.textContent,
    ),
  ).toEqual(["x^2", "y^2"]);
  expect(container).toHaveTextContent("Text $ x$.");
  expect(container).toHaveTextContent("Text $y $.");
  expect(container).toHaveTextContent("Prices range from $20,000 to $30,000.");
});
