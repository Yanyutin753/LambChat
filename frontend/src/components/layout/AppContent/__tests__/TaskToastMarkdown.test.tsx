/** @vitest-environment jsdom */
import { renderToStaticMarkup } from "react-dom/server";

import { TaskToastMarkdown } from "../TaskToastMarkdown.tsx";

test("renders inline markdown in task toast bodies", () => {
  const html = renderToStaticMarkup(
    <TaskToastMarkdown content="Finished **deploy** with `pnpm build` and [logs](https://example.com/logs)." />,
  );

  expect(html).toMatch(/<strong[^>]*>deploy<\/strong>/);
  expect(html).toMatch(/<code[^>]*>pnpm build<\/code>/);
  expect(html).toMatch(
    /<a[^>]*href="https:\/\/example.com\/logs"[^>]*>logs<\/a>/,
  );
});

test("keeps heavyweight markdown out of task toast bodies", () => {
  const html = renderToStaticMarkup(
    <TaskToastMarkdown
      content={
        '![graph](https://example.com/graph.png)\n\n```ts\nconsole.log("wide")\n```'
      }
    />,
  );

  expect(html).not.toMatch(/<img\b/);
  expect(html).not.toMatch(/<pre\b/);
});

test.each([
  [
    "Chinese asterisk strong emphasis",
    "提出到**锻炼人数达40%**左右",
    "strong",
    "锻炼人数达40%",
  ],
  [
    "Chinese punctuation-boundary strong emphasis",
    "这是**（重要）**内容",
    "strong",
    "（重要）",
  ],
  ["Japanese asterisk emphasis", "これは*（重要）*です", "em", "（重要）"],
  [
    "Korean punctuation-boundary emphasis",
    "이것은*강조.*입니다",
    "em",
    "강조.",
  ],
  [
    "Chinese strikethrough",
    "提出到~~锻炼人数达40%~~左右",
    "del",
    "锻炼人数达40%",
  ],
])("renders CJK-adjacent %s", (_name, markdown, tag, text) => {
  const html = renderToStaticMarkup(<TaskToastMarkdown content={markdown} />);

  expect(html).toContain(`<${tag}>${text}</${tag}>`);
});
