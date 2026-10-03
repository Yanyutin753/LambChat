/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { MarkdownContent } from "../MarkdownContent";

afterEach(cleanup);

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
