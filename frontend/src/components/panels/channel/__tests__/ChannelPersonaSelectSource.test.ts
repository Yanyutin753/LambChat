import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../ChannelPersonaSelect.tsx", import.meta.url),
  "utf8",
);

test("channel persona selector supports search-backed paginated loading", () => {
  expect(source).toMatch(/searchQuery/);
  expect(source).toMatch(/debouncedSearch/);
  expect(source).toMatch(/personaPresetApi\s*\.\s*list\(\{/);
  expect(source).toMatch(/q:\s*debouncedSearch\.trim\(\) \|\| undefined/);
  expect(source).toMatch(/skip:\s*nextSkip/);
  expect(source).toMatch(/limit:\s*PAGE_LIMIT/);
  expect(source).toMatch(/handleScroll/);
  expect(source).toMatch(/scrollHeight - scrollTop - clientHeight < 80/);
});

test("channel persona selector exposes a clear option", () => {
  expect(source).toMatch(/channel\.clearPersona/);
  expect(source).toMatch(/onChange\(null\)/);
});

test("channel persona selector renders preset icons in trigger and options", () => {
  expect(source).toMatch(/<AgentAvatar/);
  expect(source).toMatch(/seed=\{preset\.id \|\| preset\.name\}/);
  expect(source).toMatch(/selected && <PersonaPresetIcon preset=\{selected\}/);
  expect(source).toMatch(/<PersonaPresetIcon preset=\{preset\}/);
});
