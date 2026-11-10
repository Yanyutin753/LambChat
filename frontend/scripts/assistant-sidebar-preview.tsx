/** Local-only preview of real editor components; mutations stay in memory. */
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../src/hooks/useAuth";
import { SettingsProvider } from "../src/contexts/SettingsContext";
import { EditorSidebar } from "../src/components/common/EditorSidebar";
import { UsagePanel } from "../src/components/panels/UsagePanel";
import { MemoryPanel } from "../src/components/panels/MemoryPanel";
import { AssistantEditor } from "../src/components/assistants/AssistantEditor";
import { AssistantTasksDialog } from "../src/components/assistants/AssistantTasksDialog";
import { AssistantRulesDialog } from "../src/components/assistants/AssistantRulesDialog";
import { AssistantDiscussionsDialog } from "../src/components/assistants/AssistantDiscussionsDialog";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import i18n from "../src/i18n";
import { applyThemeToDocument, isTheme } from "../src/utils/themeDom";
import { AssistantGroupEditor } from "../src/components/assistants/AssistantGroupEditor";
import { assistantApi } from "../src/services/api/assistant";
import { assistantConfiguration, type Assistant } from "../src/types/assistant";
import { Button } from "../src/components/common/ui/Button";
import "../src/fonts.css";
import "../src/styles/tailwind.css";
import "../src/styles/tokens.css";
import "../src/styles/base.css";
import "../src/styles/components.css";
import "../src/styles/assistant-workspace.css";
import "../src/styles/animations.css";
import "../src/styles/panels.css";
import "../src/styles/glass.css";
import "../src/styles/card-base.css";
import "../src/styles/skill.css";
import "../src/styles/persona.css";
import "../src/styles/utilities.css";
void import("../src/fonts-cjk");
const params = new URLSearchParams(location.search);
const theme = params.get("theme");
applyThemeToDocument(isTheme(theme) ? theme : "light");
await i18n.changeLanguage(params.get("lang") || "zh");
const names = [
  "远航验收·排程师",
  "远航验收·审计员",
  "晨光验收·校对员",
  "晨光验收·资料员",
  "群聊验收·复核员",
  "Chief",
  "长期助手验收·持续研发与跨团队协作",
];
const members: Assistant[] = names.map((name, index) => ({
  ...assistantConfiguration(),
  name,
  id: `preview-${index}`,
  user_id: "preview",
  session_id: "preview",
  revision: 1,
  status: "active",
  created_at: "",
  updated_at: "",
}));
let group: Assistant = {
  ...members[0],
  id: "preview-group",
  name: "远航验收·交付室",
  kind: "group",
  instructions:
    "当前协调者是远航验收·排程师。在本群分析项目排程并独立复核，保留原始约束与核验依据。所有交付默认需要人工验收。",
  member_ids: [members[0].id, members[1].id],
  leader_id: members[0].id,
};
assistantApi.list = async (skip = 0, limit = 100) => ({
  assistants: members.slice(skip, skip + limit),
  total: members.length,
  skip,
  limit,
});
assistantApi.update = async (_id, draft) => {
  group = { ...group, ...draft, revision: group.revision + 1 };
  return group;
};
assistantApi.tasks = async () => ({ tasks: [], total: 0 });
assistantApi.rules = async () => ({ rules: [], total: 0 });
assistantApi.discussions = async () => ({
  discussions: [
    {
      session_id: "preview",
      channel_type: "telegram",
      chat_id: "跨部门项目协作与长期计划复盘",
      created_at: "2026-11-07T00:00:00Z",
      available: true,
    },
  ],
  total: 1,
});
export function Preview() {
  const mode = params.get("view") || "group";
  const [open, setOpen] = useState(true);
  const [saved, setSaved] = useState(false);
  return (
    <main
      className="p-6 text-theme-text space-y-5"
      style={{ maxWidth: "min(40rem, 55vw)" }}
    >
      <p className="text-12 text-theme-text-secondary">
        LambChat · 本地界面预览
      </p>
      <h1 className="text-24 font-semibold">远航验收 · 交付计划</h1>
      <p className="text-14 leading-relaxed text-theme-text-secondary">
        查看和调整群聊成员时，对话保留在左侧。此页使用真实群聊编辑组件，保存仅更新本页演示数据。
      </p>
      <nav className="flex flex-wrap gap-3">
        {[
          "group",
          "editor",
          "usage",
          "memory",
          "tasks",
          "rules",
          "discussions",
        ].map((view) => (
          <a key={view} href={`?view=${view}&theme=${theme || "light"}`}>
            {view}
          </a>
        ))}
      </nav>
      <Button
        onClick={() => {
          setSaved(false);
          setOpen(true);
        }}
      >
        群聊详情
      </Button>
      {saved && <p role="status">已保存本地演示，未修改真实群聊。</p>}
      {open && mode === "group" && (
        <AssistantGroupEditor
          value={group}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setOpen(false);
            setSaved(true);
          }}
        />
      )}
      {open && mode === "editor" && (
        <AssistantEditor
          value={members[0]}
          onClose={() => setOpen(false)}
          onSaved={() => setOpen(false)}
        />
      )}
      {open && mode === "tasks" && (
        <AssistantTasksDialog
          assistant={group}
          canWrite
          onClose={() => setOpen(false)}
        />
      )}
      {open && mode === "rules" && (
        <AssistantRulesDialog
          assistant={group}
          canWrite
          onClose={() => setOpen(false)}
        />
      )}
      {open && mode === "discussions" && (
        <AssistantDiscussionsDialog
          assistant={group}
          onClose={() => setOpen(false)}
        />
      )}
      {open && (mode === "usage" || mode === "memory") && (
        <EditorSidebar
          open
          title={i18n.t(`assistants.${mode}`)}
          onClose={() => setOpen(false)}
        >
          <div
            data-panel="assistant-data"
            className="flex h-full min-w-0 min-h-0 flex-col"
          >
            {mode === "usage" ? (
              <UsagePanel assistantId="preview-group" />
            ) : (
              <MemoryPanel assistantId="preview-group" />
            )}
          </div>
        </EditorSidebar>
      )}
    </main>
  );
}
const host = document.getElementById("root")! as HTMLElement & {
  previewRoot?: ReturnType<typeof createRoot>;
};
const root = (host.previewRoot ??= createRoot(host));
root.render(
  <BrowserRouter>
    <AuthProvider>
      <SettingsProvider>
        <Preview />
      </SettingsProvider>
    </AuthProvider>
  </BrowserRouter>,
);
