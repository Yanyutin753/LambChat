import { resolveMCPServerFormSystemMode } from "../mcpServerEditor.ts";

test("uses the pending server type when editing an MCP server", () => {
  expect(
    resolveMCPServerFormSystemMode({
      isCreating: false,
      createAsSystem: false,
      changeToSystem: true,
    }),
  ).toBe(true);

  expect(
    resolveMCPServerFormSystemMode({
      isCreating: false,
      createAsSystem: false,
      changeToSystem: false,
    }),
  ).toBe(false);
});

test("uses create-as-system only while creating an MCP server", () => {
  expect(
    resolveMCPServerFormSystemMode({
      isCreating: true,
      createAsSystem: true,
      changeToSystem: false,
    }),
  ).toBe(true);
});
