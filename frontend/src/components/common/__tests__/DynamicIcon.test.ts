/** @vitest-environment jsdom */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DynamicIcon } from "../DynamicIcon";

test("emoji icons render inside a fixed-size box via ImageWithSkeleton", () => {
  const markup = renderToStaticMarkup(
    React.createElement(DynamicIcon, {
      name: "💬",
      size: 18,
      className: "text-stone-500",
    }),
  );

  expect(markup).toMatch(/width:18px/);
  expect(markup).toMatch(/height:18px/);
  expect(markup).toMatch(/object-fit:contain/);
});
