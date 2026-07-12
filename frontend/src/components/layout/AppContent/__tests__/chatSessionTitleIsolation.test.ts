import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, "..", relativePath), "utf8");
}

function extractFunctionBody(source: string, name: string): string {
  const start = source.indexOf(`function ${name}(`);
  expect(start).not.toBe(-1);

  const firstBrace = source.indexOf("{", start);
  expect(firstBrace).not.toBe(-1);

  let depth = 0;
  for (let index = firstBrace; index < source.length; index += 1) {
    const char = source[index];
    if (char === "{") depth += 1;
    if (char === "}") depth -= 1;
    if (depth === 0) {
      return source.slice(firstBrace + 1, index);
    }
  }

  throw new Error(`${name} body is unterminated`);
}

test("keeps generated session title updates out of the chat message tree", () => {
  const chatAppSource = readSource("ChatAppContent.tsx");
  const chatViewSource = readSource("ChatView.tsx");
  const chatMessageSource = readSource("../../chat/ChatMessage/index.tsx");
  const appShellSource = readSource("AppShell.tsx");

  const chatAppBody = extractFunctionBody(chatAppSource, "ChatAppContent");
  const chatViewBody = extractFunctionBody(chatViewSource, "ChatView");

  expect(chatAppBody).not.toMatch(/setSessionName|useState<.*sessionName/);
  expect(chatAppBody).not.toMatch(/onStreamDone:\s*\(\)\s*=>\s*\{/);
  expect(chatViewSource).not.toMatch(/sessionName:/);
  expect(chatViewBody).not.toMatch(/sessionName=/);
  expect(chatMessageSource).not.toMatch(/sessionName\?:|sessionName=/);
  expect(appShellSource).not.toMatch(/sessionName\?:|sessionName=/);
});
