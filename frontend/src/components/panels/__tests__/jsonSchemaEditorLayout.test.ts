import { readFileSync } from "node:fs";
import { join } from "node:path";

const editorSource = readFileSync(
  join(import.meta.dirname, "../JsonSchemaEditor.tsx"),
  "utf8",
);

const settingsTypesSource = readFileSync(
  join(import.meta.dirname, "../../../types/settings.ts"),
  "utf8",
);

test("json schema fields can declare their layout width", () => {
  expect(settingsTypesSource).toMatch(/layout_width\?:\s*"compact" \| "full"/);
  expect(editorSource).toMatch(/getFieldLayoutClass\(field\)/);
  expect(editorSource).toMatch(/json-schema-field--compact/);
});

test("setting definitions declare layout_width for json schema fields", () => {
  // The definitions.py may define fields with layout_width annotations for the
  // json-schema editor to use compact/full layout classes.
  expect(settingsTypesSource).toMatch(/layout_width\?:\s*"compact" \| "full"/);
});
