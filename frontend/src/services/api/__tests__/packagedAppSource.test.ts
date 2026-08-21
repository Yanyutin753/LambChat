import { readFileSync } from "node:fs";

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("revealed file API uses the configured API base", () => {
  const source = readSource("../revealedFile.ts");

  expect(source).toMatch(/import \{ API_BASE/);
  expect(source).not.toMatch(/authFetch<[^>]+>\("\/api\/files/);
  expect(source).not.toMatch(/authFetch<[^>]+>\(\s*`\/api\/files/);
});

test("WebSocket notifications use the configured backend base", () => {
  const source = readSource("../../../hooks/useWebSocket.ts");

  expect(source).toMatch(/buildWebSocketUrl/);
  expect(source).not.toMatch(/window\.location\.host/);
  expect(source).not.toMatch(/`\$\{protocol\}\/\/\$\{host\}\/ws`/);
});

test("hooks with backend requests do not hardcode same-origin API roots", () => {
  const useAgent = readSource("../../../hooks/useAgent.ts");
  const useMcp = readSource("../../../hooks/useMcp.ts");
  const useTools = readSource("../../../hooks/useTools.ts");
  const useApprovals = readSource("../../../hooks/useApprovals.ts");
  const profileTools = readSource(
    "../../../components/profile/tabs/ProfileToolsTab.tsx",
  );

  expect(useAgent).toMatch(/from "\.\.\/services\/api\/config"|useAgentList/);
  const agentList = readSource("../../../hooks/useAgent/agentList.ts");
  expect(agentList).toMatch(/from "\.\.\/\.\.\/services\/api\/config"/);
  expect(useMcp).toMatch(/import \{ API_BASE/);
  expect(useTools).toMatch(/import \{ API_BASE/);
  expect(useApprovals).toMatch(/import \{ API_BASE/);
  expect(profileTools).toMatch(/import \{ API_BASE/);
  expect(useAgent).not.toMatch(/API_BASE,\n\s+type UseAgentOptions/);
  expect(useMcp).not.toMatch(/const API_BASE = "\/api/);
  expect(useTools).not.toMatch(/const API_BASE = "\/api/);
  expect(useApprovals).not.toMatch(/const API_BASE =/);
  expect(profileTools).not.toMatch(/const API_BASE = "\/api/);
  expect(useMcp).not.toMatch(/"\s*\/api\/admin\/mcp/);
  expect(useTools).not.toMatch(/"\s*\/api/);
  expect(useApprovals).not.toMatch(/"\s*\/human/);
  expect(profileTools).not.toMatch(/"\s*\/api/);
});

test("streaming SSE uses the configured backend base in packaged apps", () => {
  const source = readSource("../../../hooks/useAgent/sseConnection.ts");

  expect(source).toMatch(/import \{ buildApiUrl \}/);
  expect(source).toMatch(
    /buildApiUrl\(\s*`\/api\/chat\/sessions\/\$\{targetSessionId\}\/stream/,
  );
  expect(source).not.toMatch(/fetchEventSource\(\s*`\/api\/chat\/sessions/);
});

test("upload attachment fallback URLs use the configured backend base", () => {
  const source = readSource("../../../hooks/useFileUpload.ts");

  expect(source).toMatch(/import \{ buildApiUrl \}/);
  expect(source).toMatch(
    /url:\s*buildApiUrl\(\s*check\.url\s*\|\|\s*`\/api\/upload\/file/,
  );
  expect(source).toMatch(/url:\s*buildApiUrl\(result\.url\)/);
  expect(source).not.toMatch(/url:\s*check\.url\s*\|\|/);
});

test("signed upload URLs are resolved for packaged app document fetches", () => {
  const source = readSource("../upload.ts");

  expect(source).toMatch(/import \{[^}]*getFullUrl[^}]*\} from "\.\/config"/);
  expect(source).toMatch(/return getFullUrl\(result\.url\) \|\| result\.url/);
  expect(source).toMatch(
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

  expect(attachmentPreview).toMatch(/getFullUrl\(attachment\.url\)/);
  expect(attachmentCard).toMatch(/getFullUrl\(attachment\.url\)/);
  expect(attachmentPreview).not.toMatch(/src=\{attachment\.url\}/);
  expect(attachmentCard).not.toMatch(/src=\{attachment\.url\}/);
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
    "../../../components/chat/ChatMessage/subagentRoleMeta.ts",
  ];

  for (const file of files) {
    const source = readSource(file);
    expect(source).toMatch(/getFullUrl\(/);
  }
});

test("approval polling requests use the configured backend base", () => {
  const historyLoader = readSource("../../../hooks/useAgent/historyLoader.ts");
  const eventHandlers = readSource("../../../hooks/useAgent/eventHandlers.ts");
  const approvalPanel = readSource(
    "../../../components/panels/ApprovalPanel.tsx",
  );

  for (const source of [historyLoader, approvalPanel]) {
    expect(source).toMatch(/import \{ buildApiUrl \}/);
    expect(source).not.toMatch(/authFetch<[^>]+>\(\s*`\/human\//);
  }
  expect(eventHandlers).not.toMatch(/authFetch<[^>]+>\(\s*`\/human\//);
});

test("API modules share the normalized API base configuration", () => {
  const feedback = readSource("../feedback.ts");
  const notification = readSource("../notification.ts");

  expect(feedback).toMatch(/import \{ API_BASE \} from "\.\/config"/);
  expect(notification).toMatch(/import \{ API_BASE \} from "\.\/config"/);
  expect(feedback).not.toMatch(/import\.meta\.env\.VITE_API_BASE/);
  expect(notification).not.toMatch(/import\.meta\.env\.VITE_API_BASE/);
});
