/** @vitest-environment jsdom */
import { useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { vi } from "vitest";
import { JsonSchemaEditor } from "../JsonSchemaEditor";
import type { JsonSchema } from "../../../types/settings";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../common", async () => import("../../common/ui"));
afterEach(cleanup);
const schema: JsonSchema = {
  type: "object",
  value_type: "array",
  key_label: "Language",
  item_label: "Suggestion",
  key_options: ["en", "zh", "ja"],
  fields: [
    {
      name: "icon",
      type: "text",
      label: "Icon",
      required: true,
      layout_width: "compact",
    },
    {
      name: "text",
      type: "text",
      label: "Text",
      required: true,
      layout_width: "full",
    },
  ],
};
function Editor({ disabled = false }: { disabled?: boolean }) {
  const [value, setValue] = useState<object>({
    en: [{ icon: "A", text: "English draft" }],
    zh: [{ icon: "B", text: "中文草稿" }],
  });
  return (
    <JsonSchemaEditor
      schema={schema}
      value={value}
      disabled={disabled}
      onChange={setValue}
    />
  );
}

test("language switching shows one list and preserves unsaved edits", () => {
  render(<Editor />);
  expect(screen.queryByDisplayValue("中文草稿")).toBeNull();
  fireEvent.change(screen.getByRole("textbox", { name: "Text 1" }), {
    target: { value: "Edited draft" },
  });
  fireEvent.click(screen.getByRole("tab", { name: "zh" }));
  expect(screen.getByDisplayValue("中文草稿")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "en" }));
  expect(screen.getByDisplayValue("Edited draft")).toBeInTheDocument();
});

test("adding and deleting suggestions affects only the selected language", () => {
  render(<Editor />);
  fireEvent.click(screen.getByRole("tab", { name: "ja" }));
  expect(screen.getByText("settingDesc.JSON_SCHEMA_EMPTY")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /JSON_SCHEMA_ADD_ITEM/ }));
  fireEvent.change(screen.getByRole("textbox", { name: "Text 1" }), {
    target: { value: "New suggestion" },
  });
  fireEvent.click(screen.getByRole("button", { name: /common.delete/ }));
  expect(screen.queryByRole("textbox")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "en" }));
  expect(screen.getByDisplayValue("English draft")).toBeInTheDocument();
});

test("language tabs support arrow keys and focus follows selection", () => {
  render(<Editor />);
  const first = screen.getByRole("tab", { name: "en" });
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "zh" })).toHaveFocus();
  expect(screen.getByRole("tab", { name: "zh" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  fireEvent.keyDown(screen.getByRole("tab", { name: "zh" }), { key: "End" });
  expect(screen.getByRole("tab", { name: "ja" })).toHaveFocus();
});

test("read-only lists allow browsing languages without exposing mutations", () => {
  render(<Editor disabled />);
  fireEvent.click(screen.getByRole("tab", { name: "zh" }));
  expect(screen.getByDisplayValue("中文草稿")).toBeDisabled();
  expect(within(screen.getByRole("tabpanel")).queryByRole("button")).toBeNull();
});

test("plain array fields keep accessible controls after shared editor cleanup", () => {
  render(
    <JsonSchemaEditor
      schema={{ type: "array", fields: schema.fields }}
      value={[{ icon: "A", text: "A row" }]}
      disabled={false}
      onChange={() => {}}
    />,
  );
  expect(screen.getByRole("textbox", { name: "Text 1" })).toHaveValue("A row");
});

test("shared array rows retain typed defaults and independent field edits", () => {
  function TypedEditor() {
    const [value, setValue] = useState<object>([
      { secret: "key", count: 7, enabled: false },
    ]);
    return (
      <JsonSchemaEditor
        value={value}
        onChange={setValue}
        disabled={false}
        schema={{
          type: "array",
          fields: [
            { name: "secret", label: "Secret", type: "password" },
            { name: "count", label: "Count", type: "number" },
            { name: "enabled", label: "Enabled", type: "toggle" },
          ],
        }}
      />
    );
  }
  render(<TypedEditor />);
  fireEvent.click(screen.getByRole("switch", { name: "Enabled 1" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "Count 1" }), {
    target: { value: "12" },
  });
  fireEvent.click(screen.getByRole("button", { name: /JSON_SCHEMA_ADD_ITEM/ }));
  expect(screen.getByRole("switch", { name: "Enabled 1" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  expect(screen.getByRole("spinbutton", { name: "Count 1" })).toHaveValue(12);
  expect(screen.getByRole("spinbutton", { name: "Count 2" })).toHaveValue(0);
  expect(screen.getByRole("switch", { name: "Enabled 2" })).toHaveAttribute(
    "aria-checked",
    "false",
  );
  expect(screen.getByLabelText("Secret 2")).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("Secret 2")).toHaveValue("");
});
