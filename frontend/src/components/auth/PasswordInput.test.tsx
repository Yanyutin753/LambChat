import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { PasswordInput } from "./PasswordInput.tsx";

test("password visibility toggle is keyboard focusable and localizable", () => {
  const markup = renderToStaticMarkup(
    <PasswordInput
      value=""
      onChange={() => undefined}
      showPasswordLabel="显示密码"
      hidePasswordLabel="隐藏密码"
    />,
  );

  assert.match(markup, /aria-label="显示密码"/);
  assert.doesNotMatch(markup, /tabindex="-1"/i);
});
