/** @vitest-environment jsdom */
import { renderToStaticMarkup } from "react-dom/server";
import { PasswordInput } from "../PasswordInput.tsx";

test("password visibility toggle is keyboard focusable and localizable", () => {
  const markup = renderToStaticMarkup(
    <PasswordInput
      value=""
      onChange={() => undefined}
      showPasswordLabel="显示密码"
      hidePasswordLabel="隐藏密码"
    />,
  );

  expect(markup).toMatch(/aria-label="显示密码"/);
  expect(markup).not.toMatch(/tabindex="-1"/i);
});
