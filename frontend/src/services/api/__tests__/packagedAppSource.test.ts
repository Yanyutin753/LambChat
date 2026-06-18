import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("revealed file API uses the configured API base", () => {
  const source = readSource("../revealedFile.ts");

  assert.match(source, /import \{ API_BASE/);
  assert.doesNotMatch(source, /authFetch<[^>]+>\("\/api\/files/);
  assert.doesNotMatch(source, /authFetch<[^>]+>\(\s*`\/api\/files/);
});

test("WebSocket notifications use the configured backend base", () => {
  const source = readSource("../../../hooks/useWebSocket.ts");

  assert.match(source, /buildWebSocketUrl/);
  assert.doesNotMatch(source, /window\.location\.host/);
  assert.doesNotMatch(source, /`\$\{protocol\}\/\/\$\{host\}\/ws`/);
});

test("hooks with backend requests do not hardcode same-origin API roots", () => {
  const useAgent = readSource("../../../hooks/useAgent.ts");
  const useMcp = readSource("../../../hooks/useMcp.ts");
  const useTools = readSource("../../../hooks/useTools.ts");
  const useApprovals = readSource("../../../hooks/useApprovals.ts");
  const profileTools = readSource(
    "../../../components/profile/tabs/ProfileToolsTab.tsx",
  );

  assert.match(useAgent, /from "\.\.\/services\/api\/config"/);
  assert.match(useMcp, /import \{ API_BASE/);
  assert.match(useTools, /import \{ API_BASE/);
  assert.match(useApprovals, /import \{ API_BASE/);
  assert.match(profileTools, /import \{ API_BASE/);
  assert.doesNotMatch(useAgent, /API_BASE,\n\s+type UseAgentOptions/);
  assert.doesNotMatch(useMcp, /const API_BASE = "\/api/);
  assert.doesNotMatch(useTools, /const API_BASE = "\/api/);
  assert.doesNotMatch(useApprovals, /const API_BASE =/);
  assert.doesNotMatch(profileTools, /const API_BASE = "\/api/);
  assert.doesNotMatch(useMcp, /"\s*\/api\/admin\/mcp/);
  assert.doesNotMatch(useTools, /"\s*\/api/);
  assert.doesNotMatch(useApprovals, /"\s*\/human/);
  assert.doesNotMatch(profileTools, /"\s*\/api/);
});

test("streaming SSE uses the configured backend base in packaged apps", () => {
  const source = readSource("../../../hooks/useAgent/sseConnection.ts");

  assert.match(source, /import \{ buildApiUrl \}/);
  assert.match(
    source,
    /buildApiUrl\(\s*`\/api\/chat\/sessions\/\$\{targetSessionId\}\/stream/,
  );
  assert.doesNotMatch(source, /fetchEventSource\(\s*`\/api\/chat\/sessions/);
});

test("upload attachment fallback URLs use the configured backend base", () => {
  const source = readSource("../../../hooks/useFileUpload.ts");

  assert.match(source, /import \{ buildApiUrl \}/);
  assert.match(source, /url:\s*buildApiUrl\(c\.url \|\| `\/api\/upload\/file/);
  assert.match(source, /url:\s*buildApiUrl\(result\.url\)/);
  assert.doesNotMatch(source, /url:\s*c\.url \|\| `\/api\/upload\/file/);
});

test("signed upload URLs are resolved for packaged app document fetches", () => {
  const source = readSource("../upload.ts");

  assert.match(source, /import \{[^}]*getFullUrl[^}]*\} from "\.\/config"/);
  assert.match(source, /return getFullUrl\(result\.url\) \|\| result\.url/);
  assert.match(
    source,
    /url:\s*item\.url \? getFullUrl\(item\.url\) \|\| item\.url : item\.url/,
  );
});

test("attachment previews resolve backend-relative image URLs", () => {
  const attachmentPreview = readSource(
    "../../../components/chat/AttachmentPreview.tsx",
  );
  const attachmentCard = readSource(
    "../../../components/common/AttachmentCard.tsx",
  );

  assert.match(attachmentPreview, /getFullUrl\(attachment\.url\)/);
  assert.match(attachmentCard, /getFullUrl\(attachment\.url\)/);
  assert.doesNotMatch(attachmentPreview, /src=\{attachment\.url\}/);
  assert.doesNotMatch(attachmentCard, /src=\{attachment\.url\}/);
});

test("backend-provided avatar URLs are resolved before image rendering", () => {
  const files = [
    "../../../components/layout/UserMenu.tsx",
    "../../../components/profile/tabs/ProfileInfoTab.tsx",
    "../../../components/panels/UsersPanel.tsx",
    "../../../components/panels/SidebarParts/SessionListContent.tsx",
    "../../../components/panels/SidebarParts/SidebarRail.tsx",
    "../../../components/share/SharedPage.tsx",
    "../../../components/layout/AppContent/MessageOutlinePanel.tsx",
    "../../../components/persona/PersonaAvatarIcon.tsx",
    "../../../components/chat/ChatMessage/AssistantAvatar.tsx",
    "../../../components/chat/ChatMessage/SubagentBlocks.tsx",
  ];

  for (const file of files) {
    const source = readSource(file);
    assert.match(source, /getFullUrl\(/, file);
  }
});

test("approval polling requests use the configured backend base", () => {
  const historyLoader = readSource("../../../hooks/useAgent/historyLoader.ts");
  const eventHandlers = readSource("../../../hooks/useAgent/eventHandlers.ts");
  const approvalPanel = readSource(
    "../../../components/panels/ApprovalPanel.tsx",
  );

  for (const source of [historyLoader, eventHandlers, approvalPanel]) {
    assert.match(source, /import \{ buildApiUrl \}/);
    assert.doesNotMatch(source, /authFetch<[^>]+>\(\s*`\/human\//);
  }
});

test("API modules share the normalized API base configuration", () => {
  const feedback = readSource("../../../plugins/feedback/api.ts");
  const feedbackCompatibility = readSource("../feedback.ts");
  const notification = readSource("../notification.ts");

  assert.match(
    feedback,
    /import \{ API_BASE \} from "\.\.\/\.\.\/services\/api\/config"/,
  );
  assert.match(
    feedbackCompatibility,
    /export \{ feedbackApi \} from "\.\.\/\.\.\/plugins\/feedback\/api"/,
  );
  assert.match(notification, /import \{ API_BASE \} from "\.\/config"/);
  assert.doesNotMatch(feedback, /import\.meta\.env\.VITE_API_BASE/);
  assert.doesNotMatch(notification, /import\.meta\.env\.VITE_API_BASE/);
});
