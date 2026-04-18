import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DynamicIcon } from "./DynamicIcon";

test("emoji icons render inside a fixed-size box with a tight line height", () => {
  const markup = renderToStaticMarkup(
    React.createElement(DynamicIcon, {
      name: "📁",
      size: 18,
      className: "text-stone-500",
    }),
  );

  assert.match(markup, /width:18px/);
  assert.match(markup, /height:18px/);
  assert.match(markup, /font-size:18px/);
  assert.match(markup, /line-height:1/);
});
