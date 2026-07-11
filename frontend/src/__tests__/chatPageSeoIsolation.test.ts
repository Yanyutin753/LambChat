import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(__dirname, "../App.tsx"), "utf8");

function extractFunctionBody(name: string): string {
  const start = appSource.indexOf(`function ${name}(`);
  expect(start).not.toBe(-1);

  const signatureEnd = appSource.indexOf(") {", start);
  expect(signatureEnd).not.toBe(-1);

  const firstBrace = appSource.indexOf("{", signatureEnd);
  expect(firstBrace).not.toBe(-1);

  let depth = 0;
  for (let index = firstBrace; index < appSource.length; index += 1) {
    const char = appSource[index];
    if (char === "{") depth += 1;
    if (char === "}") depth -= 1;
    if (depth === 0) {
      return appSource.slice(firstBrace + 1, index);
    }
  }

  throw new Error(`${name} body is unterminated`);
}

test("keeps chat page title updates isolated from the chat UI tree", () => {
  const chatPageBody = extractFunctionBody("ChatPage");

  expect(appSource).toMatch(/function ChatPageSEO\(/);
  expect(chatPageBody).toMatch(/<ChatPageSEO \/>/);
  expect(chatPageBody).toMatch(
    /<AppContent key="chat" activeTab="chat" runtimePlugins=\{runtimePlugins\} \/>/,
  );
  expect(chatPageBody).not.toMatch(/useState<.*sessionName|setSessionName/);
  expect(chatPageBody).not.toMatch(/listenSessionTitleUpdated|sessionApi\.get/);
});
